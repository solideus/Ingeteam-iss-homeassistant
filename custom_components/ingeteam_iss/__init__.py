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
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import IngeteamApi, IngeteamApiError, IngeteamAuthError
from .const import (
    CONF_DEVICE_ID,
    CONF_SCAN_INTERVAL,
    CONF_SSE_TIMEOUT,
    DEFAULT_DEVICE_ID,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SSE_TIMEOUT,
    PLATFORMS,
)
from .coordinator import IngeteamCoordinator
from .entity import inverter_device_info

type IngeteamConfigEntry = ConfigEntry[IngeteamCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: IngeteamConfigEntry) -> bool:
    """Set up Ingeteam ISS from a config entry."""
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
        sse_timeout=entry.options.get(CONF_SSE_TIMEOUT, DEFAULT_SSE_TIMEOUT),
    )
    try:
        coordinator.device_info = await api.async_device_info()
    except IngeteamAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except IngeteamApiError as err:
        raise ConfigEntryNotReady(str(err)) from err
    await coordinator.async_config_entry_first_refresh()
    coordinator.telemetry.device_info = coordinator.device_info
    await coordinator.telemetry.async_load_energy()
    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, **inverter_device_info(coordinator)
    )
    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(
        hass.bus.async_listen_once(
            EVENT_HOMEASSISTANT_STOP, coordinator.telemetry.async_stop
        )
    )
    coordinator.telemetry.async_start()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: IngeteamConfigEntry) -> bool:
    """Unload a config entry."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    await entry.runtime_data.telemetry.async_stop()
    return True


async def _async_update_listener(
    hass: HomeAssistant, entry: IngeteamConfigEntry
) -> None:
    """Reload after changing integration options."""
    await hass.config_entries.async_reload(entry.entry_id)
