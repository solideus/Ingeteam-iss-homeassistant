"""Ingeteam ISS local integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USERNAME,
    EVENT_HOMEASSISTANT_STOP,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

from .api import IngeteamApi, IngeteamApiError, IngeteamAuthError
from .const import (
    CONF_DEVICE_ID,
    CONF_PUBLISH_INTERVAL,
    CONF_SCAN_INTERVAL,
    CONF_SSE_TIMEOUT,
    DEFAULT_DEVICE_ID,
    DEFAULT_PORT,
    DEFAULT_PUBLISH_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SSE_TIMEOUT,
)
from .coordinator import IngeteamCoordinator
from .entity import inverter_device_info
from .models import CONF_MODEL, CONTROL_DOMAINS, MODEL_ISS

type IngeteamConfigEntry = ConfigEntry[IngeteamCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: IngeteamConfigEntry) -> bool:
    """Set up Ingeteam ISS from a config entry."""
    time_zone = await dt_util.async_get_time_zone(hass.config.time_zone)
    if time_zone is None:
        raise ConfigEntryNotReady("Unable to resolve the configured time zone")
    api = IngeteamApi(
        async_get_clientsession(hass),
        entry.data[CONF_HOST],
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
        port=entry.data.get(CONF_PORT, DEFAULT_PORT),
        device_id=entry.data.get(CONF_DEVICE_ID, DEFAULT_DEVICE_ID),
    )
    coordinator = IngeteamCoordinator(
        hass,
        api,
        entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        config_entry=entry,
        time_zone=time_zone,
        sse_timeout=entry.options.get(CONF_SSE_TIMEOUT, DEFAULT_SSE_TIMEOUT),
        # Entries created before model selection keep the ISS behaviour.
        model=entry.data.get(CONF_MODEL, MODEL_ISS),
    )
    coordinator.telemetry.publish_interval = float(
        entry.options.get(
            CONF_PUBLISH_INTERVAL,
            entry.data.get(CONF_PUBLISH_INTERVAL, DEFAULT_PUBLISH_INTERVAL),
        ).replace("sse", "0")
    )
    try:
        coordinator.device_info = await api.async_device_info()
        await api.async_load_capabilities()
    except IngeteamAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except IngeteamApiError as err:
        raise ConfigEntryNotReady(str(err)) from err
    coordinator.identity = (
        entry.data.get("identity")
        or entry.unique_id
        or coordinator.device_info.get("SerialNumber")
        or api.host
    )
    coordinator.telemetry.identity = coordinator.identity
    await coordinator.async_config_entry_first_refresh()
    coordinator.telemetry.device_info = coordinator.device_info
    await coordinator.telemetry.async_load_energy()
    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, **inverter_device_info(coordinator)
    )
    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    _async_remove_unsupported_entities(hass, entry, coordinator)
    await hass.config_entries.async_forward_entry_setups(
        entry, coordinator.profile.platforms
    )
    entry.async_on_unload(
        hass.bus.async_listen_once(
            EVENT_HOMEASSISTANT_STOP, coordinator.telemetry.async_stop
        )
    )
    coordinator.telemetry.async_start()
    return True


def _async_remove_unsupported_entities(
    hass: HomeAssistant, entry: ConfigEntry, coordinator: IngeteamCoordinator
) -> None:
    """Drop entities a restricted profile never creates (e.g. ISS controls).

    They would otherwise stay registered as unavailable controls that, on a
    STORAGE 1Play, point at registers with a different meaning.
    """
    profile = coordinator.profile
    if profile.control_keys is None and not profile.retired_keys:
        return  # The ISS profile keeps its full, original entity set.
    registry = er.async_get(hass)
    prefix = f"{coordinator.identity}_"
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        key = entity.unique_id.removeprefix(prefix)
        unsupported_control = (
            entity.domain in CONTROL_DOMAINS
            and profile.control_keys is not None
            and key not in profile.control_keys
        )
        if (
            entity.domain not in profile.platforms
            or unsupported_control
            or key in profile.retired_keys
        ):
            registry.async_remove(entity.entity_id)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Keep the 0.4.0 identity and energy storage key across configuration edits."""
    if entry.version > 2:
        return False
    if entry.version == 1:
        data = {**entry.data, "identity": entry.unique_id or entry.data[CONF_HOST]}
        data.setdefault(CONF_PUBLISH_INTERVAL, DEFAULT_PUBLISH_INTERVAL)
        hass.config_entries.async_update_entry(entry, data=data, version=2)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: IngeteamConfigEntry) -> bool:
    """Unload a config entry."""
    platforms = entry.runtime_data.profile.platforms
    if not await hass.config_entries.async_unload_platforms(entry, platforms):
        return False
    await entry.runtime_data.telemetry.async_stop()
    return True


async def _async_update_listener(
    hass: HomeAssistant, entry: IngeteamConfigEntry
) -> None:
    """Reload after changing integration options."""
    await hass.config_entries.async_reload(entry.entry_id)
