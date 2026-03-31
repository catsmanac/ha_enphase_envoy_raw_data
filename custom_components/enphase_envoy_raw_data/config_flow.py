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

import jwt
from pyenphase import Envoy, EnvoyError, EnvoyTokenAuth
import voluptuous as vol

from homeassistant.config_entries import (
    SOURCE_REAUTH,
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
)
from homeassistant.const import (
    CONF_HOST,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_TOKEN,
    CONF_USERNAME,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import VolDictType
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    ENVOY_NAME,
    INVALID_AUTH_ERRORS,
    UNIQUE_ID,
    CONF_MANUAL_TOKEN,
    ACCESS_TOKEN_LOGIN_URL,
)

type OurConfigEntry = ConfigEntry

CONF_SERIAL = "serial"

INSTALLER_AUTH_USERNAME = "installer"

_LOGGER = logging.getLogger(__name__)

AVOID_REFLECT_KEYS = {CONF_PASSWORD, CONF_TOKEN}

UNKNOWN_TOKEN_TEXT = "?"


def without_avoid_reflect_keys(dictionary: Mapping[str, Any]) -> dict[str, Any]:
    """Return a dictionary without AVOID_REFLECT_KEYS."""
    return {k: v for k, v in dictionary.items() if k not in AVOID_REFLECT_KEYS}


def token_lifetime(token: str) -> str:
    """Return token lifetime in days."""
    days_left = UNKNOWN_TOKEN_TEXT
    try:
        jwt_payload = jwt.decode(token, options={"verify_signature": False})
        exp = jwt_payload.get("exp")
        if exp is not None:
            days_left = str(int((int(exp) - dt_util.utcnow().timestamp()) / 86400))
    except (jwt.PyJWTError, KeyError, TypeError, ValueError):
        days_left = UNKNOWN_TOKEN_TEXT
    return days_left


def descriptions(
    serial: str, token_days_left: str = UNKNOWN_TOKEN_TEXT
) -> dict[str, str]:
    """Build description placeholders."""
    return {
        CONF_SERIAL: serial,
        "enphase_url": ACCESS_TOKEN_LOGIN_URL,
        "token_life": token_days_left,
    }


