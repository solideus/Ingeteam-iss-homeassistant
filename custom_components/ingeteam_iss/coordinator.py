"""Polling and confirmed writes for Ingeteam ISS."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta, tzinfo
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .alarms import decode_alarms, raw_integer
from .api import IngeteamApi, IngeteamApiError, IngeteamAuthError
from .const import DEFAULT_SCAN_INTERVAL, DEFAULT_SSE_TIMEOUT, DOMAIN
from .models import MODEL_ISS, get_profile
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
        time_zone: tzinfo,
        sse_timeout: int = DEFAULT_SSE_TIMEOUT,
        model: str = MODEL_ISS,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
            config_entry=config_entry,
        )
        self.api = api
        self.profile = get_profile(model)
        self.device_info: dict[str, Any] = {}
        self._operation_lock = asyncio.Lock()
        self.alarms: list[dict] = []
        self.raw_alarms: dict = {}
        self._alarm_snapshot: dict = {}
        self.missing_alarm_categories: list[str] = []
        self.stale_alarm_categories: list[str] = []
        self.alarm_coverage_complete = False
        self.telemetry = IngeteamTelemetryCoordinator(
            hass,
            api,
            config_entry=config_entry,
            time_zone=time_zone,
            timeout=sse_timeout,
        )
        self.telemetry.decode_telemetry = self.profile.decode_telemetry
        self.telemetry.decode_stream = self.profile.decode_stream

    async def _async_update_data(self) -> dict[str, Any]:
        async with self._operation_lock:
            fields = self.profile.alarm_fields
            if self.profile.writable:
                try:
                    holding = await self.api.async_read_holding(
                        self.profile.holding_ranges
                    )
                except IngeteamAuthError as err:
                    raise ConfigEntryAuthFailed(str(err)) from err
                except IngeteamApiError as err:
                    raise UpdateFailed(str(err)) from err
                # Missing telemetry must not disable otherwise working EMS controls.
                try:
                    online = await self.api.async_read_online(
                        self.profile.online_ranges
                    )
                except IngeteamApiError as err:
                    _LOGGER.debug("Live telemetry update failed: %s", err)
                    online = {}
            else:
                # Profiles without holding ranges never read or write them.
                holding = {}
                try:
                    online = await self.api.async_read_online(
                        self.profile.online_ranges
                    )
                except IngeteamAuthError as err:
                    raise ConfigEntryAuthFailed(str(err)) from err
                except IngeteamApiError as err:
                    raise UpdateFailed(str(err)) from err
            alarms, self.raw_alarms = decode_alarms(
                online, self.api.capabilities, self.hass.config.language, fields
            )
            current = {(a["address"], a["bit"]): a for a in alarms}
            expected = {
                address for address in fields if self.api.supports("online", address)
            }
            valid_addresses = {
                address
                for address in fields
                if raw_integer(online.get((address, 0))) is not None
            }
            self.missing_alarm_categories = [
                fields[address] for address in sorted(expected - valid_addresses)
            ]
            self.alarm_coverage_complete = (
                bool(expected) and not self.missing_alarm_categories
            )
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
            self.alarms = [
                {**alarm, "stale": key[0] not in valid_addresses}
                for key, alarm in sorted(self._alarm_snapshot.items())
            ]
            self.stale_alarm_categories = sorted(
                {alarm["category"] for alarm in self.alarms if alarm["stale"]}
            )
            return {"holding": holding, "online": online}

    async def async_write(self, address: int, startbit: int, value: int) -> None:
        """Write one field and confirm it immediately."""
        await self.async_write_many([(address, startbit, value)])

    async def async_write_many(self, values: list[tuple[int, int, int]]) -> None:
        """Read back every write without the polling refresh debounce."""
        if not self.profile.writable:
            raise HomeAssistantError("This inverter model is read-only")
        async with self._operation_lock:
            try:
                await self.api.async_write_holding_values(values)
                holding = await self.api.async_read_holding(self.profile.holding_ranges)
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
