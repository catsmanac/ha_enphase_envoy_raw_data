"""Data Coordinator for Enphase Envoy Raw Data Support.

This custom integration registers an enphase_envoy_raw_data integration
that only provides a read_data(endpoint) and send_data(endpoint,data)
action/service. No entities are provided.

!!! SENDING DATA TO AN ENVOY ENDPOINT HAS RISK FOR PROPER OPERATION OF THE ENVOY.
DOING SO IS AT YOUR OWN RISK AND SHOULD ONLY BE DONE FULLY UNDERSTANDING ANY EFFECT OF IT !!!

This integration does not replace the core integration. It can be used next to it
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_NAME,
    CONF_PASSWORD,
    CONF_TOKEN,
    CONF_UNIQUE_ID,
    CONF_USERNAME,
)
from homeassistant.core import HomeAssistant

TO_REDACT = {
    CONF_NAME,
    CONF_PASSWORD,
    # Config entry title and unique ID may contain sensitive data:
    "title",
    CONF_UNIQUE_ID,
    CONF_USERNAME,
    CONF_TOKEN,
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""

    diagnostic_data: dict[str, Any] = {
        "config_entry": async_redact_data(entry.as_dict(), TO_REDACT),
    }

    return diagnostic_data
