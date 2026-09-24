"""Integration tests with real HA Core and an isolated local HTTP simulator."""

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
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import frame
from homeassistant.helpers.translation import async_get_translations

from custom_components.ingeteam_iss.api import IngeteamApiError
from custom_components.ingeteam_iss.config_flow import _user_schema
from custom_components.ingeteam_iss.const import DOMAIN, SSE_PATH
from custom_components.ingeteam_iss.values import bounded_integer, scaled_sum

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = json.loads((ROOT / "tests/fixtures/scenarios.json").read_text())


async def wait_until(check, timeout=3):
    async with asyncio.timeout(timeout):
        while not check():
            await asyncio.sleep(0.01)


def event_bytes(payload):
    return ("event: /ems/sse/phases\ndata: " + json.dumps(payload) + "\n\n").encode()


async def emit(system, payload):
    hass, entry, data = system
    before = entry.runtime_data.telemetry.last_event
    await data["sse_queue"].put(event_bytes(payload))
    await wait_until(lambda: entry.runtime_data.telemetry.last_event != before)
    await hass.async_block_till_done()


@pytest_asyncio.fixture
async def system(tmp_path, monkeypatch):
    (tmp_path / "custom_components").symlink_to(
        ROOT / "custom_components", target_is_directory=True
    )
    # Distinct fields in HR132 allow us to catch accidental whole-register writes.
    data = {
        "holding": {
            (86, 0): 22,
            (142, 0): 25,
            (132, 0): 0,
            (132, 12): 1,
            (132, 14): 1,
            (133, 11): 0,
            (133, 12): 1,
            (100, 5): 0,
            (133, 1): 2,
            (100, 10): 1,
            (100, 12): 3,
        },
        "online": {
            (20, 0): 57,
            (19, 0): -100,
            (17, 0): 2500,
            (18, 0): -125,
            (33, 0): 1234,
            (36, 0): 567,
            (78, 0): 321,
            (71, 0): 100,
        },
        "writes": [],
        "online_failure": False,
        "write_result": None,
        "sse_queue": asyncio.Queue(),
        "sse_connections": 0,
        "sse_active": 0,
        "reads": [],
        "sse_initial": {
            "Phases": [
                {
                    "Phase": 4,
                    "pv": 1801,
                    "W": 100,
                    "cons": 321,
                    "soc": 57,
                    "vbat": 250,
                    "PacCharge": 100,
                    "PacDischarge": 0,
                    "StatusBat": 2,
                }
            ]
        },
    }
    for address in (58, 59, 60, 63, 119, 123, 125, 126, 127, 128, 129, 130):
        data["holding"][address, 0] = 50
    for address in (61, 62, 64, 65, 117, 118, 120, 121):
        data["holding"][address, 0] = 30
        data["holding"][address, 8] = 8

    async def handle(request):
        if request.headers["Authorization"] != "Basic dGVzdGVyOnRlc3QtcGFzc3dvcmQ=":
            raise web.HTTPUnauthorized()
        if request.path.startswith("/inverter/map/"):
            return web.json_response(data.get("map", {}))
        if request.path == "/system/info/device":
            return web.json_response(
                {
                    "SerialNumber": data.get("serial", "TEST-ISS"),
                    "HwType": "ABH0101",
                    "ApiVersion": 102,
                }
            )
        if request.path == SSE_PATH:
            assert request.headers["Accept"] == "text/event-stream"
            data["sse_connections"] += 1
            if data.get("sse_status"):
                return web.Response(status=data["sse_status"])
            if data.get("sse_bad_content_type"):
                return web.Response(text="not SSE")
            response = web.StreamResponse(headers={"Content-Type": "text/event-stream"})
            await response.prepare(request)
            data["sse_active"] += 1
            try:
                if data["sse_initial"] is not None:
                    await response.write(event_bytes(data["sse_initial"]))
                while (
                    request.transport is not None and not request.transport.is_closing()
                ):
                    try:
                        message = await asyncio.wait_for(data["sse_queue"].get(), 0.05)
                    except TimeoutError:
                        continue
                    if message is None:
                        break
                    await response.write(message)
            except ConnectionResetError:
                pass
            finally:
                data["sse_active"] -= 1
            return response
        assert request.path.endswith("/1"), request.path
        assert request.content_type == "application/x-www-form-urlencoded"
        body = json.loads(await request.text())
        if "/write/" in request.path:
            data["writes"].append(body)
            if data["write_result"] is not None:
                return web.json_response(data["write_result"])
            if not data.get("ignore_writes"):
                for v in body["Values"]:
                    data["holding"][v["address"], v["startbit"]] = v["value"]
            return web.json_response(
                {
                    "result": [
                        {"address": a, "length": 1, "success": True}
                        for a in sorted({v["address"] for v in body["Values"]})
                    ]
                }
            )
        source = "online" if "/online/" in request.path else "holding"
        data["reads"].append((source, body))
        if source == "holding" and data.get("holding_failure"):
            raise web.HTTPServiceUnavailable()
        if source == "online" and data["online_failure"]:
            raise web.HTTPServiceUnavailable()
        blocks = [
            {
                "data": [
                    {"address": a, "startbit": b, "value": v}
                    for (a, b), v in data[source].items()
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
    hass.config.language = "es"
    hass.config.time_zone = "UTC"
    loader.async_setup(hass)
    frame.async_setup(hass)
    await ar.async_load(hass)
    # Core 2026.9 separates registry setup from loading. The integration itself
    # uses the registry initialized by HA; this is simulator bootstrapping only.
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
        version=1,
        minor_version=1,
        title="Test Ingeteam",
        data={
            "host": "127.0.0.1",
            "port": port,
            "username": "tester",
            "password": "test-password",
            "device_id": 1,
        },
        options={},
        source="user",
        unique_id="TEST-ISS",
        discovery_keys=MappingProxyType({}),
        subentries_data=[],
    )
    session = ClientSession()
    monkeypatch.setattr(
        "custom_components.ingeteam_iss.async_get_clientsession", lambda _: session
    )
    monkeypatch.setattr(
        "custom_components.ingeteam_iss.config_flow.async_get_clientsession",
        lambda _: session,
    )
    await hass.config_entries.async_add(entry)
    await hass.async_block_till_done()
    assert entry.state == ConfigEntryState.LOADED
    await wait_until(lambda: entry.runtime_data.telemetry.connected)
    yield hass, entry, data
    if entry.state == ConfigEntryState.LOADED:
        await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_stop(force=True)
    await session.close()
    await runner.cleanup()


def entity_id(hass, domain, key):
    return er.async_get(hass).async_get_entity_id(domain, DOMAIN, f"TEST-ISS_{key}")


@pytest.mark.asyncio
async def test_setup_grouping_translated_names_and_pv(system):
    hass, entry, data = system
    entities = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    assert len(entities) == 70
    groups = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    assert len(groups) == 6
    battery = next(d for d in groups if (DOMAIN, "TEST-ISS_battery") in d.identifiers)
    assert battery.name == "Ingeteam ISS · Gestión de batería"
    for domain, key in [
        ("number", "bms_max_charge_current"),
        ("number", "bms_max_on_grid_discharge_current"),
        ("switch", "bms_soc_calibration"),
    ]:
        ent = er.async_get(hass).async_get(entity_id(hass, domain, key))
        assert ent.device_id == battery.id
        if domain == "number":
            state = hass.states.get(ent.entity_id)
            assert state.attributes["mode"] == "slider"
            assert (
                state.attributes["min"],
                state.attributes["max"],
                state.attributes["step"],
            ) == (0, 66, 1)
    pv = hass.states.get(entity_id(hass, "sensor", "pv_total_power"))
    assert pv.state == "1801"
    assert pv.attributes["unit_of_measurement"] == "W"
    assert pv.attributes["state_class"] == "measurement"
    assert pv.attributes["friendly_name"].endswith("Potencia FV total")
    assert data["writes"] == []  # Installation must not change inverter settings.


@pytest.mark.asyncio
async def test_bms_writes_and_bit_preservation(system):
    hass, entry, data = system
    for key, address, value in [
        ("bms_max_charge_current", 86, 15),
        ("bms_max_on_grid_discharge_current", 142, 18),
    ]:
        eid = entity_id(hass, "number", key)
        await hass.services.async_call(
            "number", "set_value", {"entity_id": eid, "value": value}, blocking=True
        )
        assert data["writes"][-1]["Values"] == [
            {"address": address, "startbit": 0, "value": value}
        ]
        assert float(hass.states.get(eid).state) == value
    eid = entity_id(hass, "switch", "bms_soc_calibration")
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": eid}, blocking=True
    )
    assert data["writes"][-1]["Values"] == [{"address": 132, "startbit": 0, "value": 1}]
    assert data["holding"][132, 12] == 1 and data["holding"][132, 14] == 1
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": eid}, blocking=True
    )
    assert data["holding"][132, 0] == 0


