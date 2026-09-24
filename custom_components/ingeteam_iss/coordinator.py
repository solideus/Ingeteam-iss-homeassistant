"""Polling and confirmed writes for Ingeteam ISS."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .alarms import decode_alarms
from .api import IngeteamApi, IngeteamApiError, IngeteamAuthError
from .const import DEFAULT_SCAN_INTERVAL, DEFAULT_SSE_TIMEOUT, DOMAIN
from .telemetry import IngeteamTelemetryCoordinator

_LOGGER = logging.getLogger(__name__)


class IngeteamCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinate polls and serialize write/readback operations."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: IngeteamApi,
        scan_interval: int = DEFAULT_SCAN_INTERVAL,
        *,
        config_entry: ConfigEntry,
        sse_timeout: int = DEFAULT_SSE_TIMEOUT,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
            config_entry=config_entry,
        )
        self.api = api
        self.device_info: dict[str, Any] = {}
        self._operation_lock = asyncio.Lock()
        self.alarms: list[dict] = []
        self.raw_alarms: dict = {}
        self._alarm_snapshot: dict = {}
        self.telemetry = IngeteamTelemetryCoordinator(
            hass, api, config_entry=config_entry, timeout=sse_timeout
        )

    async def _async_update_data(self) -> dict[str, Any]:
        async with self._operation_lock:
            try:
                holding = await self.api.async_read_holding()
            except IngeteamAuthError as err:
                raise ConfigEntryAuthFailed(str(err)) from err
            except IngeteamApiError as err:
                raise UpdateFailed(str(err)) from err
            # Missing telemetry must not disable otherwise working EMS controls.
            try:
                online = await self.api.async_read_online()
            except IngeteamApiError as err:
                _LOGGER.debug("Live telemetry update failed: %s", err)
                online = {}
            self.alarms, self.raw_alarms = decode_alarms(
                online, self.api.capabilities, self.hass.config.language
            )
            current = {(a["address"], a["bit"]): a for a in self.alarms}
            valid_addresses = {address for address, _ in online}
            for key in self._alarm_snapshot.keys() | current.keys():
                if key[0] not in valid_addresses:
                    continue  # A failed read is not an alarm clearing.
                if (key in current) != (key in self._alarm_snapshot):
                    self.hass.bus.async_fire(
                        f"{DOMAIN}_alarm",
                        {
                            **(current.get(key) or self._alarm_snapshot[key]),
                            "active": key in current,
                            "entry_id": self.config_entry.entry_id,
                        },
                    )
            self._alarm_snapshot = {
                **{
                    k: v
                    for k, v in self._alarm_snapshot.items()
                    if k[0] not in valid_addresses
                },
                **current,
            }
            return {"holding": holding, "online": online}

    async def async_write(self, address: int, startbit: int, value: int) -> None:
        """Write one field and confirm it immediately."""
        await self.async_write_many([(address, startbit, value)])

    async def async_write_many(self, values: list[tuple[int, int, int]]) -> None:
        """Read back every write without the polling refresh debounce."""
        async with self._operation_lock:
            try:
                await self.api.async_write_holding_values(values)
                holding = await self.api.async_read_holding()
            except IngeteamApiError as err:
                raise HomeAssistantError(str(err)) from err
            self.async_set_updated_data(
                {
                    "holding": holding,
                    "online": (self.data or {}).get("online", {}),
                }
            )
            if any(
                holding.get((address, bit)) != value for address, bit, value in values
            ):
                raise HomeAssistantError(
                    "The inverter did not return the requested value after writing"
                )
