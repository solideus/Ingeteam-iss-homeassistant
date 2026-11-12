"""STORAGE 1Play profile in real HA Core with an isolated HTTP/SSE simulator."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import MappingProxyType

import pytest_asyncio
from aiohttp import ClientSession, web
from homeassistant import loader
from homeassistant.config_entries import ConfigEntries, ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import frame

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
async def play(tmp_path, monkeypatch):
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
            "model": "storage_1play",
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
    await wait_until(lambda: entry.runtime_data.telemetry.connected)
    await hass.async_block_till_done()
    yield hass, entry, data
    if entry.state == ConfigEntryState.LOADED:
        await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_stop(force=True)
    await session.close()


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
        e.unique_id.removeprefix(f"{SERIAL}_")
        for e in entities
        if e.domain in ("number", "switch", "select", "time")
    }
    assert controls == {
        "soc_max",
        "soc_grid",
        "soc_min",
        "max_grid_charge_power",
        "max_grid_injection_power",
        "bms_max_charge_current",
        "battery_charge_priority",
        "battery_backup",
    }
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
    hass, _, data = play
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
    hass, _, data = play
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
        "power_reduction_ratio": "78.8",
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


async def test_stale_iss_entities_are_removed_on_setup(play):
    """Controls and PV strings left by an ISS-profile entry are dropped."""
    hass, entry, _ = play
    registry = er.async_get(hass)
    for domain, key in (("number", "soc_recovery"), ("sensor", "pv_2_power")):
        registry.async_get_or_create(
            domain, DOMAIN, f"{SERIAL}_{key}", config_entry=entry
        )
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    for domain, key in (("number", "soc_recovery"), ("sensor", "pv_2_power")):
        assert registry.async_get_entity_id(domain, DOMAIN, f"{SERIAL}_{key}") is None
    assert registry.async_get_entity_id("sensor", DOMAIN, f"{SERIAL}_battery_soc")
    assert registry.async_get_entity_id("number", DOMAIN, f"{SERIAL}_soc_max")
