"""Independent SSE coordinator, watchdog, reconnect and energy persistence."""

from __future__ import annotations

import asyncio
import logging
from contextlib import aclosing, suppress
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .accounting import CalendarEnergy
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
        self.accounting = CalendarEnergy(hass.config.time_zone)
        self.publish_interval = 0.0
        self._last_publish = float("-inf")
        self.latest_sample: dict[str, Any] = {}
        self.valid_frames = 0
        self.discarded_frames = 0
        self.incomplete_frames = 0
        self.connections = 0
        self.last_received: datetime | None = None
        self.disconnect_reason: str | None = None
        self.mean_interval: float | None = None
        self.missing_fields: list[str] = []
        self._cancel_tick = None
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
            if isinstance(saved.get("calendar"), dict):
                self.accounting.restore(saved["calendar"])
        self.accounting.tick(dt_util.utcnow().timestamp())

    @callback
    def _stored_data(self) -> dict:
        self._save_pending = False
        return {"totals": dict(self.energy.totals), "calendar": self.accounting.dump()}

    @callback
    def _schedule_save(self) -> None:
        if not self._save_pending:
            self._save_pending = True
            self._store.async_delay_save(self._stored_data, ENERGY_SAVE_INTERVAL)

    @callback
    def _tick(self, now) -> None:
        self.accounting.tick(now.timestamp())
        self._schedule_save()
        # Diagnostics and calendar resets also refresh when SSE is unavailable.
        if not self.connected:
            self.async_update_listeners()

    @callback
    def async_start(self) -> None:
        if self._task is None:
            self._stopping = False
            self._cancel_tick = async_track_time_interval(
                self.hass, self._tick, timedelta(seconds=5)
            )
            self._task = self._entry.async_create_background_task(
                self.hass, self._run(), f"{DOMAIN} SSE"
            )

    async def async_stop(self, _event=None) -> None:
        """Close the socket, await cancellation and flush accumulated energy."""
        self._stopping = True
        if self._cancel_tick:
            self._cancel_tick()
            self._cancel_tick = None
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        self.energy.break_interval()
        self.accounting.break_interval()
        await self._store.async_save(self._stored_data())

    @callback
    def async_receive(self, sample: dict[str, Any]) -> None:
        """Only call for a valid selected event; equal readings are still fresh."""
        now = dt_util.utcnow()
        mono = self.hass.loop.time()
        self.energy.update(sample, mono)
        self.accounting.update(sample, mono, now.timestamp())
        self._schedule_save()
        if self.last_event is not None and self.connected:
            interval = (now - self.last_event).total_seconds()
            if interval >= 0:
                self.mean_interval = (
                    interval
                    if self.mean_interval is None
                    else self.mean_interval * 0.9 + interval * 0.1
                )
        self.valid_frames += 1
        self.missing_fields = [key for key, value in sample.items() if value is None]
        if self.missing_fields:
            self.incomplete_frames += 1
        if not self.connected and self.last_disconnect is not None:
            _LOGGER.info("Ingeteam SSE telemetry recovered")
        recovered = not self.connected
        self.connected = True
        self.last_event = now
        self.latest_sample = sample
        if recovered or mono - self._last_publish >= self.publish_interval:
            self._last_publish = mono
            self.async_set_updated_data(sample)

    @callback
    def async_mark_disconnected(self) -> None:
        """Keep cumulative totals but clear readings and integration anchors."""
        if self.connected or self.last_disconnect is None:
            self.last_disconnect = dt_util.utcnow()
        self.connected = False
        self.energy.break_interval()
        self.accounting.break_interval()
        self.latest_sample = {}
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
                            self.connections += 1
                            async for event in events:
                                self.last_received = dt_util.utcnow()
                                sample = decode_telemetry(event)
                                if sample is None:
                                    self.discarded_frames += 1
                                    if event.event == SSE_PHASE_EVENT:
                                        self.energy.break_interval()
                                        self.accounting.break_interval()
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
                    self.disconnect_reason = type(err).__name__
                    if auth_failed:
                        self._entry.async_start_reauth(self.hass)
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
