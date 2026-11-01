"""Recorder publication uses a simulated clock; integration keeps every sample."""

from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
import pytest_asyncio
from homeassistant.const import EVENT_STATE_CHANGED
from homeassistant.core import callback
from homeassistant.util import dt as dt_util
from test_integration import entity_id
from test_integration import system as system

from custom_components.ingeteam_iss.accounting import ACCOUNTING_KEYS, CalendarEnergy
from custom_components.ingeteam_iss.energy import EnergyAccumulator
from custom_components.ingeteam_iss.sensor import IngeteamCalendarSensor


def reading(second=0, *, imp=1800, exp=0, load=3600):
    return {
        "total_load_power": load + second % 11,
        "pv_total_power": 2000 + second,
        "grid_import_power": imp,
        "grid_export_power": exp,
    }


class Clock:
    def __init__(self, hass, start):
        self.start = datetime.fromisoformat(start).replace(tzinfo=timezone.utc)
        self.origin = int(hass.loop.time()) + 60
        self.second = 0

    def time(self):
        return self.origin + self.second

    def now(self):
        return self.start + timedelta(seconds=self.second)

    @contextmanager
    def patch(self, monkeypatch, hass):
        with monkeypatch.context() as patch:
            patch.setattr(hass.loop, "time", self.time)
            patch.setattr(dt_util, "utcnow", self.now)
            yield self


@pytest_asyncio.fixture
async def controlled(system):
    hass, entry, _ = system
    sse = entry.runtime_data.telemetry
    await sse.async_stop()
    zone = await dt_util.async_get_time_zone("Europe/Madrid")
    sse.accounting = CalendarEnergy(zone)
    sse.energy = EnergyAccumulator()
    sse.last_event = None
    sse.valid_frames = 0
    return hass, entry, sse


def capture_publications(monkeypatch, clock):
    publications = defaultdict(list)
    original = IngeteamCalendarSensor.async_write_ha_state

    def write(entity):
        publications[entity._key].append((clock.second, entity.native_value))
        original(entity)

    monkeypatch.setattr(IngeteamCalendarSensor, "async_write_ha_state", write)
    return publications


@pytest.mark.parametrize("cadence", [0, 5, 10, 30])
async def test_every_sample_integrated_but_calendar_publishes_every_30_seconds(
    controlled, monkeypatch, cadence
):
    hass, _, sse = controlled
    sse.publish_interval = cadence
    clock = Clock(hass, "2026-09-24T10:10:00")
    publications = capture_publications(monkeypatch, clock)
    expected_load = 0.0
    expected_import = 0.0
    with clock.patch(monkeypatch, hass):
        sse.async_receive(reading())
        publications.clear()
        old = reading()
        for second in range(1, 601):
            clock.second = second
            current = reading(second, imp=1000 + second)
            sse.async_receive(current)
            expected_load += old["total_load_power"] / 3_600_000
            expected_import += old["grid_import_power"] / 3_600_000
            # Internal precision and anchors advance at 1 Hz, even between writes.
            assert sse.accounting.values["load_energy_daily"] == expected_load
            assert sse.energy.totals["load_energy"] == expected_load
            assert sse.accounting.imported == expected_import
            old = current
            power = hass.states.get(entity_id(hass, "sensor", "pv_total_power"))
            published_second = second if cadence == 0 else second // cadence * cadence
            assert float(power.state) == 2000 + published_second
    assert sse.valid_frames == 601
    for key in ACCOUNTING_KEYS:
        assert [second for second, _ in publications[key]] == list(range(30, 601, 30))
    assert float(
        hass.states.get(entity_id(hass, "sensor", "load_energy_daily")).state
    ) == round(expected_load, 6)
    assert sse._stored_data()["calendar"] == sse.accounting.dump()


