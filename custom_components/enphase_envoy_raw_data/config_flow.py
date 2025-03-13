"""Configuration for Enphase Envoy Raw Data Support.

This custom integration registers an enphase_envoy_raw_data integration
that only provides a read_data(endpoint) and send_data(endpoint,data)
action/service. No entities are provided.

!!! SENDING DATA TO AN ENVOY ENDPOINT HAS RISK FOR PROPER OPERATION OF THE ENVOY.
DOING SO IS AT YOUR OWN RISK AND SHOULD ONLY BE DONE FULLY UNDERSTANDING ANY EFFECT OF IT !!!

This integration does not replace the core integration. It can be used next to it
"""

from collections.abc import Mapping
import logging
from typing import Any

from awesomeversion import AwesomeVersion
from pyenphase import AUTH_TOKEN_MIN_VERSION, Envoy, EnvoyError
import voluptuous as vol

from homeassistant.config_entries import (
    SOURCE_REAUTH,
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
)
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.httpx_client import get_async_client
from homeassistant.helpers.typing import VolDictType

from .const import DOMAIN, ENVOY_NAME, INVALID_AUTH_ERRORS, UNIQUE_ID

type OurConfigEntry = ConfigEntry

CONF_SERIAL = "serial"

INSTALLER_AUTH_USERNAME = "installer"

_LOGGER = logging.getLogger(__name__)


async def validate_input(
    hass: HomeAssistant,
    host: str,
    username: str,
    password: str,
    errors: dict[str, str],
    description_placeholders: dict[str, str],
) -> Envoy:
    """Validate the user input allows us to connect."""
    envoy = Envoy(host, get_async_client(hass, verify_ssl=False))
    try:
        await envoy.setup()
        await envoy.authenticate(username=username, password=password)
    except INVALID_AUTH_ERRORS as e:
        errors["base"] = "invalid_auth"
        description_placeholders["reason"] = str(e)
    except EnvoyError as e:
        errors["base"] = "cannot_connect"
        description_placeholders["reason"] = str(e)
    except Exception:
        _LOGGER.exception("Unexpected exception")
        errors["base"] = "unknown"

    return envoy


class EnphaseExtConfigFlow(ConfigFlow, domain=DOMAIN):
    """Enphase Envoy Raw Datas config flow."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize an envoy flow."""
        self.ip_address: str | None = None
        self.username = None
        self.protovers: str | None = None

    @callback
    def _async_generate_schema(self) -> vol.Schema:
        """Generate schema."""
        schema: VolDictType = {}

        if self.ip_address:
            schema[vol.Required(CONF_HOST, default=self.ip_address)] = vol.In(
                [self.ip_address]
            )
        elif self.source != SOURCE_REAUTH:
            schema[vol.Required(CONF_HOST)] = str

        default_username = ""
        if (
            not self.username
            and self.protovers
            and AwesomeVersion(self.protovers) < AUTH_TOKEN_MIN_VERSION
        ):
            default_username = INSTALLER_AUTH_USERNAME

        schema[
            vol.Optional(CONF_USERNAME, default=self.username or default_username)
        ] = str
        schema[vol.Optional(CONF_PASSWORD, default="")] = str

        return vol.Schema(schema)

    def _async_envoy_name(self) -> str:
        """Return the name of the envoy."""
        return (
            f"{ENVOY_NAME} {self.unique_id.replace(UNIQUE_ID, '')}"
            if self.unique_id
            else ENVOY_NAME
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        description_placeholders: dict[str, str] = {}
        host = (user_input or {}).get(CONF_HOST) or self.ip_address or ""

        if user_input is not None:
            envoy = await validate_input(
                self.hass,
                host,
                user_input[CONF_USERNAME],
                user_input[CONF_PASSWORD],
                errors,
                description_placeholders,
            )
            if not errors:
                name = self._async_envoy_name()

                if not self.unique_id:
                    await self.async_set_unique_id(f"{UNIQUE_ID}{envoy.serial_number}")
                    name = self._async_envoy_name()

                if self.unique_id:
                    # If envoy exists in configuration update fields and exit
                    self._abort_if_unique_id_configured(
                        {
                            CONF_HOST: host,
                            CONF_USERNAME: user_input[CONF_USERNAME],
                            CONF_PASSWORD: user_input[CONF_PASSWORD],
                        },
                        error="reauth_successful",
                    )

                # CONF_NAME is still set for legacy backwards compatibility
                return self.async_create_entry(
                    title=name, data={CONF_HOST: host, CONF_NAME: name} | user_input
                )

        if self.unique_id:
            self.context["title_placeholders"] = {
                CONF_SERIAL: self.unique_id.replace(UNIQUE_ID, ""),
                CONF_HOST: host,
            }

        suggested_values: Mapping[str, Any] | None = user_input
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                self._async_generate_schema(), suggested_values
            ),
            description_placeholders=description_placeholders,
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add reconfigure step to allow to manually reconfigure a config entry."""
        reconfigure_entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        description_placeholders: dict[str, str] = {}

        if user_input is not None:
            host: str = user_input[CONF_HOST]
            username: str = user_input[CONF_USERNAME]
            password: str = user_input[CONF_PASSWORD]
            envoy = await validate_input(
                self.hass,
                host,
                username,
                password,
                errors,
                description_placeholders,
            )
            if not errors:
                await self.async_set_unique_id(f"{UNIQUE_ID}{envoy.serial_number}")
                self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(
                    reconfigure_entry,
                    data_updates={
                        CONF_HOST: host,
                        CONF_USERNAME: username,
                        CONF_PASSWORD: password,
                    },
                )

        serial = reconfigure_entry.unique_id.replace(UNIQUE_ID, "") or "-"
        self.context["title_placeholders"] = {
            CONF_SERIAL: serial,
            CONF_HOST: reconfigure_entry.data[CONF_HOST],
        }
        description_placeholders["serial"] = serial

        suggested_values: Mapping[str, Any] = user_input or reconfigure_entry.data
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                self._async_generate_schema(), suggested_values
            ),
            description_placeholders=description_placeholders,
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle configuration by re-auth."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Dialog that informs the user that reauth is required."""
        reauth_entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        description_placeholders: dict[str, str] = {}

        if user_input is not None:
            await validate_input(
                self.hass,
                reauth_entry.data[CONF_HOST],
                user_input[CONF_USERNAME],
                user_input[CONF_PASSWORD],
                errors,
                description_placeholders,
            )
            if not errors:
                return self.async_update_reload_and_abort(
                    reauth_entry,
                    data_updates=user_input,
                )

        serial = reauth_entry.unique_id.replace(UNIQUE_ID, "") or "-"
        self.context["title_placeholders"] = {
            CONF_SERIAL: serial,
            CONF_HOST: reauth_entry.data[CONF_HOST],
        }
        description_placeholders["serial"] = serial
        suggested_values: Mapping[str, Any] = user_input or reauth_entry.data
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=self.add_suggested_values_to_schema(
                self._async_generate_schema(), suggested_values
            ),
            description_placeholders=description_placeholders,
            errors=errors,
        )
