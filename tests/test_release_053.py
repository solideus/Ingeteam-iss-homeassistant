"""Regression cases discovered in the 0.5.3 audit and physical installation."""

import json
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest
from homeassistant.core import callback
from homeassistant.util import dt as dt_util
from test_calendar_publication import Clock
from test_calendar_publication import controlled as controlled
from test_integration import ROOT, emit, entity_id
from test_integration import system as system

from custom_components.ingeteam_iss.accounting import CalendarEnergy
from custom_components.ingeteam_iss.alarms import ALARM_FIELDS, decode_alarms
from custom_components.ingeteam_iss.api import IngeteamApi, IngeteamApiError
from custom_components.ingeteam_iss.const import DOMAIN
from custom_components.ingeteam_iss.energy import EnergyAccumulator


def sample():
    return {"total_load_power": 3600, "grid_import_power": 3600, "grid_export_power": 0}


@pytest.mark.parametrize("timer_first", [True, False])
def test_early_close_preserves_late_sample_and_last_five_seconds(timer_first):
    acc = CalendarEnergy(timezone.utc)
    acc.update(sample(), 0, 3593)
    acc.update(sample(), 1, 3594)
    if timer_first:
        acc.tick(3595)
    acc.update(sample(), 3, 3596)
    if not timer_first:
        acc.tick(3596)
    # Timer/SSE ordering may place the in-flight tail in the next window, but
    # neither the observed energy nor the already-published settlement is lost.
    settled = acc.values["net_import_energy"]
    assert settled == pytest.approx(0.001 if timer_first else 0.002)
    assert settled + acc.imported == pytest.approx(0.003)
    for second in range(3597, 3601):
        acc.update(sample(), second - 3593, second)
    assert acc.values["net_import_energy"] == settled
    assert settled + acc.imported == pytest.approx(0.007)
    assert acc.values["load_energy_daily"] == pytest.approx(0.007)
    acc.tick(7195)
    assert acc.values["net_import_energy"] == pytest.approx(0.007)
    acc.tick(7200)
    assert acc.values["net_import_energy"] == pytest.approx(0.007)


def test_saved_future_nominal_hour_does_not_look_like_clock_rollback():
    acc = CalendarEnergy(timezone.utc)
    acc.update(sample(), 0, 3596)
    acc.update(sample(), 1, 3597)
    restored = CalendarEnergy(timezone.utc)
    restored.restore(acc.dump())
    restored.tick(3598)
    restored.update(sample(), 0, 3598)
    restored.update(sample(), 1, 3599)
    assert restored.imported == pytest.approx(0.002)
    assert restored.values["net_import_energy"] == 0


def test_legacy_052_pending_bucket_is_settled_once_on_upgrade():
    acc = CalendarEnergy(timezone.utc)
    acc.restore(
        {
            "values": {"net_import_energy": 10},
            "hour": 0,
            "imported": 0.25,
            "exported": 0.1,
            "day": "1970-01-01",
            "month": "1970-01",
        }
    )
    acc.tick(3597)
    assert acc.values["net_import_energy"] == pytest.approx(10.15)
    restored = CalendarEnergy(timezone.utc)
    restored.restore(acc.dump())
    restored.tick(3598)
    restored.tick(3600)
    assert restored.values["net_import_energy"] == pytest.approx(10.15)


@pytest.mark.parametrize("start", ["2026-03-29T00:59:53", "2026-10-25T00:59:53"])
def test_early_cut_and_actual_dst_transition_close_one_window(start):
    from zoneinfo import ZoneInfo

    zone = ZoneInfo("Europe/Madrid")
    stamp = datetime.fromisoformat(start).replace(tzinfo=timezone.utc).timestamp()
    acc = CalendarEnergy(zone)
    for second in range(11):
        acc.update(sample(), second, stamp + second)
        acc.tick(stamp + second)
    assert acc.values["net_import_energy"] == pytest.approx(0.002)
    assert acc.imported == pytest.approx(0.008)
    assert acc.values["load_energy_daily"] == pytest.approx(0.010)
    before = datetime.fromtimestamp(stamp, zone)
    after = datetime.fromtimestamp(stamp + 10, zone)
    assert before.utcoffset() != after.utcoffset()


@pytest.mark.parametrize("timer_first", [True, False])
def test_net_settlements_and_pending_balance_preserve_signed_observed_energy(
    timer_first,
):
    acc = CalendarEnergy(timezone.utc)
    gross = EnergyAccumulator()
    start = datetime(2026, 9, 24, 10, 10, tzinfo=timezone.utc).timestamp()
    for second in range(7201):
        watts = (second % 31 - 15) * 300
        current = {
            "total_load_power": 500 + second % 1000,
            "grid_import_power": max(watts, 0),
            "grid_export_power": max(-watts, 0),
        }
        if timer_first and second % 5 == 0:
            acc.tick(start + second)
        acc.update(current, second, start + second)
        gross.update(current, second)
        if not timer_first and second % 5 == 0:
            acc.tick(start + second)
    assert acc.values["net_import_energy"] - acc.values[
        "net_export_energy"
    ] + acc.imported - acc.exported == pytest.approx(
        gross.totals["grid_import_energy"] - gross.totals["grid_export_energy"],
        abs=1e-10,
    )
    assert acc.values["load_energy_daily"] == gross.totals["load_energy"]


