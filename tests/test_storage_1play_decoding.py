"""STORAGE 1Play decoding with real captures; no Home Assistant needed."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from custom_components.ingeteam_iss.alarms import decode_alarms, label_for
from custom_components.ingeteam_iss.const import SSE_PHASE_EVENT, SSE_STREAM_EVENT
from custom_components.ingeteam_iss.models import (
    MODEL_ISS,
    MODEL_STORAGE_1PLAY,
    PROFILES,
    STORAGE_1PLAY_ALARM_FIELDS,
    detect_model,
    get_profile,
)
from custom_components.ingeteam_iss.sse import (
    SSEEvent,
    decode_stream,
    decode_telemetry,
    decode_telemetry_per_phase,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT / "tests/fixtures/storage_1play.json").read_text("utf-8"))


def phases(name):
    return SSEEvent(SSE_PHASE_EVENT, json.dumps(FIXTURE["sse"][name]["phases"]))


def stream(name):
    return SSEEvent(SSE_STREAM_EVENT, json.dumps(FIXTURE["sse"][name]["stream"]))


def test_iss_decoder_discards_1play_events():
    """The original failure: every 1Play phase event was discarded."""
    assert decode_telemetry(phases("night")) is None
    assert decode_telemetry(phases("solar")) is None


def test_night_capture():
    sample = decode_telemetry_per_phase(phases("night"))
    assert sample["pv_total_power"] == 0
    assert sample["external_grid_power"] == 7
    assert sample["grid_import_power"] == 7
    assert sample["grid_export_power"] == 0
    # Household load = inverter AC output (1812 W) + grid (7 W).
    assert sample["total_load_power"] == 1819
    assert sample["battery_discharge_power"] == 1919
    assert sample["battery_charge_power"] == 0
    assert sample["battery_power"] == 1919
    assert sample["battery_soc"] == 15
    assert sample["battery_voltage"] == 190


def test_solar_capture():
    sample = decode_telemetry_per_phase(phases("solar"))
    # PdcPVStorage equals the stream's PacPV in the same second.
    assert (
        sample["pv_total_power"]
        == FIXTURE["sse"]["solar"]["stream"]["Devices"][0]["PacPV"]
    )
    assert sample["battery_charge_power"] == 1109
    assert sample["battery_power"] == -1109
    assert sample["total_load_power"] == 1489 + 20


def test_stream_status_codes():
    assert decode_stream(stream("night")) == {
        "battery_status": 1,
        "inverter_status": 3,
    }
    assert decode_stream(stream("solar"))["battery_status"] == 2
    # Phase events and malformed payloads are not status updates.
    assert decode_stream(phases("night")) is None
    assert decode_stream(SSEEvent(SSE_STREAM_EVENT, "{")) is None
    assert decode_stream(SSEEvent(SSE_STREAM_EVENT, '{"Devices": [{}]}')) is None


def test_missing_phase_value_is_not_zero():
    payload = json.loads(json.dumps(FIXTURE["sse"]["night"]["phases"]))
    del payload["Phases"][1]["W"]
    sample = decode_telemetry_per_phase(SSEEvent(SSE_PHASE_EVENT, json.dumps(payload)))
    assert sample["external_grid_power"] is None
    assert sample["total_load_power"] is None
    assert sample["pv_total_power"] == 0


def test_aggregate_phase_still_uses_iss_decoder():
    payload = {"Phases": [{"Phase": 4, "pv": 100, "cons": 50, "W": -50}]}
    event = SSEEvent(SSE_PHASE_EVENT, json.dumps(payload))
    assert decode_telemetry_per_phase(event) == decode_telemetry(event)


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"compatible": [{"firmware": "ABH1002AL"}]}, MODEL_STORAGE_1PLAY),
        ({"compatible": [{"firmware": "ABH1007AE"}]}, MODEL_ISS),
        ({"compatible": [{"firmware": "XYZ"}]}, None),
        ({}, None),
    ],
)
def test_detect_model(payload, expected):
    assert detect_model(payload) == expected


def test_detect_model_from_real_map():
    assert detect_model(FIXTURE["map"]) == MODEL_STORAGE_1PLAY


def test_profiles():
    assert get_profile(None).key == MODEL_ISS
    assert get_profile("unknown").key == MODEL_ISS
    iss = PROFILES[MODEL_ISS]
    play = PROFILES[MODEL_STORAGE_1PLAY]
    assert iss.writable and "number" in iss.platforms
    assert play.writable
    assert set(play.platforms) == {
        "sensor",
        "binary_sensor",
        "number",
        "switch",
        "select",
    }
    assert "time" not in play.platforms


# Each enabled 1Play control and the label of its own map entry.
EXPECTED_CONTROLS = {
    "soc_max": (123, 0, "SOCmax"),
    "soc_grid": (124, 0, "SOCgrid"),
    "soc_min": (125, 0, "SOCmin"),
    "max_grid_charge_power": (128, 0, "Maximum battery charging power from the grid"),
    "max_grid_injection_power": (129, 0, "Maximum power injected to the grid"),
    "bms_max_charge_current": (116, 0, "Maximum Charge Current"),
    "battery_charge_priority": (132, 4, "Battery Charging Priority"),
    "battery_backup": (132, 1, "Battery-Backup Function"),
}


def test_1play_controls_match_their_map_entries():
    """Every enabled 1Play control is the expected setting of the device map."""
    number = pytest.importorskip("custom_components.ingeteam_iss.number")
    select = pytest.importorskip("custom_components.ingeteam_iss.select")
    switch = pytest.importorskip("custom_components.ingeteam_iss.switch")
    profile = PROFILES[MODEL_STORAGE_1PLAY]
    assert set(profile.control_keys) == set(EXPECTED_CONTROLS)
    fields = {(f["add"], f.get("start", 0)): f for f in FIXTURE["map"]["holding"]}
    labels = FIXTURE["map"]["langs"]["ENGLISH"]
    descriptions = (
        *number.STORAGE_1PLAY_NUMBERS,
        *select.STORAGE_1PLAY_SELECTS,
        *switch.STORAGE_1PLAY_SWITCHES,
    )
    assert {d.key for d in descriptions} == set(EXPECTED_CONTROLS)
    read = {
        address
        for r in profile.holding_ranges
        for address in range(r["address"], r["address"] + r["length"])
    }
    for desc in descriptions:
        address, bit, label = EXPECTED_CONTROLS[desc.key]
        assert (desc.register.address, desc.register.startbit) == (address, bit)
        assert address in read, desc.key
        field = fields[address, bit]
        assert labels[field["tid"]].startswith(label), desc.key
        assert field["sc"] == 1
        if hasattr(desc, "native_min_value"):
            assert (field["min"], field["max"]) == (
                desc.native_min_value,
                desc.native_max_value,
            ), desc.key
    # Select options follow the map's custom type order (0, 1).
    priority = select.STORAGE_1PLAY_SELECTS[0]
    custom = FIXTURE["map"]["customtypes"][fields[132, 4]["ty"]]["values"]
    assert len(priority.options) == len(custom)


def test_1play_ranges_cover_every_online_register_of_the_map():
    declared = {f["add"] for f in FIXTURE["map"]["online"]}
    ranges = PROFILES[MODEL_STORAGE_1PLAY].online_ranges
    read = {
        address
        for r in ranges
        for address in range(r["address"], r["address"] + r["length"])
    }
    assert declared <= read


def test_1play_sensor_divisors_match_the_map_scale():
    """value = raw * sc / 100000 for every scaled 1Play sensor."""
    sensor = pytest.importorskip("custom_components.ingeteam_iss.sensor")
    scale = {f["add"]: f["sc"] for f in FIXTURE["map"]["online"]}
    for desc in sensor.STORAGE_1PLAY_SENSORS:
        if desc.sse:
            continue
        address = desc.register.address
        assert desc.divisor == 100000 / scale[address], desc.key


def test_1play_alarms_use_their_own_addresses():
    online = {(int(a), 0): v for a, v in FIXTURE["online"].items()}
    alarms, raw = decode_alarms(
        online, FIXTURE["map"], "en", STORAGE_1PLAY_ALARM_FIELDS
    )
    assert alarms == []
    assert set(raw) == set(STORAGE_1PLAY_ALARM_FIELDS.values())
    # With the ISS addresses the same readings become false alarms.
    false_alarms, _ = decode_alarms(online, FIXTURE["map"], "en")
    assert false_alarms


def test_1play_bms_alarm_labels():
    online = {(47, 0): 0b101}
    alarms, _ = decode_alarms(online, FIXTURE["map"], "en", STORAGE_1PLAY_ALARM_FIELDS)
    assert [a["description"] for a in alarms] == [
        "High Current during Charge",
        "Low Voltage",
    ]


@pytest.mark.parametrize(
    ("address", "code", "label"),
    [
        (12, 11, "On-grid Mode"),
        (21, 1, "Discharging"),
        (59, 7, "Self-consumption by ISS 1Play"),
    ],
)
def test_state_labels_from_map(address, code, label):
    assert label_for(FIXTURE["map"], address, code, "en") == label
