"""STORAGE 1Play profile in real HA Core with an isolated HTTP/SSE simulator."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import MappingProxyType

import pytest
import pytest_asyncio
from aiohttp import ClientSession, web
from homeassistant import loader
from homeassistant.config_entries import ConfigEntries, ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import frame
from homeassistant.helpers import issue_registry as ir

from custom_components.ingeteam_iss.const import DOMAIN, SSE_PATH

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT / "tests/fixtures/storage_1play.json").read_text("utf-8"))
SERIAL = "TEST-1PLAY"


async def wait_until(check, timeout=3):
    async with asyncio.timeout(timeout):
        while not check():
            await asyncio.sleep(0.01)


def event_bytes(name, payload):
    return (f"event: {name}\ndata: " + json.dumps(payload) + "\n\n").encode()


def capture(name):
    """One stream event followed by its phase event, as the inverter sends."""
    return event_bytes("/ems/sse/stream", FIXTURE["sse"][name]["stream"]) + (
        event_bytes("/ems/sse/phases", FIXTURE["sse"][name]["phases"])
    )


@pytest_asyncio.fixture
async def play(tmp_path, monkeypatch, request):
    # "storage_1play" by default; None = entry created before model selection.
    model = getattr(request, "param", "storage_1play")
    (tmp_path / "custom_components").symlink_to(
        ROOT / "custom_components", target_is_directory=True
    )
    data = {
        "online": {(int(a), 0): v for a, v in FIXTURE["online"].items()},
        "holding": {
            tuple(map(int, key.split("."))): value
            for key, value in FIXTURE["holding"].items()
        },
        "reads": [],
        "writes": [],
        "sse_queue": asyncio.Queue(),
    }

    async def handle(request):
        if request.headers["Authorization"] != "Basic dGVzdGVyOnRlc3QtcGFzc3dvcmQ=":
            raise web.HTTPUnauthorized()
        if request.path.startswith("/inverter/map/"):
            return web.json_response(FIXTURE["map"])
        if request.path == "/system/info/device":
            return web.json_response(
                {
                    "SerialNumber": SERIAL,
                    "HwType": "AAX0077",
                    "Version": "AAX1055DC",
                    "ApiVersion": 102,
                }
            )
        if request.path == SSE_PATH:
            response = web.StreamResponse(headers={"Content-Type": "text/event-stream"})
            await response.prepare(request)
            await response.write(capture("night"))
            try:
                while (
                    request.transport is not None and not request.transport.is_closing()
                ):
                    try:
                        message = await asyncio.wait_for(data["sse_queue"].get(), 0.05)
                    except TimeoutError:
                        continue
                    await response.write(message)
            except ConnectionResetError:
                pass
            return response
        body = json.loads(await request.text())
        if "/write/" in request.path:
            data["writes"].append(body)
            for value in body["Values"]:
                data["holding"][value["address"], value["startbit"]] = value["value"]
            return web.json_response(
                {
                    "result": [
                        {"address": v["address"], "length": 1, "success": True}
                        for v in body["Values"]
                    ]
                }
            )
        source = "online" if "/online/" in request.path else "holding"
        data["reads"].append((source, body))
        values = data[source]
        blocks = [
            {
                "data": [
                    {"address": a, "startbit": b, "value": v}
                    for (a, b), v in values.items()
                    if r["address"] <= a < r["address"] + r["length"]
                ]
            }
            for r in body
        ]
        return web.json_response({"Data": blocks})

    app = web.Application()
    app.router.add_route("*", "/{path:.*}", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    hass = HomeAssistant(str(tmp_path))
    hass.config.language = "en"
    hass.config.time_zone = "UTC"
    loader.async_setup(hass)
    frame.async_setup(hass)
    await ar.async_load(hass)
    if hasattr(dr, "async_setup"):
        dr.async_setup(hass)
    await dr.async_load(hass)
    if hasattr(er, "async_setup"):
        er.async_setup(hass)
    await er.async_load(hass)
    hass.config_entries = ConfigEntries(hass, {})
    await hass.config_entries.async_initialize()
    entry = ConfigEntry(
        domain=DOMAIN,
        version=2,
        minor_version=1,
        title="Test 1Play",
        data={
            "host": "127.0.0.1",
            "port": port,
            "username": "tester",
            "password": "test-password",
            "device_id": 1,
            "identity": SERIAL,
            **({"model": model} if model else {}),
        },
        options={},
        source="user",
        unique_id=SERIAL,
        discovery_keys=MappingProxyType({}),
        subentries_data=[],
    )
    session = ClientSession()
    monkeypatch.setattr(
        "custom_components.ingeteam_iss.async_get_clientsession", lambda _: session
    )
    await hass.config_entries.async_add(entry)
    await hass.async_block_till_done()
    assert entry.state == ConfigEntryState.LOADED
    if model == "storage_1play":
        await wait_until(lambda: entry.runtime_data.telemetry.connected)
    await hass.async_block_till_done()
    yield hass, entry, data
    if entry.state == ConfigEntryState.LOADED:
        await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_stop(force=True)
    await session.close()


CONTROLS = {
    "soc_max",
    "soc_grid",
    "soc_min",
    "max_grid_charge_power",
    "max_grid_injection_power",
    "bms_max_charge_current",
    "battery_charge_priority",
    "battery_backup",
}


async def enable_controls(hass, entry):
    """Experimental controls are disabled by default; enable them for a test."""
    registry = er.async_get(hass)
    for item in er.async_entries_for_config_entry(registry, entry.entry_id):
        if item.domain in ("number", "switch", "select") and item.disabled_by:
            registry.async_update_entity(item.entity_id, disabled_by=None)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    await wait_until(lambda: entry.runtime_data.telemetry.connected)
    await hass.async_block_till_done()


async def emit(hass, entry, data, payload_bytes):
    telemetry = entry.runtime_data.telemetry
    before = (telemetry.last_event, telemetry.discarded_frames)
    await data["sse_queue"].put(payload_bytes)
    await wait_until(
        lambda: (telemetry.last_event, telemetry.discarded_frames) != before
    )
    await hass.async_block_till_done()


def state(hass, domain, key):
    entity_id = er.async_get(hass).async_get_entity_id(
        domain, DOMAIN, f"{SERIAL}_{key}"
    )
    assert entity_id, key
    return hass.states.get(entity_id)


async def test_only_validated_controls_and_no_unrequested_writes(play):
    hass, entry, data = play
    entities = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    controls = {
        e.unique_id.removeprefix(f"{SERIAL}_"): e
        for e in entities
        if e.domain in ("number", "switch", "select", "time")
    }
    assert set(controls) == CONTROLS
    # Experimental controls are registered disabled by default.
    assert all(e.disabled_by is not None for e in controls.values())
    # Holding reads are limited to the validated registers; setup never writes.
    holding_reads = [body for source, body in data["reads"] if source == "holding"]
    assert holding_reads
    expected = [
        {"address": a, "length": 1} for a in (116, 123, 124, 125, 128, 129, 132)
    ]
    assert all(body == expected for body in holding_reads)
    assert data["writes"] == []
    keys = {e.unique_id.removeprefix(f"{SERIAL}_") for e in entities}
    assert "pv_1_power" not in keys and "pv_2_power" not in keys


async def test_soc_max_write_and_readback(play):
    hass, entry, data = play
    await enable_controls(hass, entry)
    assert state(hass, "number", "soc_max").state == "95.0"
    entity_id = state(hass, "number", "soc_max").entity_id
    await hass.services.async_call(
        "number", "set_value", {"entity_id": entity_id, "value": 96}, blocking=True
    )
    assert data["writes"][-1]["Values"] == [
        {"address": 123, "startbit": 0, "value": 96}
    ]
    assert state(hass, "number", "soc_max").state == "96.0"


async def test_1play_settings_write_their_own_registers(play):
    hass, entry, data = play
    await enable_controls(hass, entry)
    assert state(hass, "number", "max_grid_injection_power").state == "6000.0"
    assert state(hass, "number", "bms_max_charge_current").state == "50.0"
    assert state(hass, "switch", "battery_backup").state == "on"
    assert state(hass, "select", "battery_charge_priority").state == "pv_then_grid"
    calls = (
        ("number", "set_value", "max_grid_injection_power", {"value": -1000}),
        ("number", "set_value", "bms_max_charge_current", {"value": 49}),
        ("switch", "turn_off", "battery_backup", {}),
        ("select", "select_option", "battery_charge_priority", {"option": "grid_only"}),
    )
    for domain, service, key, extra in calls:
        entity_id = state(hass, domain, key).entity_id
        await hass.services.async_call(
            domain, service, {"entity_id": entity_id, **extra}, blocking=True
        )
    assert [w["Values"] for w in data["writes"]] == [
        [{"address": 129, "startbit": 0, "value": -1000}],
        [{"address": 116, "startbit": 0, "value": 49}],
        [{"address": 132, "startbit": 1, "value": 0}],
        [{"address": 132, "startbit": 4, "value": 1}],
    ]
    # Bit fields of register 132 are independent.
    assert state(hass, "switch", "battery_backup").state == "off"
    assert state(hass, "select", "battery_charge_priority").state == "grid_only"
    assert data["holding"][132, 5] == FIXTURE["holding"]["132.5"]


async def test_sse_telemetry_with_stream_status(play):
    hass, entry, _ = play
    assert state(hass, "sensor", "total_load_power").state == "1819"
    assert state(hass, "sensor", "external_grid_power").state == "7"
    assert state(hass, "sensor", "battery_soc").state == "15"
    assert state(hass, "sensor", "battery_flow").state == "discharging"
    telemetry = entry.runtime_data.telemetry
    assert telemetry.data["battery_status"] == 1
    assert telemetry.data["inverter_status"] == 3

    before = telemetry.last_event
    await play[2]["sse_queue"].put(capture("solar"))
    await wait_until(lambda: telemetry.last_event != before)
    await hass.async_block_till_done()
    assert state(hass, "sensor", "pv_total_power").state == "2598"
    assert state(hass, "sensor", "battery_flow").state == "charging"
    assert state(hass, "binary_sensor", "pv_active").state == "on"


async def test_online_registers_are_scaled_with_the_map(play):
    hass, _, _ = play
    expected = {
        "battery_current": "17.48",
        "battery_soh": "95",
        "battery_temperature": "35.0",
        "pv_voltage": "342",
        "pv_current": "3.89",
        "grid_frequency": "50.01",
        "ac_loads_power": "4728",
        "heatsink_temperature": "61.6",
    }
    for key, value in expected.items():
        assert float(state(hass, "sensor", key).state) == float(value), key


async def test_states_alarms_and_grid_bit(play):
    hass, entry, _ = play
    assert state(hass, "sensor", "inverter_state").state == "On-grid Mode"
    assert state(hass, "sensor", "battery_state").state == "Discharging"
    assert state(hass, "binary_sensor", "grid_connected").state == "on"
    assert state(hass, "binary_sensor", "alarm_active").state == "off"
    assert state(hass, "sensor", "active_alarms").state == "0"
    assert entry.runtime_data.alarm_coverage_complete


async def test_writes_are_checked_before_any_request(play):
    """Only fields of created controls, inside their range, reach the inverter."""
    hass, entry, data = play
    await enable_controls(hass, entry)
    coordinator = entry.runtime_data
    with pytest.raises(HomeAssistantError, match="Unsupported"):
        await coordinator.async_write(58, 0, 200)  # digital output threshold
    with pytest.raises(HomeAssistantError, match="out of range"):
        await coordinator.async_write(123, 0, 101)
    with pytest.raises(HomeAssistantError, match="Unsupported"):
        # One forbidden field rejects the whole operation.
        await coordinator.async_write_many([(123, 0, 96), (130, 0, 10)])
    assert data["writes"] == []


async def test_writes_are_refused_while_controls_are_disabled(play):
    hass, entry, data = play
    with pytest.raises(HomeAssistantError, match="Unsupported"):
        await entry.runtime_data.async_write(123, 0, 96)
    assert data["writes"] == []


@pytest.mark.parametrize("play", [None, "iss"], indirect=True)
async def test_tl_m_profile_on_a_1play_map_blocks_controls_and_writes(play):
    """Old entries without model and a wrong selection are both caught."""
    hass, entry, data = play
    coordinator = entry.runtime_data
    assert coordinator.profile_conflict
    assert "holding 58.0" in coordinator.profile_conflict
    entities = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    assert not [
        e for e in entities if e.domain in ("number", "switch", "select", "time")
    ]
    with pytest.raises(HomeAssistantError, match="does not match"):
        await coordinator.async_write(58, 0, 200)
    assert data["writes"] == []
    issue = ir.async_get(hass).async_get_issue(
        DOMAIN, f"profile_mismatch_{entry.entry_id}"
    )
    assert issue is not None and issue.translation_key == "profile_mismatch"


async def test_reconfigure_rejects_a_model_that_contradicts_the_map(play, monkeypatch):
    hass, entry, data = play
    session = ClientSession()
    monkeypatch.setattr(
        "custom_components.ingeteam_iss.config_flow.async_get_clientsession",
        lambda _: session,
    )
    try:
        flow = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "reconfigure", "entry_id": entry.entry_id}
        )
        result = await hass.config_entries.flow.async_configure(
            flow["flow_id"],
            {
                "model": "iss",
                "host": entry.data["host"],
                "username": "tester",
                "password": "",
                "port": entry.data["port"],
                "device_id": 1,
            },
        )
    finally:
        await session.close()
    assert result["errors"] == {"base": "model_mismatch"}
    assert entry.data["model"] == "storage_1play"


async def test_entities_are_kept_with_their_customisations(play):
    """Unsupported entities are not removed; they just get no control."""
    hass, entry, data = play
    registry = er.async_get(hass)
    for domain, key in (("number", "soc_recovery"), ("sensor", "pv_2_power")):
        item = registry.async_get_or_create(
            domain, DOMAIN, f"{SERIAL}_{key}", config_entry=entry
        )
        registry.async_update_entity(item.entity_id, name=f"Mine {key}")
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    for domain, key in (("number", "soc_recovery"), ("sensor", "pv_2_power")):
        entity_id = registry.async_get_entity_id(domain, DOMAIN, f"{SERIAL}_{key}")
        assert entity_id is not None
        assert registry.async_get(entity_id).name == f"Mine {key}"
    with pytest.raises(HomeAssistantError, match="Unsupported"):
        await entry.runtime_data.async_write(130, 0, 10)
    assert data["writes"] == []


def stream_with(name, **changes):
    payload = json.loads(json.dumps(FIXTURE["sse"][name]["stream"]))
    payload["Devices"][0].update(changes)
    return event_bytes("/ems/sse/stream", payload)


async def test_battery_not_configured_withdraws_battery_readings(play):
    hass, entry, data = play
    assert state(hass, "sensor", "battery_soc").state == "15"
    await emit(
        hass,
        entry,
        data,
        stream_with("night", StatusBat=7)
        + event_bytes("/ems/sse/phases", FIXTURE["sse"]["night"]["phases"]),
    )
    for key in ("battery_soc", "battery_power", "battery_discharge_power"):
        assert state(hass, "sensor", key).state == "unavailable", key
    assert state(hass, "sensor", "battery_flow").state == "not_available"
    # Grid and load readings are unaffected.
    assert state(hass, "sensor", "total_load_power").state == "1819"


async def test_stale_stream_status_withdraws_battery_readings(play):
    hass, entry, data = play
    telemetry = entry.runtime_data.telemetry
    telemetry._stream_time -= telemetry.timeout + 1
    await emit(
        hass,
        entry,
        data,
        event_bytes("/ems/sse/phases", FIXTURE["sse"]["night"]["phases"]),
    )
    assert telemetry.data["battery_status"] is None
    assert state(hass, "sensor", "battery_soc").state == "unavailable"
    assert state(hass, "sensor", "total_load_power").state == "1819"


async def test_duplicated_phase_is_rejected(play):
    hass, entry, data = play
    telemetry = entry.runtime_data.telemetry
    payload = json.loads(json.dumps(FIXTURE["sse"]["night"]["phases"]))
    payload["Phases"][1] = dict(payload["Phases"][0])  # phase 1 twice
    frames = telemetry.valid_frames
    await emit(hass, entry, data, event_bytes("/ems/sse/phases", payload))
    assert telemetry.valid_frames == frames
    assert state(hass, "sensor", "total_load_power").state == "1819"
