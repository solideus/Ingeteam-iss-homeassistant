"""Independent SSE coordinator, watchdog, reconnect and energy persistence."""

from __future__ import annotations

import asyncio
import logging
from contextlib import aclosing, suppress
from datetime import datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .api import IngeteamApi, IngeteamApiError, IngeteamAuthError
from .const import DEFAULT_SSE_TIMEOUT, DOMAIN, ENERGY_SAVE_INTERVAL, SSE_PHASE_EVENT
from .energy import EnergyAccumulator
from .sse import decode_telemetry

_LOGGER = logging.getLogger(__name__)


class IngeteamTelemetryCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Push updates cannot reset the HTTP polling timer or control availability."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: IngeteamApi,
        *,
        config_entry: ConfigEntry,
        timeout: int = DEFAULT_SSE_TIMEOUT,
    ) -> None:
        super().__init__(hass, _LOGGER, name=f"{DOMAIN}_sse", config_entry=config_entry)
        self.api = api
        self._entry = config_entry
        self.device_info: dict[str, Any] = {}
        self.timeout = timeout
        self.connected = False
        self.last_event: datetime | None = None
        self.last_disconnect: datetime | None = None
        self.energy = EnergyAccumulator()
        self._store: Store = Store(
            hass,
            1,
            f"{DOMAIN}.{config_entry.entry_id}.energy",
            serialize_in_event_loop=True,
            atomic_writes=True,
        )
        self._save_pending = False
        self._task: asyncio.Task | None = None
        self._stopping = False
        self.data = {}

    async def async_load_energy(self) -> None:
        """Load totals before any entity is exposed or SSE event is consumed."""
        saved = await self._store.async_load()
        if isinstance(saved, dict) and isinstance(saved.get("totals"), dict):
            self.energy.restore(saved["totals"])

    @callback
    def _stored_data(self) -> dict:
        self._save_pending = False
        return {"totals": dict(self.energy.totals)}

    @callback
    def async_start(self) -> None:
        if self._task is None:
            self._stopping = False
            self._task = self._entry.async_create_background_task(
                self.hass, self._run(), f"{DOMAIN} SSE"
            )

    async def async_stop(self, _event=None) -> None:
        """Close the socket, await cancellation and flush accumulated energy."""
        self._stopping = True
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        self.energy.break_interval()
        await self._store.async_save(self._stored_data())

    @callback
    def async_receive(self, sample: dict[str, Any]) -> None:
        """Only call for a valid selected event; equal readings are still fresh."""
        if self.energy.update(sample, self.hass.loop.time()) and not self._save_pending:
            self._save_pending = True
            self._store.async_delay_save(self._stored_data, ENERGY_SAVE_INTERVAL)
        if not self.connected and self.last_disconnect is not None:
            _LOGGER.info("Ingeteam SSE telemetry recovered")
        self.connected = True
        self.last_event = dt_util.utcnow()
        self.async_set_updated_data(sample)

    @callback
    def async_mark_disconnected(self) -> None:
        """Keep cumulative totals but clear readings and integration anchors."""
        if self.connected or self.last_disconnect is None:
            self.last_disconnect = dt_util.utcnow()
        self.connected = False
        self.energy.break_interval()
        self.async_set_updated_data({})

    async def _run(self) -> None:
        delay = 1
        reported_failure = False
        try:
            while not self._stopping:
                auth_failed = False
                try:
                    # Comments, other event types and invalid JSON do not extend
                    # this deadline. A live TCP socket is not proof of fresh data.
                    async with asyncio.timeout(self.timeout) as watchdog:
                        async with aclosing(self.api.async_events()) as events:
                            async for event in events:
                                sample = decode_telemetry(event)
                                if sample is None:
                                    if event.event == SSE_PHASE_EVENT:
                                        self.energy.break_interval()
                                    continue
                                self.async_receive(sample)
                                watchdog.reschedule(
                                    self.hass.loop.time() + self.timeout
                                )
                                delay = 1
                                reported_failure = False
                    raise IngeteamApiError("SSE stream ended")
                except (IngeteamApiError, TimeoutError) as err:
                    auth_failed = isinstance(err, IngeteamAuthError)
                    self.async_mark_disconnected()
                    if not reported_failure:
                        _LOGGER.warning(
                            "Ingeteam SSE unavailable (%s); reconnecting. HTTP controls remain independent",
                            type(err).__name__,
                        )
                        reported_failure = True
                await asyncio.sleep(60 if auth_failed else delay)
                delay = min(delay * 2, 60)
        finally:
            self.async_mark_disconnected()