@pytest.mark.parametrize("cadence", [0, 5, 10, 30])
async def test_net_closure_publishes_before_statistics_boundary(
    controlled, monkeypatch, cadence
):
    hass, entry, sse = controlled
    sse.publish_interval = cadence
    clock = Clock(hass, "2026-09-24T10:59:52")
    monkeypatch.setattr(
        "homeassistant.helpers.entity.timer", lambda: clock.now().timestamp()
    )
    lifetime_id = entity_id(hass, "sensor", "net_import_energy")
    with clock.patch(monkeypatch, hass):
        sse.async_receive(sample())
        clock.second = 1
        sse.async_receive(sample())
        power_updates = Mock()
        remove = sse.async_add_listener(power_updates)
        clock.second = 3  # HH:59:55, without a new SSE event.
        sse._tick(clock.now())
        state = hass.states.get(lifetime_id)
        assert float(state.state) == 0.001
        assert state.last_updated == clock.now()
        assert state.last_updated.minute == 59 and state.last_updated.second == 55
        assert power_updates.call_count == 0
        sse._tick(clock.now())
        assert sse.accounting.values["net_import_energy"] == pytest.approx(0.001)
        remove()


async def test_hourly_timer_registered_and_removed(system, monkeypatch):
    hass, entry, _ = system
    sse = entry.runtime_data.telemetry
    await sse.async_stop()
    cancel = Mock()
    track = Mock(return_value=cancel)
    monkeypatch.setattr(
        "custom_components.ingeteam_iss.telemetry.async_track_utc_time_change", track
    )
    sse.async_start()
    assert track.call_args.kwargs == {"minute": 59, "second": 55}
    await sse.async_stop()
    assert cancel.call_count == 1
    assert sse._cancel_net_close is None


@pytest.mark.parametrize("start", ["2026-09-24T21:59:52", "2026-09-30T21:59:52"])
async def test_reload_publishes_old_net_closure_before_day_month_reset(
    system, monkeypatch, start
):
    hass, entry, data = system
    hass.config.time_zone = "Europe/Madrid"
    sse = entry.runtime_data.telemetry
    await sse.async_stop()
    zone = await dt_util.async_get_time_zone("Europe/Madrid")
    sse.accounting = CalendarEnergy(zone)
    stamp = datetime.fromisoformat(start).replace(tzinfo=timezone.utc)
    sse.accounting.update(sample(), 0, stamp.timestamp())
    sse.accounting.update(sample(), 1, stamp.timestamp() + 1)
    sse._publish_calendar_periods()
    await sse._store.async_save(sse._stored_data())
    observed = {
        key: []
        for key in (
            "net_import_energy_daily",
            "net_import_energy_monthly",
            "load_energy_daily",
            "load_energy_monthly",
        )
    }
    ids = {entity_id(hass, "sensor", key): key for key in observed}

    @callback
    def changed(event):
        if (key := ids.get(event.data["entity_id"])) and (
            state := event.data["new_state"]
        ):
            if state.state not in ("unavailable", "unknown"):
                observed[key].append(float(state.state))

    remove = hass.bus.async_listen("state_changed", changed)
    data["sse_initial"] = None
    monkeypatch.setattr(
        dt_util,
        "utcnow",
        lambda: datetime.fromtimestamp(stamp.timestamp() + 70, timezone.utc),
    )
    # This test travels to September while the host wall clock keeps running.
    # Registration is tested separately; do not let real timers catch up to the
    # host date and replace the simulated restoration instant.
    for tracker in ("async_track_time_interval", "async_track_utc_time_change"):
        monkeypatch.setattr(
            f"custom_components.ingeteam_iss.telemetry.{tracker}",
            Mock(return_value=lambda: None),
        )
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    remove()
    for key, values in observed.items():
        assert 0.001 in values
        if key.endswith("daily") or "09-30" in start:
            assert values[-1] == 0, (key, values)
        # Recorder's total_increasing sum must include the pending old subtotal.
        assert sum(
            new - old if new >= old else new for old, new in zip([0.0, *values], values)
        ) == pytest.approx(0.001)
    assert entry.runtime_data.telemetry.accounting.values[
        "net_import_energy"
    ] == pytest.approx(0.001)