@pytest.mark.asyncio
async def test_pv_missing_data_and_failure_recovery(system):
    hass, entry, data = system
    eid = entity_id(hass, "sensor", "pv_2_power")
    data["online"].pop((36, 0))
    await entry.runtime_data.async_refresh()
    assert hass.states.get(eid).state == "unavailable"
    data["online"][36, 0] = 0
    data["online"][33, 0] = 0
    await entry.runtime_data.async_refresh()
    assert hass.states.get(eid).state == "0"
    data["online_failure"] = True
    await entry.runtime_data.async_refresh()
    assert hass.states.get(eid).state == "unavailable"
    assert hass.states.get(entity_id(hass, "sensor", "pv_total_power")).state == "1801"
    assert (
        float(
            hass.states.get(entity_id(hass, "number", "bms_max_charge_current")).state
        )
        == 22
    )
    data["online_failure"] = False
    data["online"][36, 0] = 75
    await entry.runtime_data.async_refresh()
    assert hass.states.get(eid).state == "75"


@pytest.mark.asyncio
async def test_schedule_write_and_select(system):
    hass, entry, data = system
    eid = entity_id(hass, "time", "grid_charge_schedule_1_start")
    await hass.services.async_call(
        "time", "set_value", {"entity_id": eid, "time": "12:45:00"}, blocking=True
    )
    assert data["writes"][-1]["Values"] == [
        {"address": 117, "startbit": 0, "value": 45},
        {"address": 117, "startbit": 8, "value": 12},
    ]
    eid = entity_id(hass, "select", "grid_charge_schedule_1_mode")
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": eid, "option": "weekdays"},
        blocking=True,
    )
    assert data["writes"][-1]["Values"] == [{"address": 100, "startbit": 5, "value": 2}]


