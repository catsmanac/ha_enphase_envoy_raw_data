"""Tests for the Enphase Envoy raw data custom integration."""

from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntryState
from homeassistant.util.dt import now
from jwt import encode

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry


async def setup_integration(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    expected_state: ConfigEntryState = ConfigEntryState.LOADED,
) -> None:
    """Fixture for setting up the component and testing expected state."""
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert config_entry.state is expected_state  # noqa: S101


def envoy_token(days_to_expiry: int = 365) -> str:
    """Build envoy token with specified days to expiration."""
    return encode(
        payload={
            "name": "envoy",
            "exp": (now() + timedelta(days=days_to_expiry)).timestamp(),
        },
        key="useaverylongsecrettoavoidjwtwarning",
        algorithm="HS256",
    )
