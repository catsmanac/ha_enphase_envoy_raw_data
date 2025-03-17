"""Test Enphase Envoy runtime."""

from datetime import timedelta
import logging
from unittest.mock import AsyncMock, MagicMock, patch

from freezegun.api import FrozenDateTimeFactory
from jwt import encode
from pyenphase import EnvoyAuthenticationError, EnvoyError, EnvoyTokenAuth
from pyenphase.auth import EnvoyLegacyAuth
import pytest
import respx

from custom_components.enphase_envoy_raw_data.const import DOMAIN

from custom_components.enphase_envoy_raw_data.coordinator import (
    FIRMWARE_REFRESH_INTERVAL,
    SCAN_INTERVAL,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import (
    CONF_HOST,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_TOKEN,
    CONF_USERNAME,
    STATE_UNAVAILABLE,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.update_coordinator import UpdateFailed
from homeassistant.setup import async_setup_component

from . import setup_integration

from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed
from pytest_homeassistant_custom_component.typing import WebSocketGenerator


async def test_with_pre_v7_firmware(
    hass: HomeAssistant,
    mock_envoy: AsyncMock,
    config_entry: MockConfigEntry,
) -> None:
    """Test enphase_envoy coordinator with pre V7 firmware."""
    mock_envoy.firmware = "5.1.1"
    mock_envoy.auth = EnvoyLegacyAuth(
        "127.0.0.1", username="test-username", password="test-password"
    )
    await setup_integration(hass, config_entry)
    assert config_entry.runtime_data.envoy == mock_envoy

@pytest.mark.freeze_time("2024-07-23 00:00:00+00:00")
async def test_token_in_config_file(
    hass: HomeAssistant,
    mock_envoy: AsyncMock,
) -> None:
    """Test coordinator with token provided from config."""
    token = encode(
        payload={"name": "envoy", "exp": 1907837780},
        key="secret",
        algorithm="HS256",
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="45a36e55aaddb2007c5f6602e0c38e72",
        title="Envoy 1234",
        unique_id="1234",
        data={
            CONF_HOST: "1.1.1.1",
            CONF_NAME: "Envoy 1234",
            CONF_USERNAME: "test-username",
            CONF_PASSWORD: "test-password",
            CONF_TOKEN: token,
        },
    )
    mock_envoy.auth = EnvoyTokenAuth("127.0.0.1", token=token, envoy_serial="1234")
    await setup_integration(hass, entry)

    assert entry.runtime_data.envoy == mock_envoy


@respx.mock
@pytest.mark.freeze_time("2024-07-23 00:00:00+00:00")
async def test_expired_token_in_config(
    hass: HomeAssistant,
    mock_envoy: AsyncMock,
) -> None:
    """Test coordinator with expired token provided from config."""
    current_token = encode(
        # some time in 2021
        payload={"name": "envoy", "exp": 1627314600},
        key="secret",
        algorithm="HS256",
    )

    # mock envoy with expired token in config
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="45a36e55aaddb2007c5f6602e0c38e72",
        title="Envoy 1234",
        unique_id="1234",
        data={
            CONF_HOST: "1.1.1.1",
            CONF_NAME: "Envoy 1234",
            CONF_USERNAME: "test-username",
            CONF_PASSWORD: "test-password",
            CONF_TOKEN: current_token,
        },
    )
    # Make sure to mock pyenphase.auth.EnvoyTokenAuth._obtain_token
    # when specifying username and password in EnvoyTokenauth
    mock_envoy.auth = EnvoyTokenAuth(
        "127.0.0.1",
        token=current_token,
        envoy_serial="1234",
        cloud_username="test_username",
        cloud_password="test_password",
    )
    await setup_integration(hass, entry)

    assert entry.runtime_data.envoy == mock_envoy


async def test_coordinator_update_error(
    hass: HomeAssistant,
    mock_envoy: AsyncMock,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test coordinator update error handling."""
    await setup_integration(hass, config_entry)
    assert config_entry.runtime_data.envoy == mock_envoy
    coordinator = config_entry.runtime_data

    mock_envoy.update.side_effect = EnvoyError("This must fail")
    with pytest.raises(
        UpdateFailed,
        match="Error communicating with Envoy API on",
    ):
        await coordinator._async_update_data()


async def test_coordinator_update_authentication_error(
    hass: HomeAssistant,
    mock_envoy: AsyncMock,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test enphase_envoy coordinator update authentication error handling."""
    await setup_integration(hass, config_entry)
    coordinator = config_entry.runtime_data

    mock_envoy.update.side_effect = EnvoyAuthenticationError("This must fail")
    with pytest.raises(
        ConfigEntryAuthFailed,
        match="Envoy authentication failure on",
    ):
        await coordinator._async_update_data()


@pytest.mark.freeze_time("2024-07-23 00:00:00+00:00")
async def test_coordinator_token_refresh_error(
    hass: HomeAssistant,
    mock_envoy: AsyncMock,
) -> None:
    """Test coordinator with expired token and failure to refresh."""
    token = encode(
        # some time in 2021
        payload={"name": "envoy", "exp": 1627314600},
        key="secret",
        algorithm="HS256",
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="45a36e55aaddb2007c5f6602e0c38e72",
        title="Envoy 1234",
        unique_id="1234",
        data={
            CONF_HOST: "1.1.1.1",
            CONF_NAME: "Envoy 1234",
            CONF_USERNAME: "test-username",
            CONF_PASSWORD: "test-password",
            CONF_TOKEN: token,
        },
    )
    # override fresh token in conftest mock_envoy.auth
    mock_envoy.auth = EnvoyTokenAuth("127.0.0.1", token=token, envoy_serial="1234")
    # force token refresh to fail.
    with patch(
        "pyenphase.auth.EnvoyTokenAuth._obtain_token",
        side_effect=EnvoyError,
    ):
        await setup_integration(hass, entry)

    assert entry.runtime_data.envoy == mock_envoy


async def test_config_no_unique_id(
    hass: HomeAssistant,
    mock_envoy: AsyncMock,
) -> None:
    """Test enphase_envoy init if config entry has no unique id."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="45a36e55aaddb2007c5f6602e0c38e72",
        title="Envoy 1234",
        unique_id=None,
        data={
            CONF_HOST: "1.1.1.1",
            CONF_NAME: "Envoy 1234",
            CONF_USERNAME: "test-username",
            CONF_PASSWORD: "test-password",
        },
    )
    await setup_integration(hass, entry)
    assert entry.unique_id == f"{DOMAIN}_for_{mock_envoy.serial_number}"


async def test_config_different_unique_id(
    hass: HomeAssistant,
    mock_envoy: AsyncMock,
) -> None:
    """Test enphase_envoy init if config entry has different unique id."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="45a36e55aaddb2007c5f6602e0c38e72",
        title="Envoy 1234",
        unique_id="4321",
        data={
            CONF_HOST: "1.1.1.1",
            CONF_NAME: "Envoy 1234",
            CONF_USERNAME: "test-username",
            CONF_PASSWORD: "test-password",
        },
    )
    await setup_integration(hass, entry, expected_state=ConfigEntryState.SETUP_RETRY)

async def test_option_change_reload(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_envoy: AsyncMock,
) -> None:
    """Test options change will reload entity."""
    await setup_integration(hass, config_entry)
    # By default neither option is available
    assert config_entry.options == {}

    # option change will also take care of COV of init::async_reload_entry
    hass.config_entries.async_update_entry(
        config_entry,
        options={
            "Test_option": True,
        },
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    assert config_entry.state is ConfigEntryState.LOADED
    assert config_entry.options == {
        "Test_option": True,
    }
    # flip em
    hass.config_entries.async_update_entry(
        config_entry,
        options={
            "Test_option": False,
        },
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    assert config_entry.state is ConfigEntryState.LOADED
    assert config_entry.options == {
        "Test_option": False,
    }

def mock_envoy_setup(mock_envoy: AsyncMock):
    """Mock envoy.setup."""
    mock_envoy.firmware = "9.9.9999"


@patch(
    "custom_components.enphase_envoy_raw_data.coordinator.SCAN_INTERVAL",
    timedelta(days=1),
)
@respx.mock
async def test_coordinator_firmware_refresh(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_envoy: AsyncMock,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test coordinator scheduled firmware check."""
    await setup_integration(hass, config_entry)

    # Move time to next firmware check moment
    # SCAN_INTERVAL is patched to 1 day to disable it's firmware detection
    mock_envoy.setup.reset_mock()
    freezer.tick(FIRMWARE_REFRESH_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)

    mock_envoy.setup.assert_called_once_with()
    mock_envoy.setup.reset_mock()

    envoy = config_entry.runtime_data.envoy
    assert envoy.firmware == "7.6.175"

    caplog.set_level(logging.WARNING)

    with patch(
        "custom_components.enphase_envoy_raw_data.Envoy.setup",
        MagicMock(return_value=mock_envoy_setup(mock_envoy)),
    ):
        freezer.tick(FIRMWARE_REFRESH_INTERVAL)
        async_fire_time_changed(hass)
        await hass.async_block_till_done(wait_background_tasks=True)

        assert (
            "Envoy firmware changed from: 7.6.175 to: 9.9.9999, reloading config entry Envoy 1234"
            in caplog.text
        )
        envoy = config_entry.runtime_data.envoy
        assert envoy.firmware == "9.9.9999"
    
    device_info =  config_entry.runtime_data._get_device_info()
    assert device_info["sw_version"] == "9.9.9999"

@respx.mock
async def test_coordinator_firmware_change_detection(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_envoy: AsyncMock,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test coordinator scheduled firmware check."""
    await setup_integration(hass, config_entry)
    coordinator = config_entry.runtime_data

    mock_envoy.setup.reset_mock()
    await coordinator._async_update_data()
    await hass.async_block_till_done(wait_background_tasks=True)

    envoy = config_entry.runtime_data.envoy
    assert envoy.firmware == "7.6.175"

    caplog.set_level(logging.WARNING)

    with patch(
        "custom_components.enphase_envoy_raw_data.Envoy.setup",
        MagicMock(return_value=mock_envoy_setup(mock_envoy)),
    ):
        await coordinator._async_update_data()
        await hass.async_block_till_done(wait_background_tasks=True)
        mock_envoy.setup.assert_called_once_with()
        assert (
            "Envoy firmware changed from: 7.6.175 to: 9.9.9999, reloading enphase envoy raw data integration"
            in caplog.text
        )
        envoy = config_entry.runtime_data.envoy
        assert envoy.firmware == "9.9.9999"
    
    device_info =  config_entry.runtime_data._get_device_info()
    assert device_info["sw_version"] == "9.9.9999"


@respx.mock
async def test_coordinator_firmware_refresh_with_envoy_error(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_envoy: AsyncMock,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test coordinator scheduled firmware check."""
    await setup_integration(hass, config_entry)

    caplog.set_level(logging.DEBUG)
    logging.getLogger("custom_components.enphase_envoy_raw_data.coordinator").setLevel(
        logging.DEBUG
    )

    mock_envoy.setup.side_effect = EnvoyError
    freezer.tick(FIRMWARE_REFRESH_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)

    assert "Error reading firmware:" in caplog.text