@pytest.mark.parametrize(
    "start,day,month",
    [
        ("2026-09-24T10:59:58", False, False),
        ("2026-09-24T21:59:58", True, False),
        ("2026-09-30T21:59:58", True, True),
        ("2026-12-31T22:59:58", True, True),
        ("2026-03-29T00:59:58", False, False),
        ("2026-10-25T00:59:58", False, False),
    ],
)
async def test_final_subtotal_and_zero_are_published_at_period_boundaries(
    controlled, monkeypatch, start, day, month
):
    hass, _, sse = controlled
    clock = Clock(hass, start)
    publications = capture_publications(monkeypatch, clock)
    with clock.patch(monkeypatch, hass):
        sse.async_receive(reading())
        publications.clear()
        clock.second = 4
        sse.async_receive(reading())
    assert sse.accounting.values["load_energy_daily"] == pytest.approx(
        0.002 if day else 0.004
    )
    assert sse.accounting.values["load_energy_monthly"] == pytest.approx(
        0.002 if month else 0.004
    )
    assert sse.accounting.values["net_import_energy"] == pytest.approx(0.001)
    assert sse.accounting.values["hourly_net_balance"] == pytest.approx(-0.001)
    for key, reset in [("load_energy_daily", day), ("load_energy_monthly", month)]:
        assert publications[key] == ([(4, 0.002), (4, 0.0)] if reset else [])
        if reset:
            assert hass.states.get(entity_id(hass, "sensor", key)).state == "0.0"
    assert publications["hourly_net_balance"] == [(4, -0.001), (4, 0.0)]
    assert (
        float(hass.states.get(entity_id(hass, "sensor", "net_import_energy")).state)
        == 0.001
    )


@pytest.mark.parametrize("connected", [True, False])
async def test_idle_midnight_settlement_publishes_without_refreshing_power(
    controlled, monkeypatch, connected
):
    hass, _, sse = controlled
    clock = Clock(hass, "2026-12-31T22:59:56")
    publications = capture_publications(monkeypatch, clock)
    power_updates = Mock()
    with clock.patch(monkeypatch, hass):
        sse.async_receive(reading())
        clock.second = 1
        sse.async_receive(reading())
        if not connected:
            sse.async_mark_disconnected()
        publications.clear()
        remove = sse.async_add_listener(power_updates)
        clock.second = 9  # Safety margin elapsed; no more SSE samples.
        sse._tick(clock.now())
        snapshot = sse.accounting.dump()
        clock.second = 14
        sse._tick(clock.now())
        assert sse.accounting.dump() == snapshot
        remove()
    assert sse.accounting.values["net_import_energy"] == pytest.approx(0.0005)
    assert sse.accounting.values["load_energy_daily"] == 0
    assert sse.accounting.values["load_energy_monthly"] == 0
    assert (9, 0.001) in publications["load_energy_daily"]
    assert (
        float(hass.states.get(entity_id(hass, "sensor", "net_import_energy")).state)
        == 0.0005
    )
    assert power_updates.call_count == (0 if connected else 2)


async def test_recorded_states_keep_final_energy_even_when_reset_is_small(
    controlled, monkeypatch
):
    hass, _, sse = controlled
    clock = Clock(hass, "2026-09-30T21:59:59")
    recorded = []
    daily_id = entity_id(hass, "sensor", "load_energy_daily")

    @callback
    def state_changed(event):
        if event.data["entity_id"] == daily_id:
            recorded.append(float(event.data["new_state"].state))

    remove = hass.bus.async_listen(EVENT_STATE_CHANGED, state_changed)
    with clock.patch(monkeypatch, hass):
        sse.async_receive(reading())
        clock.second = 2
        sse.async_receive(reading())  # Old and new day both hold 0.001 kWh.
        clock.second = 32
        sse.async_receive(reading())  # Gap adds nothing; publication catches up.
    await hass.async_block_till_done()
    remove()
    assert recorded[-3:] == [0.001, 0.0, 0.001]
    # This is the total_increasing sum Recorder derives across the explicit reset.
    total = sum(
        new - old if new >= old else new for old, new in zip([0.0, *recorded], recorded)
    )
    assert total == pytest.approx(0.002)
    assert sse.energy.totals["load_energy"] == pytest.approx(0.002)


async def test_hourly_netting_import_and_export_settles_once(controlled, monkeypatch):
    hass, _, sse = controlled
    clock = Clock(hass, "2026-09-24T10:00:00")
    with clock.patch(monkeypatch, hass):
        for second in range(7201):
            clock.second = second
            # First hour: net import 0.9 kWh; second: net export 0.9 kWh.
            importing = second < 1800 or 5400 <= second < 7200
            sse.async_receive(
                reading(
                    imp=3600 if importing else 0,
                    exp=0 if importing else (1800 if second < 3600 else 5400),
                )
            )
        assert sse.accounting.values["net_import_energy"] == pytest.approx(0.9)
        assert sse.accounting.values["net_export_energy"] == pytest.approx(0.9)
        for direction in ("import", "export"):
            for suffix in ("", "_daily", "_monthly"):
                state = hass.states.get(
                    entity_id(hass, "sensor", f"net_{direction}_energy{suffix}")
                )
                assert float(state.state) == 0.9
        sse._tick(clock.now() + timedelta(seconds=10))
        assert sse.accounting.values["net_export_energy"] == pytest.approx(0.9)