@pytest.mark.asyncio
async def test_reject_invalid_current_and_api_confirmation(system):
    hass, entry, data = system
    eid = entity_id(hass, "number", "bms_max_charge_current")
    for bad in (-1, 67, 12.5):
        with pytest.raises(ServiceValidationError):
            await hass.services.async_call(
                "number", "set_value", {"entity_id": eid, "value": bad}, blocking=True
            )
    assert not data["writes"]
    for reply in ({"result": []}, {"result": [None]}, {"result": [{"success": False}]}):
        data["write_result"] = reply
        with pytest.raises(IngeteamApiError):
            await entry.runtime_data.api.async_write_holding(86, 0, 10)


def test_node_number_box_and_integer_normalization():
    schema = _user_schema()
    key = next(k for k in schema.schema if k.schema == "device_id")
    assert key.default() == 1
    assert schema.schema[key].serialize()["selector"]["number"]["mode"] == "box"
    assert bounded_integer(1.0, 1, 247) == 1
    assert isinstance(bounded_integer(1.0, 1, 247), int)
    for bad in (0, 248, 1.5, float("nan"), float("inf"), True):
        with pytest.raises(ValueError):
            bounded_integer(bad, 1, 247)


@pytest.mark.asyncio
async def test_translations_are_loaded_by_core(system):
    hass, _, _ = system
    for code in ("es", "en", "fr", "de", "it", "pt", "nl", "pl"):
        translations = await async_get_translations(hass, code, "entity", {DOMAIN})
        assert translations[f"component.{DOMAIN}.entity.sensor.pv_total_power.name"]
        translated_devices = await async_get_translations(
            hass, code, "device", {DOMAIN}
        )
        assert translated_devices[f"component.{DOMAIN}.device.battery.name"]
        config = await async_get_translations(hass, code, "config", {DOMAIN})
        assert config[f"component.{DOMAIN}.config.step.user.data.device_id"]