async def test_partial_alarm_read_keeps_known_active_alarm_and_coverage(system):
    hass, entry, data = system
    data["online"].update({(address, 0): 0 for address in ALARM_FIELDS})
    data["online"][73, 0] = 4
    received = []
    remove = hass.bus.async_listen(
        f"{DOMAIN}_alarm", lambda event: received.append(event.data)
    )
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    del data["online"][73, 0]
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    binary = hass.states.get(entity_id(hass, "binary_sensor", "alarm_active"))
    count = hass.states.get(entity_id(hass, "sensor", "active_alarms"))
    assert binary.state == "on" and count.state == "1"
    assert not binary.attributes["coverage_complete"]
    assert binary.attributes["stale_categories"] == ["bms_warning"]
    assert count.attributes["alarms"][0]["stale"]
    assert len(received) == 1 and received[0]["active"]
    data["online"][73, 0] = 0
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(binary.entity_id).state == "off"
    assert hass.states.get(count.entity_id).state == "0"
    assert len(received) == 2 and not received[-1]["active"]
    remove()


async def test_partial_zero_alarm_read_is_unknown_not_confirmed_clear(system):
    hass, entry, data = system
    data["online"][10, 0] = 0
    await entry.runtime_data.async_refresh()
    for domain, key in (("binary_sensor", "alarm_active"), ("sensor", "active_alarms")):
        assert hass.states.get(entity_id(hass, domain, key)).state == "unavailable"


@pytest.mark.parametrize("bad", [-1, 2.9, True, "bad", float("nan"), float("inf")])
async def test_invalid_controls_do_not_keep_stale_values_or_interrupt_others(
    system, bad
):
    hass, entry, data = system
    data["holding"].update(
        {(86, 0): bad, (142, 0): 17, (100, 5): bad, (117, 0): bad, (132, 0): bad}
    )
    await entry.runtime_data.async_refresh()
    assert entry.runtime_data.last_update_success
    for domain, key in (
        ("number", "bms_max_charge_current"),
        ("select", "grid_charge_schedule_1_mode"),
        ("time", "grid_charge_schedule_1_start"),
        ("switch", "bms_soc_calibration"),
    ):
        assert hass.states.get(entity_id(hass, domain, key)).state == "unavailable"
    assert (
        hass.states.get(
            entity_id(hass, "number", "bms_max_on_grid_discharge_current")
        ).state
        == "17.0"
    )
    assert not data["writes"]


@pytest.mark.parametrize(
    "response",
    [
        {"Data": None},
        {"Data": [{"data": None}]},
        {"Data": [{"data": [{"address": "bad", "value": 1}]}]},
    ],
)
async def test_invalid_online_shapes_leave_holding_controls_working(
    system, monkeypatch, response
):
    hass, entry, _ = system
    api = entry.runtime_data.api
    original = api._request_json

    async def request(method, path, payload=None):
        return (
            response
            if "/online/read/" in path
            else await original(method, path, payload)
        )

    monkeypatch.setattr(api, "_request_json", request)
    await entry.runtime_data.async_refresh()
    assert entry.runtime_data.last_update_success
    assert (
        hass.states.get(entity_id(hass, "number", "bms_max_charge_current")).state
        == "22.0"
    )


def test_flatten_bad_items_preserves_valid_registers():
    response = {
        "Data": [
            None,
            {"data": None},
            {
                "data": [
                    {"address": "bad", "value": 1},
                    {"address": 1.5, "value": 3},
                    {"address": 86, "value": True},
                    {"address": 142, "value": 17},
                ]
            },
        ]
    }
    assert IngeteamApi._flatten_register_response(response) == {(142, 0): 17}
    with pytest.raises(IngeteamApiError):
        IngeteamApi._flatten_register_response({"Data": None})


@pytest.mark.parametrize(
    "mapping",
    [
        {"online": None},
        {"online": [{"add": 73, "ty": []}]},
        {"online": [{"add": 73, "ty": "bms"}], "customtypes": None},
        {
            "online": [{"add": 73, "ty": "bms"}],
            "customtypes": {"bms": {"values": {"00": []}}},
            "langs": None,
        },
    ],
)
def test_incomplete_alarm_map_keeps_undocumented_codes(mapping):
    alarms, raw = decode_alarms({(73, 0): 1}, mapping, "es")
    assert len(alarms) == 1 and not alarms[0]["documented"]
    assert raw["bms_warning"] == "0x0001"


REAL_CAPTURES = json.loads((ROOT / "tests/fixtures/real_sse_captures.json").read_text())


@pytest.mark.parametrize("name", REAL_CAPTURES)
async def test_original_user_sse_captures_in_home_assistant(system, name):
    hass, entry, data = system
    payload = REAL_CAPTURES[name]
    await emit(system, payload)
    phase = payload["Phases"][0]
    for key, expected in (
        ("pv_total_power", phase["pv"]),
        ("total_load_power", phase["cons"]),
        ("grid_import_power", max(phase["W"], 0)),
        ("grid_export_power", max(-phase["W"], 0)),
    ):
        assert float(hass.states.get(entity_id(hass, "sensor", key)).state) == expected
    assert (
        hass.states.get(entity_id(hass, "binary_sensor", "grid_connected")).state
        == "on"
    )
    assert hass.states.get(entity_id(hass, "sensor", "battery_soc")).state == (
        "unavailable" if phase["StatusBat"] == 7 else str(phase["soc"])
    )
    assert not data["writes"]
