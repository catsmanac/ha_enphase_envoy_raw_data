"""Initialization for Enphase Envoy Raw Data Support.

This custom integration registers an enphase_envoy_raw_data integration
that only provides a read_data(endpoint) and send_data(endpoint,data)
action/service. No entities are provided.

!!! SENDING DATA TO AN ENVOY ENDPOINT HAS RISK FOR PROPER OPERATION OF THE ENVOY.
DOING SO IS AT YOUR OWN RISK AND SHOULD ONLY BE DONE FULLY UNDERSTANDING ANY EFFECT OF IT !!!

This integration does not replace the core integration. It can be used next to it
"""

from __future__ import annotations

import logging

from pyenphase import Envoy

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.httpx_client import get_async_client
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, UNIQUE_ID
from .coordinator import EnphaseRawDataConfigEntry, EnphaseRawDataUpdateCoordinator
from .services import setup_hass_services

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up Enphase Envoy raw data integration."""

    # setup the enphase_envoy_raw_data services
    await setup_hass_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Enphase Envoy raw data support from a config entry."""

    host = entry.data[CONF_HOST]
    envoy = Envoy(host, get_async_client(hass, verify_ssl=False))
    coordinator = EnphaseRawDataUpdateCoordinator(hass, envoy, entry)

    # wait for one pyenphase data collection cycle to establish communication
    await coordinator.async_config_entry_first_refresh()
    if not entry.unique_id:
        hass.config_entries.async_update_entry(
            entry, unique_id=f"{UNIQUE_ID}{envoy.serial_number}"
        )

    if entry.unique_id.replace(UNIQUE_ID, "") != envoy.serial_number:
        # If the serial number of the device does not match the unique_id
        # of the config entry, it likely means the DHCP lease has expired
        # and the device has been assigned a new IP address. We need to
        # wait for the next discovery to find the device at its new address
        # and update the config entry so we do not mix up devices.
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="unexpected_device",
            translation_placeholders={
                "host": host,
                "expected_serial": str(entry.unique_id.replace(UNIQUE_ID, "")),
                "actual_serial": str(envoy.serial_number),
            },
        )

    entry.runtime_data = coordinator

    # Reload entry when it is updated.
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the config entry when it changed."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(
    hass: HomeAssistant, entry: EnphaseRawDataConfigEntry
) -> bool:
    """Unload a config entry."""
    coordinator = entry.runtime_data
    # cancel scheduled functions
    coordinator.async_cancel_token_refresh()
    coordinator.async_cancel_firmware_refresh()
    return True
