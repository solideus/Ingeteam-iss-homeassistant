"""Profile selection, migration and extensions through the actual HA services."""

from dataclasses import replace
from types import MappingProxyType
from unittest.mock import Mock

import pytest
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.data_entry_flow import InvalidData
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from test_integration import entity_id, wait_until
from test_integration import system as system

from custom_components.ingeteam_iss import profiles
from custom_components.ingeteam_iss.api import IngeteamApiError
from custom_components.ingeteam_iss.const import DOMAIN, SSE_PHASE_EVENT, Register
from custom_components.ingeteam_iss.profiles.base import ReadRange


@pytest.mark.parametrize(
    "explicit", [False, True], ids=["legacy-default", "explicit-tl-m"]
)
async def test_legacy_and_explicit_profile_preserve_ids_reads_names_and_totals(
    system, explicit
):
    hass, entry, data = system
    registry = er.async_get(hass)
    original = {
        item.unique_id: item.entity_id
        for item in er.async_entries_for_config_entry(registry, entry.entry_id)
    }
    assert len(original) == 70
    control_id = entity_id(hass, "number", "soc_max")
    registry.async_update_entity(
        control_id, name="My battery limit", icon="mdi:solar-power"
    )
    entry.runtime_data.telemetry.energy.totals["load_energy"] = 123.456789123
    entry.runtime_data.telemetry.accounting.values["net_import_energy"] = 77.25
    if explicit:
        await hass.config_entries.async_unload(entry.entry_id)
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, "profile": "tl_m"}
        )
        assert await hass.config_entries.async_setup(entry.entry_id)
    else:
        assert "profile" not in entry.data
        assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    await wait_until(lambda: entry.runtime_data.telemetry.connected)
    assert entry.runtime_data.profile.id == "tl_m"
    assert {
        item.unique_id: item.entity_id
        for item in er.async_entries_for_config_entry(registry, entry.entry_id)
    } == original
    assert registry.async_get(control_id).name == "My battery limit"
    assert registry.async_get(control_id).icon == "mdi:solar-power"
    assert entry.runtime_data.telemetry.energy.totals["load_energy"] == 123.456789123
    assert entry.runtime_data.telemetry.accounting.values["net_import_energy"] == 77.25
    profile = profiles.get_profile()
    expected = {
        "holding": [item.payload() for item in profile.holding_ranges],
        "online": [item.payload() for item in profile.online_ranges],
    }
    assert data["reads"]
    assert all(body == expected[source] for source, body in data["reads"])
    assert data["writes"] == []


@pytest.mark.parametrize("profile_id", ["unknown", "storage_1play"])
async def test_unknown_profile_setup_fails_before_creating_a_client(
    system, monkeypatch, profile_id
):
    hass, entry, data = system
    await hass.config_entries.async_unload(entry.entry_id)
    make_session = Mock(
        side_effect=AssertionError("No HTTP client should be requested")
    )
    monkeypatch.setattr(
        "custom_components.ingeteam_iss.async_get_clientsession", make_session
    )
    previous_reads = list(data["reads"])
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, "profile": profile_id}
    )
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state != ConfigEntryState.LOADED
    make_session.assert_not_called()
    assert data["reads"] == previous_reads
    assert data["writes"] == []


@pytest.mark.parametrize("kind", ["unknown-profile", "known-other-model-map"])
async def test_initial_form_rejects_unsupported_profile_or_map(system, kind):
    hass, entry, data = system
    if kind == "known-other-model-map":
        data["map"] = {"compatible": [{"firmware": "ABH1002AL"}]}
    previous_reads = list(data["reads"])
    flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    candidate = {
        "host": entry.data["host"],
        "port": entry.data["port"],
        "username": "tester",
        "password": "test-password",
        "device_id": 1,
        "profile": "unknown" if kind == "unknown-profile" else "tl_m",
    }
    if kind == "unknown-profile":
        with pytest.raises(InvalidData):
            await hass.config_entries.flow.async_configure(flow["flow_id"], candidate)
        assert data["reads"] == previous_reads
        assert data["writes"] == []
        return
    result = await hass.config_entries.flow.async_configure(flow["flow_id"], candidate)
    assert result["type"] == "form"
    assert result["errors"] == {"base": "unsupported_profile"}
    assert data["reads"] == previous_reads
    assert data["writes"] == []