async def test_disconnect_reconnect_and_reload_preserve_calendar_energy(
    system, monkeypatch
):
    hass, entry, data = system
    sse = entry.runtime_data.telemetry
    await sse.async_stop()
    # Use the current date so async_load_energy does not legitimately roll it over.
    clock = Clock(
        hass, dt_util.utcnow().replace(minute=10, second=0, microsecond=0).isoformat()
    )
    sse.accounting = CalendarEnergy(timezone.utc)
    with clock.patch(monkeypatch, hass):
        sse.async_receive(reading())
        clock.second = 1
        sse.async_receive(reading())
        sse.async_mark_disconnected()
        assert (
            float(hass.states.get(entity_id(hass, "sensor", "load_energy_daily")).state)
            == 0.001
        )
        before = sse.accounting.dump()
        clock.second = 100
        sse.async_receive(reading())
        assert sse.accounting.dump() == before
        clock.second = 101
        sse.async_receive(reading())
        assert sse.accounting.values["load_energy_daily"] == pytest.approx(0.002)
    saved = sse.accounting.dump()
    identities = {key: entity_id(hass, "sensor", key) for key in ACCOUNTING_KEYS}
    data["sse_initial"] = None
    assert await hass.config_entries.async_reload(entry.entry_id)
    restored = entry.runtime_data.telemetry
    assert restored.accounting.dump() == saved
    assert restored.accounting._previous is None
    assert not any(sse._calendar_listeners.values())
    for key, identity in identities.items():
        assert entity_id(hass, "sensor", key) == identity
        state = hass.states.get(identity)
        assert float(state.state) == round(saved["values"][key], 6)
        assert state.attributes["unit_of_measurement"] == "kWh"
        assert state.attributes["state_class"] == (
            "measurement" if key == "hourly_net_balance" else "total_increasing"
        )
        assert state.attributes.get("device_class") == (
            None if key == "hourly_net_balance" else "energy"
        )


@pytest.mark.parametrize("tick_first", [True, False])
async def test_midnight_timer_and_sse_order_preserve_recorded_subtotals(
    controlled, monkeypatch, tick_first
):
    hass, _, sse = controlled
    clock = Clock(hass, "2026-12-31T22:59:59")
    publications = capture_publications(monkeypatch, clock)
    with clock.patch(monkeypatch, hass):
        sse.async_receive(reading())
        publications.clear()
        if tick_first:
            clock.second = 1
            sse._tick(clock.now())
        clock.second = 2
        sse.async_receive(reading())
        if not tick_first:
            sse._tick(clock.now())
        clock.second = 32
        sse.async_receive(reading())
    for key in ("load_energy_daily", "load_energy_monthly"):
        values = [value for _, value in publications[key]]
        total = sum(
            new - old if new >= old else new for old, new in zip([0.0, *values], values)
        )
        assert total == pytest.approx(0.002)
        assert sse.accounting.values[key] == pytest.approx(0.001)
    assert sse.accounting.values["net_import_energy"] == pytest.approx(0.0005)


async def test_publication_failure_cannot_interrupt_accounting(controlled, monkeypatch):
    hass, _, sse = controlled
    clock = Clock(hass, "2026-09-30T21:59:59")
    broken = Mock(side_effect=RuntimeError("Synthetic entity failure"))
    with clock.patch(monkeypatch, hass):
        sse.async_receive(reading())
        remove = sse.async_add_calendar_listener("load_energy_daily", broken)
        clock.second = 2
        sse.async_receive(reading())
        remove()
        assert sse.accounting.values["load_energy_daily"] == pytest.approx(0.001)
        assert sse.accounting.values["net_import_energy"] == pytest.approx(0.0005)
        assert sse.accounting.take_period_updates() == []
        assert sse.valid_frames == 2
    assert broken.call_count == 2