def test_translation_coverage():
    def leaves(d, prefix=""):
        return {
            k
            for a, v in d.items()
            for k in (
                leaves(v, prefix + a + ".") if isinstance(v, dict) else [prefix + a]
            )
        }

    files = list((ROOT / "custom_components/ingeteam_iss/translations").glob("*.json"))
    expected = leaves(json.loads((files[0]).read_text()))
    assert len(files) == 8
    for file in files:
        assert leaves(json.loads(file.read_text())) == expected, file.name
        assert "[%key:" not in file.read_text()


def test_total_pv_validation():
    keys = ((33, 0), (36, 0))
    for missing in (None, "invalid", float("nan"), float("inf"), True):
        assert scaled_sum({keys[0]: 300, keys[1]: missing}, keys) is None
    assert scaled_sum({keys[0]: 100.5, keys[1]: 200.25}, keys) == 300.75


@pytest.mark.asyncio
async def test_mismatched_readback_is_an_error(system):
    hass, entry, data = system
    data["ignore_writes"] = True
    with pytest.raises(HomeAssistantError, match="did not return"):
        await entry.runtime_data.async_write(86, 0, 10)
    eid = entity_id(hass, "number", "bms_max_charge_current")
    assert float(hass.states.get(eid).state) == 22


@pytest.mark.asyncio
async def test_concurrent_writes_each_get_confirmed(system):
    import asyncio

    hass, entry, data = system
    await asyncio.gather(
        entry.runtime_data.async_write(86, 0, 12),
        entry.runtime_data.async_write(142, 0, 19),
    )
    assert len(data["writes"]) == 2
    for key, value in [
        ("bms_max_charge_current", 12),
        ("bms_max_on_grid_discharge_current", 19),
    ]:
        assert float(hass.states.get(entity_id(hass, "number", key)).state) == value


@pytest.mark.parametrize("name", SCENARIOS)
async def test_real_captures_in_core(system, name):
    hass, entry, data = system
    await emit(system, SCENARIOS[name])
    phase = SCENARIOS[name]["Phases"][0]
    for key, value in {
        "pv_total_power": phase["pv"],
        "total_load_power": phase["cons"],
        "grid_import_power": max(phase["W"], 0),
        "grid_export_power": max(-phase["W"], 0),
    }.items():
        assert float(hass.states.get(entity_id(hass, "sensor", key)).state) == value
    for key, field in [
        ("battery_voltage", "vbat"),
        ("battery_soc", "soc"),
        ("battery_charge_power", "PacCharge"),
        ("battery_discharge_power", "PacDischarge"),
    ]:
        state = hass.states.get(entity_id(hass, "sensor", key)).state
        if phase["StatusBat"] == 7:
            assert state == "unavailable"
        else:
            assert float(state) == phase[field]
    current = hass.states.get(entity_id(hass, "sensor", "battery_current")).state
    assert current == ("unavailable" if phase["StatusBat"] == 7 else "-1.25")
    assert (
        hass.states.get(entity_id(hass, "binary_sensor", "sse_connected")).state == "on"
    )
    assert (
        float(
            hass.states.get(entity_id(hass, "number", "bms_max_charge_current")).state
        )
        == 22
    )
    assert data["writes"] == []


async def test_http_failure_does_not_disable_sse(system):
    hass, entry, data = system
    data["holding_failure"] = True
    await entry.runtime_data.async_refresh()
    assert (
        hass.states.get(entity_id(hass, "number", "bms_max_charge_current")).state
        == "unavailable"
    )
    await emit(system, SCENARIOS["self_consumption"])
    assert (
        hass.states.get(entity_id(hass, "sensor", "total_load_power")).state == "3200"
    )
    data["holding_failure"] = False
    await entry.runtime_data.async_refresh()
    assert (
        hass.states.get(entity_id(hass, "number", "bms_max_charge_current")).state
        == "22.0"
    )


