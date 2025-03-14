"""Services for Enphase Envoy Raw Data Support.

This custom integration registers an enphase_envoy_raw_data integration
that only provides a read_data(endpoint) and send_data(endpoint,data)
action/service. No entities are provided.

!!! SENDING DATA TO AN ENVOY ENDPOINT HAS RISK FOR PROPER OPERATION OF THE ENVOY.
DOING SO IS AT YOUR OWN RISK AND SHOULD ONLY BE DONE FULLY UNDERSTANDING ANY EFFECT OF IT !!!

This integration does not replace the core integration. It can be used next to it
"""

from __future__ import annotations

import logging
from typing import Any, Never

from httpx import HTTPError, Response
import orjson
from pyenphase import EnvoyError
from pyenphase.const import URL_TARIFF
import voluptuous as vol

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from .const import DOMAIN
from .coordinator import EnphaseRawDataUpdateCoordinator

ATTR_CONFIG_ENTRY_ID = "config_entry_id"
ATTR_ENDPOINT = "endpoint"
ATTR_DATA = "data"
ATTR_METHOD = "method"
ATTR_RISK_ACKNOWLEDGED = "risk_acknowledged"
ATTR_VALIDATE_MODE = "test_mode"
ATTR_FROM_CACHE = "from_cache"

REQUESTERRORS = (EnvoyError, HTTPError)

_LOGGER = logging.getLogger(__name__)


def _raise_validation(key: str, param: str = "") -> Never:
    """Raise Servicevalidation error."""
    raise ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key=key,
        translation_placeholders={
            "args": param,
        },
    )


def _raise_ha_error(call: ServiceCall, key: str, host: str, param: str) -> Never:
    """Raise HomeAssistant error."""
    raise HomeAssistantError(
        translation_domain=DOMAIN,
        translation_key=key,
        translation_placeholders={
            "host": host,
            "args": f"{call.service} {param}",
        },
    )


def _find_envoy_coordinator(
    hass: HomeAssistant, call: ServiceCall
) -> EnphaseRawDataUpdateCoordinator:
    """Find envoy config entry from service data and return envoy coordinator."""
    identifier = str(call.data.get(ATTR_CONFIG_ENTRY_ID))
    _LOGGER.debug("Finding coordinator for %s", identifier)
    if not (entry := hass.config_entries.async_get_entry(identifier)):
        _raise_validation("envoy_service_no_config", identifier)
    if entry.state is not ConfigEntryState.LOADED:
        _raise_validation("not_initialized", identifier)

    coordinator: EnphaseRawDataUpdateCoordinator = entry.runtime_data
    if (
        not (coordinator)
        or not (envoy_to_use := coordinator.envoy)
        or not envoy_to_use.data
        or not envoy_to_use.data.raw
    ):
        _raise_validation("not_initialized", identifier)
    return coordinator


async def _envoy_request(
    hass: HomeAssistant,
    call: ServiceCall,
    endpoint: str,
    method: str | None = None,
    data: dict[str, Any] | None = None,
    to_cache: bool = False,
    from_cache: bool = False,
) -> Any:
    """Send request to envoy an return reply."""
    coordinator = _find_envoy_coordinator(hass, call)
    envoy_to_use = coordinator.envoy
    if from_cache and endpoint in envoy_to_use.data.raw:
        _LOGGER.debug(
            "envoy_request, return data from cache %s", envoy_to_use.data.raw[endpoint]
        )
        return envoy_to_use.data.raw[endpoint]
    try:
        _LOGGER.debug("envoy_request, sending request to %s", endpoint)
        reply: Response = await envoy_to_use.request(endpoint, data, method)
    except REQUESTERRORS as err:
        _raise_ha_error(call, "envoy_error", envoy_to_use.host, err.args[0])

    if not (200 <= reply.status_code < 300):
        _raise_ha_error(
            call,
            "envoy_error",
            f"{envoy_to_use.host}{endpoint}",
            f"{reply.status_code} {reply.reason_phrase}",
        )
    _LOGGER.debug(
        "envoy_request, request status %s %s", reply.status_code, reply.reason_phrase
    )

    try:
        result = orjson.loads(reply.content)
    except (orjson.JSONDecodeError, ValueError):
        # it's xml or html
        _LOGGER.debug("envoy_request, No JSON data returned, decode it")
        result = reply.content.decode("utf-8")
    if to_cache:
        envoy_to_use.data.raw[endpoint] = result
    return result


