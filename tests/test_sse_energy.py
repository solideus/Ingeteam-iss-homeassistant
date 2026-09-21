"""Pure protocol and energy regression tests using synthetic scenarios."""

import json
from copy import deepcopy
from pathlib import Path

import pytest

from custom_components.ingeteam_iss.const import SSE_PHASE_EVENT
from custom_components.ingeteam_iss.energy import ENERGY_SOURCES, EnergyAccumulator
from custom_components.ingeteam_iss.sse import (
    MAX_EVENT_SIZE,
    SSEEvent,
    decode_telemetry,
    iter_sse,
)

SCENARIOS = json.loads((Path(__file__).parent / "fixtures/scenarios.json").read_text())


def decode(payload):
    return decode_telemetry(SSEEvent(SSE_PHASE_EVENT, json.dumps(payload)))


@pytest.mark.parametrize(
    "name,pv,load,imp,exp,charge,discharge",
    [
        ("grid_charge", 4000, 2500, 3000, 0, 4500, 0),
        ("battery_export", 3500, 2000, 0, 2000, 0, 500),
        ("self_consumption", 1200, 3200, 50, 0, 0, 2050),
        ("battery_disconnected", 0, 800, 800, 0, None, None),
        ("pv_charge", 5000, 2000, 0, 0, 3000, 0),
    ],
)
def test_synthetic_operating_scenarios(name, pv, load, imp, exp, charge, discharge):
    sample = decode(SCENARIOS[name])
    expected = (pv, load, imp, exp, charge, discharge)
    assert tuple(sample[source] for source in ENERGY_SOURCES.values()) == expected
    accumulator = EnergyAccumulator()
    accumulator.update(sample, 0)
    for second in range(1, 3601):
        accumulator.update(sample, second)
    assert tuple(accumulator.totals.values()) == pytest.approx(
        tuple((p or 0) / 1000 for p in expected)
    )


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize("size", [1, 7, 4096])
@pytest.mark.asyncio
async def test_sse_framing_multiline_utf8_and_comments(newline, size):
    lines = [
        ": heartbeat",
        "event: /ems/sse/phases",
        'data: {"Phases":',
        'data: [{"Phase":4,"pv":0,"label":"Batería"}]}',
        "",
        "event: other",
        "data: ignored",
        "",
        "data: truncated",
    ]
    raw = ("\ufeff" + newline.join(lines)).encode()

    async def chunks():
        for i in range(0, len(raw), size):
            yield raw[i : i + size]

    events = [event async for event in iter_sse(chunks())]
    assert len(events) == 2
    assert decode_telemetry(events[0])["pv_total_power"] == 0
    assert events[1] == SSEEvent("other", "ignored")


@pytest.mark.asyncio
async def test_sse_oversize_and_invalid_utf8():
    for raw in (b"data: " + b"x" * (MAX_EVENT_SIZE + 1), b"data: \xff\n\n"):

        async def chunks():
            yield raw

        with pytest.raises((ValueError, UnicodeError)):
            _ = [event async for event in iter_sse(chunks())]


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "[1]",
        "null",
        "{}",
        '{"Phases":null}',
        '{"Phases":[{}]}',
        '{"Phases":[{"Phase":4,"pv":true}]}',
    ],
)
def test_bad_json_and_shapes_ignored(raw):
    assert decode_telemetry(SSEEvent(SSE_PHASE_EVENT, raw)) is None


def test_ignore_other_events_and_duplicate_aggregate():
    payload = SCENARIOS["grid_charge"]
    assert decode_telemetry(SSEEvent("/ems/sse/stream", json.dumps(payload))) is None
    ambiguous = {"Phases": payload["Phases"] * 2}
    assert decode(ambiguous) is None
    combined = {"Phases": [{"Phase": 1, "pv": 99999}, *payload["Phases"]]}
    assert decode(combined)["pv_total_power"] == 4000


@pytest.mark.parametrize(
    "bad", [None, True, "1", "bad", float("nan"), float("inf"), -1]
)
def test_missing_or_invalid_fields_are_not_zero(bad):
    payload = deepcopy(SCENARIOS["grid_charge"])
    payload["Phases"][0]["PacCharge"] = bad
    sample = decode(payload)
    assert sample["battery_charge_power"] is None
    assert sample["battery_power"] is None
    assert sample["grid_import_power"] == 3000


def test_battery_disconnect_and_legitimate_zero():
    sample = decode(SCENARIOS["battery_disconnected"])
    for key in (
        "battery_soc",
        "battery_power",
        "battery_voltage",
        "battery_charge_power",
        "battery_discharge_power",
    ):
        assert sample[key] is None
    payload = deepcopy(SCENARIOS["battery_disconnected"])
    payload["Phases"][0].update(StatusBat=1, vbat=199)
    sample = decode(payload)
    assert sample["battery_soc"] == sample["battery_power"] == 0
    assert sample["battery_voltage"] == 199


def test_no_extrapolation_across_gaps_invalid_values_and_restart():
    acc = EnergyAccumulator()
    sample = {source: 3600 for source in ENERGY_SOURCES.values()}
    acc.update(sample, 10)
    acc.update(sample, 11)
    assert acc.totals["pv_energy"] == pytest.approx(0.001)
    acc.update(sample, 100)  # 89-second gap: discard the whole interval.
    assert acc.totals["pv_energy"] == pytest.approx(0.001)
    acc.update(sample, 101)
    assert acc.totals["pv_energy"] == pytest.approx(0.002)
    acc.update({**sample, "pv_total_power": None}, 102)
    acc.update(sample, 103)
    assert acc.totals["pv_energy"] == pytest.approx(0.002)
    assert acc.totals["load_energy"] == pytest.approx(0.004)
    acc.break_interval()
    acc.update(sample, 104)
    assert acc.totals["load_energy"] == pytest.approx(0.004)
    restored = EnergyAccumulator()
    restored.restore(acc.totals)
    restored.update(sample, 1000)
    assert restored.totals == acc.totals


def test_left_rule_direction_change_and_internal_precision():
    acc = EnergyAccumulator()
    sample = {"grid_import_power": 3600, "grid_export_power": 0}
    acc.update(sample, 0)
    acc.update({"grid_import_power": 0, "grid_export_power": 7200}, 1)
    acc.update({"grid_import_power": 0, "grid_export_power": 7200}, 2)
    assert acc.totals["grid_import_energy"] == pytest.approx(0.001)
    assert acc.totals["grid_export_energy"] == pytest.approx(0.002)
    tiny = EnergyAccumulator()
    for second in range(3601):
        tiny.update({"pv_total_power": 1}, second)
    assert tiny.totals["pv_energy"] == pytest.approx(0.001)


def test_non_monotonic_clock_does_not_subtract_energy():
    acc = EnergyAccumulator()
    for instant in (10, 9, 9):
        acc.update({"pv_total_power": 3600}, instant)
    assert acc.totals["pv_energy"] == 0


def test_restore_sanitizes_values():
    acc = EnergyAccumulator()
    acc.restore(
        {
            "pv_energy": 12.345678,
            "load_energy": float("nan"),
            "grid_import_energy": -5,
            "other": 3,
        }
    )
    assert acc.totals["pv_energy"] == 12.345678
    assert acc.totals["load_energy"] == acc.totals["grid_import_energy"] == 0
    assert "other" not in acc.totals