async def test_sse_eof_unavailable_reconnect_and_no_extra_http(system):
    hass, entry, data = system
    sse = entry.runtime_data.telemetry
    before = sse.last_event
    http_count = len(data["reads"])
    await data["sse_queue"].put(None)
    await wait_until(lambda: not sse.connected)
    assert sse.last_event == before
    assert sse.last_disconnect is not None
    assert (
        hass.states.get(entity_id(hass, "sensor", "pv_total_power")).state
        == "unavailable"
    )
    assert hass.states.get(entity_id(hass, "sensor", "pv_1_power")).state == "1234"
    assert (
        hass.states.get(entity_id(hass, "number", "bms_max_charge_current")).state
        == "22.0"
    )
    assert (
        hass.states.get(entity_id(hass, "sensor", "pv_energy")).state != "unavailable"
    )
    await wait_until(lambda: sse.connected)
    assert data["sse_connections"] == 2
    assert len(data["reads"]) == http_count
    assert hass.states.get(entity_id(hass, "sensor", "pv_total_power")).state == "1801"


async def test_watchdog_ignores_heartbeats_other_events_and_invalid_json(system):
    hass, entry, data = system
    sse = entry.runtime_data.telemetry
    await sse.async_stop()
    await wait_until(lambda: data["sse_active"] == 0)
    sse.timeout = 0.2
    sse.async_start()
    await wait_until(lambda: sse.connected)
    before = sse.last_event
    for _ in range(5):
        await data["sse_queue"].put(
            b': heartbeat\n\nevent: /ems/sse/stream\ndata: {"Devices": []}\n\nevent: /ems/sse/phases\ndata: invalid\n\n'
        )
        await asyncio.sleep(0.03)
    await wait_until(lambda: not sse.connected)
    assert sse.last_event == before
    assert (
        hass.states.get(entity_id(hass, "binary_sensor", "sse_connected")).state
        == "off"
    )
    await entry.runtime_data.async_write(86, 0, 23)
    assert (
        hass.states.get(entity_id(hass, "number", "bms_max_charge_current")).state
        == "23.0"
    )


async def test_equal_samples_are_fresh_and_http_poll_timer_unchanged(system):
    hass, entry, data = system
    coordinator = entry.runtime_data
    scheduled = coordinator._unsub_refresh
    first = coordinator.telemetry.last_event
    for _ in range(3):
        await emit(system, data["sse_initial"])
    assert coordinator.telemetry.last_event > first
    assert coordinator._unsub_refresh is scheduled
    assert coordinator.telemetry.energy.totals["pv_energy"] > 0


async def test_energy_restored_on_reload_without_reset_or_time_bridge(system):
    hass, entry, data = system
    sse = entry.runtime_data.telemetry
    # Simulate existing precise totals, independent of small wall-clock waits.
    sse.energy.restore({key: 123.123456789 for key in sse.energy.totals})
    original_ids = {
        e.unique_id: e.entity_id
        for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    }
    await hass.config_entries.async_reload(entry.entry_id)
    await wait_until(lambda: entry.runtime_data.telemetry.connected)
    assert entry.runtime_data.telemetry is not sse
    assert entry.runtime_data.telemetry.energy.totals == sse.energy.totals
    assert {
        e.unique_id: e.entity_id
        for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    } == original_ids
    for key in sse.energy.totals:
        state = hass.states.get(entity_id(hass, "sensor", key))
        assert float(state.state) == 123.123457
        assert state.attributes["device_class"] == "energy"
        assert state.attributes["unit_of_measurement"] == "kWh"
        assert state.attributes["state_class"] == "total"
    assert data["writes"] == []


async def test_missing_sse_field_clears_only_its_sensors(system):
    from copy import deepcopy

    hass, entry, data = system
    payload = deepcopy(data["sse_initial"])
    del payload["Phases"][0]["pv"]
    await emit(system, payload)
    assert (
        hass.states.get(entity_id(hass, "sensor", "pv_total_power")).state
        == "unavailable"
    )
    assert (
        hass.states.get(entity_id(hass, "sensor", "external_grid_power")).state == "100"
    )
    assert entry.runtime_data.telemetry.connected


