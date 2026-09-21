"""Config flow for Ingeteam ISS."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)

from .api import IngeteamApi, IngeteamAuthError, IngeteamConnectionError
from .const import (
    CONF_DEVICE_ID,
    CONF_SCAN_INTERVAL,
    CONF_SSE_TIMEOUT,
    DEFAULT_DEVICE_ID,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SSE_TIMEOUT,
    DOMAIN,
)
from .values import bounded_integer


class IngeteamConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the Ingeteam ISS setup flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Configure a local inverter."""
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input = dict(user_input)
            try:
                user_input[CONF_DEVICE_ID] = bounded_integer(
                    user_input.get(CONF_DEVICE_ID, DEFAULT_DEVICE_ID), 1, 247
                )
                user_input[CONF_PORT] = bounded_integer(
                    user_input.get(CONF_PORT, DEFAULT_PORT), 1, 65535
                )
            except ValueError:
                errors["base"] = "invalid_connection_settings"
                return self.async_show_form(
                    step_id="user", data_schema=_user_schema(), errors=errors
                )
            host = user_input[CONF_HOST].strip()
            api = IngeteamApi(
                async_get_clientsession(self.hass),
                host,
                user_input[CONF_USERNAME],
                user_input[CONF_PASSWORD],
                port=user_input[CONF_PORT],
                device_id=user_input[CONF_DEVICE_ID],
            )
            try:
                info = await api.async_device_info()
                await api.async_read_holding()
            except IngeteamAuthError:
                errors["base"] = "invalid_auth"
            except IngeteamConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:  # Home Assistant shows a generic setup error.
                errors["base"] = "unknown"
            else:
                serial = str(info.get("SerialNumber") or host)
                await self.async_set_unique_id(serial)
                self._abort_if_unique_id_configured(updates={CONF_HOST: host})
                user_input[CONF_HOST] = host
                return self.async_create_entry(
                    title=f"Ingeteam ISS {serial}", data=user_input
                )

        return self.async_show_form(
            step_id="user", data_schema=_user_schema(), errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> IngeteamOptionsFlow:
        """Return the options flow."""
        return IngeteamOptionsFlow()


def _user_schema() -> vol.Schema:
    """Use a typed number box for node selection, with the usual node 1."""
    return vol.Schema(
        {
            vol.Required(CONF_HOST): str,
            vol.Required(CONF_USERNAME): str,
            vol.Required(CONF_PASSWORD): str,
            vol.Optional(CONF_PORT, default=DEFAULT_PORT): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=65535)
            ),
            vol.Optional(CONF_DEVICE_ID, default=DEFAULT_DEVICE_ID): NumberSelector(
                NumberSelectorConfig(
                    min=1, max=247, step=1, mode=NumberSelectorMode.BOX
                )
            ),
        }
    )


class IngeteamOptionsFlow(config_entries.OptionsFlow):
    """Handle integration options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Configure polling frequency."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SCAN_INTERVAL,
                        default=self.config_entry.options.get(
                            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=5, max=300)),
                    vol.Optional(
                        CONF_SSE_TIMEOUT,
                        default=self.config_entry.options.get(
                            CONF_SSE_TIMEOUT, DEFAULT_SSE_TIMEOUT
                        ),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=10, max=120, step=1, mode=NumberSelectorMode.BOX
                        )
                    ),
                }
            ),
        )