@pytest.mark.parametrize("target", ["api", "coordinator"])
async def test_all_invalid_write_fields_are_rejected_before_any_http_request(
    system, target
):
    _, entry, data = system
    writer = (
        entry.runtime_data.api.async_write_holding_values
        if target == "api"
        else entry.runtime_data.async_write_many
    )
    previous_reads = list(data["reads"])
    for values in (
        [(123, 0, 96), (999, 0, 10)],
        [(123, 0, 101)],
        [(132, 13, 1)],
        [(117, 0, 60), (117, 8, 12)],
    ):
        with pytest.raises((HomeAssistantError, IngeteamApiError)):
            await writer(values)
    assert data["reads"] == previous_reads
    assert data["writes"] == []


@pytest.mark.parametrize("read_only", [False, True], ids=["writable", "read-only"])
async def test_registered_extension_profile_does_not_change_tl_m_entry(
    system, monkeypatch, read_only
):
    """A test-only second model uses platform contracts without model branches.

    Registering this model changes no production profile or platform module.
    Its register, decoder and entities are deliberately unlike the TL M's.
    """
    hass, original_entry, data = system
    original = profiles.get_profile()

    class SyntheticDecoder:
        def decode(self, event, now):
            return {"test_power": 999.0} if self.is_sample_event(event) else None

        def is_sample_event(self, event):
            return event.event == SSE_PHASE_EVENT

        def reset(self):
            pass

    extension = replace(
        original,
        id="synthetic_test_only",
        name="Synthetic extension for tests",
        platforms=("sensor",) if read_only else ("sensor", "number"),
        holding_ranges=() if read_only else (ReadRange(200, 1),),
        online_ranges=(ReadRange(201, 1),),
        sensors=(
            replace(
                original.sensors[0],
                key="test_power",
                translation_key=None,
                name="Test power",
            ),
        ),
        numbers=()
        if read_only
        else (
            replace(
                original.numbers[0],
                key="test_limit",
                translation_key=None,
                name="Test limit",
                register=Register(200),
                native_max_value=10,
            ),
        ),
        selects=(),
        switches=(),
        times=(),
        operating_states=(),
        flow_states=(),
        alarm_fields=MappingProxyType({}),
        create_decoder=SyntheticDecoder,
        map_validator=lambda mapping: None,
    )
    monkeypatch.setattr(
        profiles,
        "PROFILES",
        MappingProxyType({**profiles.PROFILES, extension.id: extension}),
    )
    data["holding"][200, 0] = 5
    data["online"][201, 0] = 123
    entry = ConfigEntry(
        domain=DOMAIN,
        version=2,
        minor_version=1,
        title="Synthetic model",
        data={
            **original_entry.data,
            "identity": "TEST-EXTENSION",
            "profile": extension.id,
        },
        options={},
        source="user",
        unique_id="TEST-EXTENSION",
        discovery_keys=MappingProxyType({}),
        subentries_data=[],
    )
    try:
        reads_before = len(data["reads"])
        await hass.config_entries.async_add(entry)
        await hass.async_block_till_done()
        assert entry.state == ConfigEntryState.LOADED
        await wait_until(lambda: entry.runtime_data.telemetry.connected)
        registry = er.async_get(hass)
        control = registry.async_get_entity_id(
            "number", DOMAIN, "TEST-EXTENSION_test_limit"
        )
        sensor = registry.async_get_entity_id(
            "sensor", DOMAIN, "TEST-EXTENSION_test_power"
        )
        assert hass.states.get(sensor).state == "999"
        if read_only:
            assert control is None
            assert all(
                source == "online" for source, body in data["reads"][reads_before:]
            )
            from custom_components.ingeteam_iss.config_flow import (
                _async_validate_connection,
            )

            assert await _async_validate_connection(entry.runtime_data.api)
            with pytest.raises(IngeteamApiError):
                await entry.runtime_data.api.async_write_holding_values([(200, 0, 6)])
            assert data["writes"] == []
        else:
            assert hass.states.get(control).state == "5.0"
        assert original_entry.runtime_data.profile is original
        assert (
            hass.states.get(entity_id(hass, "sensor", "pv_total_power")).state == "1801"
        )
        if not read_only:
            await hass.services.async_call(
                "number", "set_value", {"entity_id": control, "value": 6}, blocking=True
            )
            assert data["writes"][-1]["Values"] == [
                {"address": 200, "startbit": 0, "value": 6}
            ]
        assert original.numbers[0].register.address == 86
        assert (
            entry.runtime_data.telemetry._decoder
            is not original_entry.runtime_data.telemetry._decoder
        )
    finally:
        if entry.state == ConfigEntryState.LOADED:
            await hass.config_entries.async_unload(entry.entry_id)