async def test_disabled_diagnostics_and_persistent_energy_group(system):
    hass, entry, data = system
    for key in ("sse_last_event", "sse_last_disconnect"):
        entity = er.async_get(hass).async_get(entity_id(hass, "sensor", key))
        assert entity.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    groups = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    group = next(d for d in groups if (DOMAIN, "TEST-ISS_energy") in d.identifiers)
    assert group.name == "Ingeteam ISS · Energía"


async def test_legacy_entity_identities_are_retained(system):
    hass, entry, data = system
    legacy = json.loads((ROOT / "tests/fixtures/legacy_entity_keys.json").read_text())
    assert sum(len(keys) for keys in legacy.values()) == 40
    for domain, keys in legacy.items():
        for key in keys:
            assert entity_id(hass, domain, key) is not None


async def test_energy_state_throttling_keeps_full_precision(system, monkeypatch):
    from unittest.mock import Mock

    from custom_components.ingeteam_iss.sensor import IngeteamEnergySensor

    hass, entry, data = system
    entity = IngeteamEnergySensor(entry.runtime_data, "pv_energy")
    write = Mock()
    monkeypatch.setattr(entity, "async_write_ha_state", write)
    for _ in range(5):
        entity._handle_coordinator_update()
    assert write.call_count == 1
    entity._last_publish -= 31
    entry.runtime_data.telemetry.energy.totals["pv_energy"] = 1.123456789
    entity._handle_coordinator_update()
    assert write.call_count == 2
    assert entity.native_value == 1.123457
    assert entry.runtime_data.telemetry.energy.totals["pv_energy"] == 1.123456789
    entry.runtime_data.telemetry.async_mark_disconnected()
    entity._handle_coordinator_update()
    assert write.call_count == 3


async def test_periodic_save_is_not_postponed_by_every_event(system, monkeypatch):
    from unittest.mock import Mock

    hass, entry, data = system
    sse = entry.runtime_data.telemetry
    save = Mock()
    sse._stored_data()  # Simulate completion of the save scheduled by the first frame.
    monkeypatch.setattr(sse._store, "async_delay_save", save)
    for _ in range(5):
        sse.async_receive(dict(sse.data))
    assert save.call_count == 1
    assert save.call_args.args[1] == 60
    persisted = save.call_args.args[0]()
    assert persisted["totals"] == sse.energy.totals
    assert not sse._save_pending


async def test_reconfigure_preserves_identity_password_counters_and_single_connection(
    system,
):
    hass, entry, data = system
    before = {
        e.unique_id: e.entity_id
        for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    }
    entry.runtime_data.telemetry.energy.totals["load_energy"] = 123.456
    entry.runtime_data.telemetry.accounting.values["net_import_energy"] = 77.0
    flow = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "reconfigure", "entry_id": entry.entry_id}
    )
    assert flow["step_id"] == "reconfigure"
    result = await hass.config_entries.flow.async_configure(
        flow["flow_id"],
        {
            "host": "localhost",
            "username": "tester",
            "password": "",
            "port": entry.data["port"],
            "device_id": 1,
            "publish_interval": "10",
        },
    )
    assert result["type"] == "abort" and result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    await wait_until(lambda: entry.runtime_data.telemetry.connected)
    assert entry.data["password"] == "test-password"
    assert entry.runtime_data.telemetry.publish_interval == 10
    assert entry.runtime_data.telemetry.energy.totals["load_energy"] == 123.456
    assert entry.runtime_data.telemetry.accounting.values["net_import_energy"] == 77
    after = {
        e.unique_id: e.entity_id
        for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    }
    assert before == after
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1
    await wait_until(lambda: data["sse_active"] == 1)


async def test_reconfigure_rejects_wrong_auth_and_different_inverter(system):
    hass, entry, data = system
    old = dict(entry.data)
    flow = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "reconfigure", "entry_id": entry.entry_id}
    )
    candidate = {k: old[k] for k in ("host", "port", "username", "device_id")}
    result = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {**candidate, "password": "wrong"}
    )
    assert result["errors"]["base"] == "invalid_auth"
    assert dict(entry.data) == old
    data["serial"] = "OTHER-INVERTER"
    result = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {**candidate, "password": ""}
    )
    assert result["errors"]["base"] == "different_device"
    assert dict(entry.data) == old


