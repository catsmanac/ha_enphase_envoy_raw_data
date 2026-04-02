"""Test Enphase Envoy diagnostics."""

from typing import TYPE_CHECKING

from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)

from . import setup_integration

if TYPE_CHECKING:
    from unittest.mock import AsyncMock

    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from pytest_homeassistant_custom_component.typing import ClientSessionGenerator
    from syrupy.assertion import SnapshotAssertion

# Fields to exclude from snapshot as they change each run
TO_EXCLUDE = {
    "id",
    "device_id",
    "via_device_id",
    "last_updated",
    "last_changed",
    "last_reported",
    "created_at",
    "modified_at",
}


def limit_diagnostic_attrs(prop: str, path) -> bool:  # noqa: ANN001
    """Mark attributes to exclude from diagnostic snapshot."""
    return prop in TO_EXCLUDE


async def test_entry_diagnostics(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_client: ClientSessionGenerator,
    mock_envoy: AsyncMock,
    snapshot: SnapshotAssertion,
) -> None:
    """Test config entry diagnostics."""
    await setup_integration(hass, config_entry)
    assert await get_diagnostics_for_config_entry(
        hass, hass_client, config_entry
    ) == snapshot(exclude=limit_diagnostic_attrs)  # type: ignore [arg-type]