async def setup_hass_services(hass: HomeAssistant) -> ServiceResponse:
    """Configure Home Assistant services for Enphase_Envoy."""

    async def read_data_service(call: ServiceCall) -> ServiceResponse:
        """Send GET request to envoy."""
        endpoint = call.data[ATTR_ENDPOINT]
        _LOGGER.debug("read_data_service, reading endpoint %s", endpoint)
        reply = await _envoy_request(
            hass,
            call,
            endpoint=endpoint,
            to_cache=True,
            from_cache=call.data.get(ATTR_FROM_CACHE, False),
        )
        return {endpoint: reply}

    # declare read request services
    hass.services.async_register(
        DOMAIN,
        "read_data",
        read_data_service,
        schema=vol.Schema(
            {
                vol.Required(ATTR_CONFIG_ENTRY_ID): str,
                vol.Required(ATTR_ENDPOINT): str,
                vol.Optional(ATTR_FROM_CACHE): bool,
            }
        ),
        supports_response=SupportsResponse.OPTIONAL,
    )

    async def send_data_service(call: ServiceCall) -> ServiceResponse:
        """Send put or post request to envoy."""
        if not call.data[ATTR_RISK_ACKNOWLEDGED]:
            _raise_validation("not_acknowledged", call.service)
        endpoint = call.data[ATTR_ENDPOINT]
        data = call.data[ATTR_DATA]
        _LOGGER.debug("send_data_service endpoint: %s data: %s", endpoint, data)
        try:
            # make data dict or list
            data_to_send = data if isinstance(data, (dict)) else orjson.loads(str(data))
        except (orjson.JSONDecodeError, ValueError, TypeError) as err:
            _raise_validation(
                "envoy_service_invalid_parameter",
                f", Error: {err.args[0]}, Data: {data}",
            )

        # if in validate mode return data to send
        if call.data.get(ATTR_VALIDATE_MODE):
            try:
                _LOGGER.debug(
                    "send_data_service, test mode, not sending data, returning formatted data: %s",
                    {endpoint: data_to_send},
                )
                return {endpoint: data_to_send}
            except TypeError as err:
                _raise_validation(
                    "envoy_service_invalid_parameter",
                    f", Error: {err.args[0]}, Data: {data}",
                )
        try:
            reply = await _envoy_request(
                hass,
                call,
                endpoint=endpoint,
                method=call.data.get(ATTR_METHOD),
                data=dict(data_to_send),
            )
        except TypeError as err:
            _raise_validation(
                "envoy_service_invalid_parameter",
                f", Error: {err.args[0]}, Data: {data}",
            )

        return {endpoint: reply}

    # declare SEND request services
    hass.services.async_register(
        DOMAIN,
        "send_data",
        send_data_service,
        schema=vol.Schema(
            {
                vol.Required(ATTR_CONFIG_ENTRY_ID): str,
                vol.Required(ATTR_ENDPOINT): str,
                vol.Required(ATTR_DATA): vol.Any(str, object),
                vol.Required(ATTR_METHOD): vol.In(["PUT", "POST"]),
                vol.Required(ATTR_RISK_ACKNOWLEDGED): bool,
                vol.Required(ATTR_VALIDATE_MODE): bool,
            }
        ),
        supports_response=SupportsResponse.OPTIONAL,
    )

    return None