async def test_reauth_updates_same_entry(system):
    hass, entry, data = system
    flow = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "reauth", "entry_id": entry.entry_id},
        data=dict(entry.data),
    )
    assert flow["step_id"] == "reauth_confirm"
    result = await hass.config_entries.flow.async_configure(
        flow["flow_id"],
        {
            "host": entry.data["host"],
            "username": "tester",
            "password": "test-password",
            "port": entry.data["port"],
            "device_id": 1,
        },
    )
    assert result["reason"] == "reauth_successful"
    await hass.async_block_till_done()
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


@pytest.mark.parametrize("frequency", ["sse", "5", "10", "30"])
async def test_frequency_options_and_all_samples_still_integrated(system, frequency):
    hass, entry, data = system
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(
        flow["flow_id"],
        {"publish_interval": frequency, "scan_interval": 15, "sse_timeout": 30},
    )
    await hass.async_block_till_done()
    sse = entry.runtime_data.telemetry
    await wait_until(lambda: sse.connected)
    assert sse.publish_interval == (0 if frequency == "sse" else int(frequency))
    await wait_until(lambda: data["sse_active"] == 1)
    old_event, frames = sse.last_event, sse.valid_frames
    await emit(system, SCENARIOS["self_consumption"])
    assert sse.last_event != old_event and sse.valid_frames == frames + 1
    assert sse.latest_sample["total_load_power"] == 3200
    state = hass.states.get(entity_id(hass, "sensor", "total_load_power"))
    assert state.state == ("3200" if frequency == "sse" else "321")
    sse._last_publish -= 31
    await emit(system, SCENARIOS["self_consumption"])
    assert hass.states.get(state.entity_id).state == "3200"


async def test_alarm_events_do_not_clear_on_failed_read(system):
    hass, entry, data = system
    received = []
    unsub = hass.bus.async_listen(
        f"{DOMAIN}_alarm", lambda event: received.append(event.data)
    )
    data["online"][73, 0] = 4
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert received[-1]["active"] and received[-1]["bit"] == 2
    assert not received[-1]["documented"]
    data["online_failure"] = True
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert len(received) == 1
    data["online_failure"] = False
    data["online"][73, 0] = 0
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert len(received) == 2 and not received[-1]["active"]
    unsub()


async def test_capabilities_filter_controls_and_reject_unsupported_writes(system):
    hass, entry, data = system
    data["map"] = {"holding": [{"add": 86, "start": 0}], "online": []}
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data.api.supports("holding", 86)
    assert not entry.runtime_data.api.supports("holding", 142)
    with pytest.raises(HomeAssistantError, match="Unsupported"):
        await entry.runtime_data.async_write(142, 0, 12)
    assert not data["writes"]


async def test_diagnostics_do_not_leak_credentials(system):
    from custom_components.ingeteam_iss.diagnostics import (
        async_get_config_entry_diagnostics,
    )

    hass, entry, data = system
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    encoded = json.dumps(diagnostics)
    for private in ("test-password", "tester", "127.0.0.1", "TEST-ISS"):
        assert private not in encoded
    assert diagnostics["telemetry"]["valid_frames"] >= 1


async def test_unload_closes_sse_socket_and_task(system):
    hass, entry, data = system
    sse = entry.runtime_data.telemetry
    await hass.config_entries.async_unload(entry.entry_id)
    await wait_until(lambda: data["sse_active"] == 0)
    assert sse._task is None
    assert not sse.connected


@pytest.mark.parametrize(
    "status,bad_content", [(401, False), (500, False), (None, True)]
)
async def test_sse_http_errors_do_not_disable_controls(system, status, bad_content):
    hass, entry, data = system
    sse = entry.runtime_data.telemetry
    await sse.async_stop()
    await wait_until(lambda: data["sse_active"] == 0)
    data["sse_status"] = status
    data["sse_bad_content_type"] = bad_content
    count = data["sse_connections"]
    sse.async_start()
    await wait_until(lambda: data["sse_connections"] > count)
    assert not sse.connected
    await entry.runtime_data.async_write(86, 0, 24)
    assert (
        hass.states.get(entity_id(hass, "number", "bms_max_charge_current")).state
        == "24.0"
    )