async def validate_input(
    hass: HomeAssistant,
    host: str,
    username: str,
    password: str,
    token: str | None,
    errors: dict[str, str],
    description_placeholders: dict[str, str],
) -> Envoy:
    """Validate the user input allows us to connect."""
    envoy = Envoy(host, async_get_clientsession(hass, verify_ssl=False))
    try:
        await envoy.setup()
        await envoy.authenticate(username=username, password=password, token=token)
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
        self.manual_token: bool = False

    @callback
    def _async_generate_schema(self) -> vol.Schema:
        """Generate schema."""
        schema: VolDictType = {}

        if self.source != SOURCE_REAUTH:
            schema[vol.Required(CONF_HOST)] = str

        default_username = ""

        if self.manual_token:
            # in manual token entry mode show token input field
            schema[vol.Optional(CONF_TOKEN, default="")] = str
        else:
            # in automatic token mode show username and password inputs
            schema[vol.Optional(CONF_USERNAME, default=self.username or default_username)] = str
            schema[vol.Optional(CONF_PASSWORD, default="")] = str

        # option to switch between automatic and manual token entry modes
        schema[vol.Optional(CONF_MANUAL_TOKEN, default=self.manual_token)] = bool

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
        token_days_left: str = UNKNOWN_TOKEN_TEXT

        if user_input and (token := user_input.get(CONF_TOKEN, "")):
            token_days_left = token_lifetime(token)

        if user_input is not None:
            if (
                manual_mode := user_input.get(CONF_MANUAL_TOKEN, False)
            ) != self.manual_token:
                # for new config self.manual_token starts default as false
                # user is switching between manual and automatic token entry mode
                # show form again in other mode, no configuration update yet
                self.manual_token = manual_mode
            else:
                envoy = await validate_input(
                    self.hass,
                    host,
                    user_input.get(CONF_USERNAME, ""),
                    user_input.get(CONF_PASSWORD, ""),
                    token := user_input.get(CONF_TOKEN, ""),
                    errors,
                    description_placeholders,
                )
                if not errors:
                    name = self._async_envoy_name()
                    # successful authentication, store token in config
                    token_update = (
                        {CONF_TOKEN: envoy.auth.token}
                        if isinstance(envoy.auth, EnvoyTokenAuth)
                        else {}
                    )

                    if not self.unique_id:
                        await self.async_set_unique_id(
                            f"{UNIQUE_ID}{envoy.serial_number}"
                        )
                        name = self._async_envoy_name()

                    if self.unique_id:
                        # If envoy exists in configuration update fields and exit
                        self._abort_if_unique_id_configured(
                            {
                                CONF_HOST: host,
                                CONF_USERNAME: user_input.get(CONF_USERNAME, ""),
                                CONF_PASSWORD: user_input.get(CONF_PASSWORD, ""),
                                CONF_MANUAL_TOKEN: self.manual_token,
                            }
                            | token_update,
                            error="reauth_successful",
                        )

                    # CONF_NAME is still set for legacy backwards compatibility
                    return self.async_create_entry(
                        title=name,
                        data={CONF_HOST: host, CONF_NAME: name}
                        | user_input
                        | token_update,
                    )

        description_placeholders.update(descriptions("", token_days_left))
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                self._async_generate_schema(),
                without_avoid_reflect_keys(user_input or {}),
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
        token_days_left: str = UNKNOWN_TOKEN_TEXT

        if token := reconfigure_entry.data.get(CONF_TOKEN, ""):
            token_days_left = token_lifetime(token)
        if user_input is None:
            # remember current manual_token setting to detect switch between modes
            self.manual_token = reconfigure_entry.data.get(CONF_MANUAL_TOKEN, False)
        elif user_input.get(CONF_MANUAL_TOKEN) != self.manual_token:
            # user switches between manual and automatic token entry mode
            # show form again on other mode, no configuration update yet
            self.manual_token = user_input[CONF_MANUAL_TOKEN]
        else:
            envoy = await validate_input(
                self.hass,
                host := user_input[CONF_HOST],
                username := user_input.get(CONF_USERNAME, ""),
                password := user_input.get(CONF_PASSWORD, ""),
                token := user_input.get(CONF_TOKEN, ""),
                errors,
                description_placeholders,
            )
            if not errors:
                # successful authentication, store token in config
                await self.async_set_unique_id(f"{UNIQUE_ID}{envoy.serial_number}")
                self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(
                    reconfigure_entry,
                    data_updates={
                        CONF_HOST: host,
                        CONF_USERNAME: username,
                        CONF_PASSWORD: password,
                        CONF_MANUAL_TOKEN: self.manual_token,
                    }
                    | (
                        {CONF_TOKEN: envoy.auth.token}
                        if isinstance(envoy.auth, EnvoyTokenAuth)
                        else {}
                    ),
                )
            if token:
                token_days_left = token_lifetime(token)

        serial = reconfigure_entry.unique_id.replace(UNIQUE_ID, "") or "-"
        self.context["title_placeholders"] = {
            CONF_SERIAL: serial,
            CONF_HOST: reconfigure_entry.data[CONF_HOST],
        }
        description_placeholders.update(descriptions(serial, token_days_left))

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                self._async_generate_schema(),
                without_avoid_reflect_keys(user_input or reconfigure_entry.data),
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
        token_days_left: str = UNKNOWN_TOKEN_TEXT

        if token := reauth_entry.data.get(CONF_TOKEN, ""):
            token_days_left = token_lifetime(token)

        if user_input is None:
            # remember current manual_token setting to detect switch between modes
            self.manual_token = reauth_entry.data.get(CONF_MANUAL_TOKEN, False)
        elif user_input.get(CONF_MANUAL_TOKEN) != self.manual_token:
            # user is switching between manual and automatic token entry mode
            # display the form in the other mode, no configuration update yet
            self.manual_token = user_input[CONF_MANUAL_TOKEN]
        else:
            envoy = await validate_input(
                self.hass,
                reauth_entry.data[CONF_HOST],
                user_input.get(CONF_USERNAME, ""),
                user_input.get(CONF_PASSWORD, ""),
                token := user_input.get(CONF_TOKEN, ""),
                errors,
                description_placeholders,
            )
            if not errors:
                return self.async_update_reload_and_abort(
                    reauth_entry,
                    data_updates=user_input
                    | (
                        {CONF_TOKEN: envoy.auth.token}
                        if isinstance(envoy.auth, EnvoyTokenAuth)
                        else {}
                    ),
                )
            if token:
                token_days_left = token_lifetime(token)

        serial = reauth_entry.unique_id.replace(UNIQUE_ID, "") or "-"
        self.context["title_placeholders"] = {
            CONF_SERIAL: serial,
            CONF_HOST: reauth_entry.data[CONF_HOST],
        }
        description_placeholders.update(descriptions(serial, token_days_left))
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=self.add_suggested_values_to_schema(
                self._async_generate_schema(),
                without_avoid_reflect_keys(user_input or reauth_entry.data),
            ),
            description_placeholders=description_placeholders,
            errors=errors,
        )
