"""Profile isolation and a frozen v0.5.3 TL M regression reference.

The fixture was generated once from c3b95df, before the extraction. These tests
do not import a second implementation, access Git, or contact an inverter.
"""

import ast
import json
from dataclasses import FrozenInstanceError
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from custom_components.ingeteam_iss.accounting import CalendarEnergy
from custom_components.ingeteam_iss.api import IngeteamApi
from custom_components.ingeteam_iss.energy import EnergyAccumulator
from custom_components.ingeteam_iss.profiles import (
    DEFAULT_PROFILE_ID,
    UnsupportedProfileError,
    get_profile,
    resolve_profile,
)
from custom_components.ingeteam_iss.sse import SSEEvent

ROOT = Path(__file__).resolve().parents[1]
BASELINE = json.loads(
    (ROOT / "tests/fixtures/profile_baseline_053.json").read_text("utf-8")
)
CAPTURES = {capture["name"]: capture for capture in BASELINE["captures"]}


def _metadata_value(value):
    if hasattr(value, "address") and hasattr(value, "startbit"):
        return {"address": value.address, "startbit": value.startbit}
    return list(value) if isinstance(value, tuple) else value


def test_existing_entries_resolve_only_to_the_validated_profile():
    profile = get_profile()
    assert DEFAULT_PROFILE_ID == profile.id == "tl_m"
    assert get_profile(None) is profile
    assert get_profile("tl_m") is profile
    assert resolve_profile(None, {}) is profile
    for unknown in ("storage_1play", "../tl_m", "some_module:Profile"):
        with pytest.raises(UnsupportedProfileError):
            get_profile(unknown)


def test_known_previous_generation_is_not_given_tl_m_controls():
    previous_generation = {"compatible": [{"firmware": "ABH1002AL"}]}
    for profile_id in (None, "tl_m"):
        with pytest.raises(UnsupportedProfileError):
            resolve_profile(profile_id, previous_generation)


def test_malformed_map_labels_do_not_crash_the_legacy_profile():
    profile = resolve_profile(
        None,
        {
            "holding": [{"add": 58, "start": 0, "tid": []}],
            "langs": {"ENGLISH": {}},
        },
    )
    assert profile.id == "tl_m"


def test_tl_m_configuration_matches_the_053_reference():
    profile = get_profile()
    expected = BASELINE["metadata"]
    for source, attribute in (
        ("sensor", "sensors"),
        ("number", "numbers"),
        ("select", "selects"),
        ("switch", "switches"),
        ("time", "times"),
    ):
        descriptions = getattr(profile, attribute)
        assert len(descriptions) == len(expected[source])
        for description, original in zip(descriptions, expected[source], strict=True):
            actual = {
                key: _metadata_value(getattr(description, key)) for key in original
            }
            assert actual == original, (source, description.key)
    assert [item.payload() for item in profile.holding_ranges] == expected[
        "holding_ranges"
    ]
    assert [item.payload() for item in profile.online_ranges] == expected[
        "online_ranges"
    ]
    assert {str(key): value for key, value in profile.alarm_fields.items()} == expected[
        "alarm_fields"
    ]
    assert list(profile.platforms) == expected["platforms"]


def test_profile_definitions_are_immutable_and_decoders_are_per_entry():
    profile = get_profile()
    with pytest.raises(FrozenInstanceError):
        profile.id = "changed"
    with pytest.raises(TypeError):
        profile.alarm_fields[10] = "changed"
    with pytest.raises(FrozenInstanceError):
        profile.holding_ranges[0].address = 999
    payload = profile.holding_ranges[0].payload()
    payload["address"] = 999
    assert profile.holding_ranges[0].payload()["address"] != 999
    assert profile.create_decoder() is not profile.create_decoder()


@pytest.mark.parametrize(
    "case",
    BASELINE["writes"],
    ids=lambda item: f"{item['platform']}:{item['key']}:{item['values']}",
)
async def test_tl_m_write_requests_match_053_without_contacting_a_device(case):
    """Every original control keeps its address/bit, bounds and field payload."""
    api = IngeteamApi(
        None, "127.0.0.1", "profile-test", "fixture-password", device_id=7
    )
    requests = []

    async def request(method, path, payload=None):
        requests.append({"method": method, "path": path, "payload": payload})
        return {"result": [{"success": True}]}

    api._request_json = request
    await api.async_write_holding_values([tuple(value) for value in case["values"]])
    assert requests == [case["request"]]


