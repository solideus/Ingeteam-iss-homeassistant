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
    SelectSelector,
    SelectSelectorConfig,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import IngeteamApi, IngeteamAuthError, IngeteamConnectionError
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
    DOMAIN,
)
from .values import bounded_integer


class IngeteamConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the Ingeteam ISS setup flow."""

    VERSION = 2

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
                holding = await api.async_read_holding()
                if not holding:
                    raise IngeteamConnectionError(
                        "No supported inverter registers returned"
                    )
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
                user_input["identity"] = serial
                if info.get("SerialNumber"):
                    user_input["device_serial"] = str(info["SerialNumber"])
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

    async def async_step_reconfigure(self, user_input=None):
        """Validate before changing an existing entry; never replace its identity."""
        return await self._edit_connection("reconfigure", user_input)

    async def async_step_reauth(self, entry_data):
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        return await self._edit_connection("reauth_confirm", user_input)

    async def _edit_connection(self, step, user_input):
        entry = (
            self._get_reconfigure_entry()
            if step == "reconfigure"
            else self._get_reauth_entry()
        )
        errors = {}
        defaults = dict(entry.data)
        if user_input is not None:
            candidate = {**entry.data, **user_input}
            candidate[CONF_PASSWORD] = (
                user_input.get(CONF_PASSWORD) or entry.data[CONF_PASSWORD]
            )
            candidate[CONF_HOST] = candidate[CONF_HOST].strip()
            try:
                candidate[CONF_PORT] = bounded_integer(
                    candidate.get(CONF_PORT, DEFAULT_PORT), 1, 65535
                )
                candidate[CONF_DEVICE_ID] = bounded_integer(
                    candidate.get(CONF_DEVICE_ID, 1), 1, 247
                )
                api = IngeteamApi(
                    async_get_clientsession(self.hass),
                    candidate[CONF_HOST],
                    candidate[CONF_USERNAME],
                    candidate[CONF_PASSWORD],
                    port=candidate[CONF_PORT],
                    device_id=candidate[CONF_DEVICE_ID],
                )
                info = await api.async_device_info()
                holding = await api.async_read_holding()
                if not holding:
                    errors["base"] = "unsupported_device"
                elif (entry.data.get("device_serial") or entry.unique_id) not in (
                    None,
                    entry.data[CONF_HOST],
                    str(info.get("SerialNumber")),
                ):
                    errors["base"] = "different_device"
            except IngeteamAuthError:
                errors["base"] = "invalid_auth"
            except IngeteamConnectionError:
                errors["base"] = "cannot_connect"
            except ValueError, UnicodeError:
                errors["base"] = "invalid_connection_settings"
            except Exception:
                errors["base"] = "unknown"
            if not errors:
                candidate["identity"] = (
                    entry.data.get("identity")
                    or entry.unique_id
                    or entry.data[CONF_HOST]
                )
                # The existing entry listener performs exactly one reload.
                if info.get("SerialNumber"):
                    candidate["device_serial"] = str(info["SerialNumber"])
                options = dict(entry.options)
                if CONF_PUBLISH_INTERVAL in user_input:
                    options[CONF_PUBLISH_INTERVAL] = user_input[CONF_PUBLISH_INTERVAL]
                unchanged = candidate == entry.data and options == entry.options
                self.hass.config_entries.async_update_entry(
                    entry, data=candidate, options=options
                )
                if unchanged:
                    await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(
                    reason="reconfigure_successful"
                    if step == "reconfigure"
                    else "reauth_successful"
                )
            defaults.update(user_input)
        fields = {
            vol.Optional(
                CONF_PUBLISH_INTERVAL,
                default=entry.options.get(
                    CONF_PUBLISH_INTERVAL,
                    defaults.get(CONF_PUBLISH_INTERVAL, DEFAULT_PUBLISH_INTERVAL),
                ),
            ): _frequency_selector(),
            vol.Required(CONF_HOST, default=defaults[CONF_HOST]): str,
            vol.Required(CONF_USERNAME, default=defaults[CONF_USERNAME]): str,
            vol.Optional(CONF_PASSWORD): TextSelector(
                TextSelectorConfig(type=TextSelectorType.PASSWORD)
            ),
            vol.Required(CONF_PORT, default=defaults.get(CONF_PORT, 80)): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=65535)
            ),
            vol.Required(
                CONF_DEVICE_ID, default=defaults.get(CONF_DEVICE_ID, 1)
            ): NumberSelector(
                NumberSelectorConfig(
                    min=1, max=247, step=1, mode=NumberSelectorMode.BOX
                )
            ),
        }
        return self.async_show_form(
            step_id=step, data_schema=vol.Schema(fields), errors=errors
        )


def _user_schema() -> vol.Schema:
    """Use a typed number box for node selection, with the usual node 1."""
    return vol.Schema(
        {
            vol.Required(CONF_HOST): str,
            vol.Required(CONF_USERNAME): str,
            vol.Required(CONF_PASSWORD): TextSelector(
                TextSelectorConfig(type=TextSelectorType.PASSWORD)
            ),
            vol.Optional(
                CONF_PUBLISH_INTERVAL, default=DEFAULT_PUBLISH_INTERVAL
            ): _frequency_selector(),
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
                        CONF_PUBLISH_INTERVAL,
                        default=self.config_entry.options.get(
                            CONF_PUBLISH_INTERVAL,
                            self.config_entry.data.get(
                                CONF_PUBLISH_INTERVAL, DEFAULT_PUBLISH_INTERVAL
                            ),
                        ),
                    ): _frequency_selector(),
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


def _frequency_selector():
    return SelectSelector(
        SelectSelectorConfig(
            options=["sse", "5", "10", "30"], translation_key="publish_interval"
        )
    )
