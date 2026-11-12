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
    assert set(play.platforms) == {"sensor", "binary_sensor", "number"}
    assert play.control_keys == ("soc_max",)
    assert play.holding_ranges == ({"address": 123, "length": 1},)


def test_1play_controls_match_their_map_entries():
    """Every enabled 1Play control is the same setting in the device map."""
    number = pytest.importorskip("custom_components.ingeteam_iss.number")
    fields = {(f["add"], f.get("start", 0)): f for f in FIXTURE["map"]["holding"]}
    for desc in number.NUMBERS:
        if desc.key not in PROFILES[MODEL_STORAGE_1PLAY].control_keys:
            continue
        field = fields[desc.register.address, desc.register.startbit]
        assert field["uw"] == 1
        assert (field["min"], field["max"]) == (
            desc.native_min_value,
            desc.native_max_value,
        )
        assert field["sc"] == 1
        label = FIXTURE["map"]["langs"]["ENGLISH"].get(field["tid"], "")
        assert label.startswith("SOCmax"), label


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