async def test_tl_m_http_read_payloads_match_053_without_contacting_a_device():
    api = IngeteamApi(
        None, "127.0.0.1", "profile-test", "fixture-password", device_id=7
    )
    requests = []

    async def request(method, path, payload=None):
        requests.append({"method": method, "path": path, "payload": payload})
        return {"Data": []}

    api._request_json = request
    await api.async_read_holding()
    await api.async_read_online()
    assert requests == [
        {
            "method": "POST",
            "path": "/inverter/holding/read/7",
            "payload": BASELINE["metadata"]["holding_ranges"],
        },
        {
            "method": "POST",
            "path": "/inverter/online/read/7",
            "payload": BASELINE["metadata"]["online_ranges"],
        },
    ]


@pytest.mark.parametrize("capture", BASELINE["captures"], ids=lambda item: item["name"])
def test_tl_m_decoder_matches_original_real_and_synthetic_captures(capture):
    decoder = get_profile().create_decoder()
    event = SSEEvent(capture["event"], capture["data"])
    assert decoder.decode(event, 100.0) == capture["expected"]


@pytest.mark.parametrize(
    "case", BASELINE["states"], ids=lambda item: f"{item['key']}:{item['data']}"
)
def test_tl_m_automation_states_match_053(case):
    profile = get_profile()
    states = {
        item.key: item for item in (*profile.operating_states, *profile.flow_states)
    }
    data = dict(case["data"])
    if "online" in data:
        data["online"] = {
            (address, bit): value for address, bit, value in data["online"]
        }
    assert states[case["key"]].evaluator(data) == case["expected"]


@pytest.mark.parametrize("trace", BASELINE["traces"], ids=lambda item: item["name"])
def test_tl_m_energy_and_calendar_replay_match_053_exactly(trace):
    """Check closure publication order as well as every persisted subtotal.

    The fixed clocks cross the early hourly cutoff, local day/month/year,
    Madrid's two DST transitions, missing channels, gaps, disconnection and
    restore. Restores must not recover the previous power/time anchors.
    """
    decoder = get_profile().create_decoder()
    energy = EnergyAccumulator()
    calendar = CalendarEnergy(ZoneInfo(trace["zone"]))
    for record in trace["records"]:
        operation = record["operation"]
        second = operation["second"]
        if operation["kind"] == "sample":
            capture = CAPTURES[operation["capture"]]
            sample = decoder.decode(SSEEvent(capture["event"], capture["data"]), second)
            energy.update(sample, second)
            calendar.update(sample, second, trace["start"] + second)
        elif operation["kind"] == "tick":
            calendar.tick(trace["start"] + second)
        elif operation["kind"] == "break":
            decoder.reset()
            energy.break_interval()
            calendar.break_interval()
        elif operation["kind"] == "restore":
            totals, saved = energy.totals.copy(), calendar.dump()
            decoder = get_profile().create_decoder()
            energy = EnergyAccumulator()
            calendar = CalendarEnergy(ZoneInfo(trace["zone"]))
            energy.restore(totals)
            calendar.restore(saved)
        assert energy.totals == record["energy"], operation
        assert calendar.dump() == record["calendar"], operation
        assert [list(update) for update in calendar.take_period_updates()] == record[
            "period_updates"
        ], operation


@pytest.mark.parametrize(
    "filename",
    ("sensor.py", "number.py", "select.py", "switch.py", "time.py", "binary_sensor.py"),
)
def test_platforms_do_not_import_a_specific_model(filename):
    """A model extension must not require a platform-specific import or branch."""
    path = ROOT / "custom_components/ingeteam_iss" / filename
    tree = ast.parse(path.read_text("utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert "tl_m" not in (node.module or ""), filename
        elif isinstance(node, ast.Import):
            assert all("tl_m" not in alias.name for alias in node.names), filename
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            assert node.value not in ("tl_m", "storage_1play"), filename
