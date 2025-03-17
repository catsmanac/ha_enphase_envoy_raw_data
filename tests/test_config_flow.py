"""Test the Enphase Envoy config flow."""

from ipaddress import ip_address
import logging
from unittest.mock import AsyncMock

from pyenphase import EnvoyAuthenticationError, EnvoyError
import pytest

from custom_components.enphase_envoy_raw_data.const import DOMAIN, ENVOY_NAME, UNIQUE_ID

from homeassistant.config_entries import SOURCE_USER, SOURCE_ZEROCONF
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from . import setup_integration

from pytest_homeassistant_custom_component.common import MockConfigEntry


_LOGGER = logging.getLogger(__name__)


async def test_form(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
    mock_envoy: AsyncMock,
) -> None:
    """Test we get the form."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_HOST: "1.1.1.1",
            CONF_USERNAME: "test-username",
            CONF_PASSWORD: "test-password",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == f"{ENVOY_NAME} 1234"
    assert result["result"].unique_id == f"{UNIQUE_ID}1234"
    assert result["data"] == {
        CONF_HOST: "1.1.1.1",
        CONF_NAME: f"{ENVOY_NAME} 1234",
        CONF_USERNAME: "test-username",
        CONF_PASSWORD: "test-password",
    }


async def test_user_no_serial_number(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
    mock_envoy: AsyncMock,
) -> None:
    """Test user setup without a serial number."""
    mock_envoy.serial_number = None
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_HOST: "1.1.1.1",
            CONF_USERNAME: "test-username",
            CONF_PASSWORD: "test-password",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == f"{ENVOY_NAME} None"
    assert result["result"].unique_id == f"{UNIQUE_ID}None"
    assert result["data"] == {
        CONF_HOST: "1.1.1.1",
        CONF_NAME: f"{ENVOY_NAME} None",
        CONF_USERNAME: "test-username",
        CONF_PASSWORD: "test-password",
    }


@pytest.mark.parametrize(
    ("exception", "error"),
    [
        (EnvoyAuthenticationError("fail authentication"), "invalid_auth"),
        (EnvoyError, "cannot_connect"),
        (Exception, "unknown"),
        (ValueError, "unknown"),
    ],
)
async def test_form_errors(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
    mock_envoy: AsyncMock,
    exception: Exception,
    error: str,
) -> None:
    """Test we handle form errors."""
    mock_envoy.setup.side_effect = exception
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_HOST: "1.1.1.1",
            CONF_USERNAME: "test-username",
            CONF_PASSWORD: "test-password",
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}

    mock_envoy.setup.side_effect = None
    # mock successful authentication and update of credentials
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_HOST: "1.1.1.1",
            CONF_USERNAME: "test-username",
            CONF_PASSWORD: "test-password",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY

async def test_reauth(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_setup_entry: AsyncMock,
    mock_envoy: AsyncMock,
) -> None:
    """Test we reauth auth."""
    await setup_integration(hass, config_entry)
    result = await config_entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_USERNAME: "test-username",
            CONF_PASSWORD: "test-password",
        },
    )
    assert result2["type"] is FlowResultType.ABORT
    assert result2["reason"] == "reauth_successful"


async def test_reconfigure(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_setup_entry: AsyncMock,
    mock_envoy: AsyncMock,
) -> None:
    """Test we can reconfiger the entry."""
    await setup_integration(hass, config_entry)
    result = await config_entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    assert result["errors"] == {}

    # original entry
    assert config_entry.data[CONF_HOST] == "1.1.1.1"
    assert config_entry.data[CONF_USERNAME] == "test-username"
    assert config_entry.data[CONF_PASSWORD] == "test-password"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_HOST: "1.1.1.2",
            CONF_USERNAME: "test-username2",
            CONF_PASSWORD: "test-password2",
        },
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"

    # changed entry
    assert config_entry.data[CONF_HOST] == "1.1.1.2"
    assert config_entry.data[CONF_USERNAME] == "test-username2"
    assert config_entry.data[CONF_PASSWORD] == "test-password2"


async def test_reconfigure_nochange(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_setup_entry: AsyncMock,
    mock_envoy: AsyncMock,
) -> None:
    """Test we get the reconfigure form and apply nochange."""
    await setup_integration(hass, config_entry)
    result = await config_entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    assert result["errors"] == {}

    # original entry
    assert config_entry.data[CONF_HOST] == "1.1.1.1"
    assert config_entry.data[CONF_USERNAME] == "test-username"
    assert config_entry.data[CONF_PASSWORD] == "test-password"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_HOST: "1.1.1.1",
            CONF_USERNAME: "test-username",
            CONF_PASSWORD: "test-password",
        },
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"

    # unchanged original entry
    assert config_entry.data[CONF_HOST] == "1.1.1.1"
    assert config_entry.data[CONF_USERNAME] == "test-username"
    assert config_entry.data[CONF_PASSWORD] == "test-password"


async def test_reconfigure_otherenvoy(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_setup_entry: AsyncMock,
    mock_envoy: AsyncMock,
) -> None:
    """Test entering ip of other envoy and prevent changing it based on serial."""
    await setup_integration(hass, config_entry)
    result = await config_entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    assert result["errors"] == {}

    # let mock return different serial from first time, sim it's other one on changed ip
    mock_envoy.serial_number = "45678"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_HOST: "1.1.1.2",
            CONF_USERNAME: "test-username",
            CONF_PASSWORD: "new-password",
        },
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "unique_id_mismatch"

    # entry should still be original entry
    assert config_entry.data[CONF_HOST] == "1.1.1.1"
    assert config_entry.data[CONF_USERNAME] == "test-username"
    assert config_entry.data[CONF_PASSWORD] == "test-password"


@pytest.mark.parametrize(
    ("exception", "error"),
    [
        (EnvoyAuthenticationError("fail authentication"), "invalid_auth"),
        (EnvoyError, "cannot_connect"),
        (Exception, "unknown"),
    ],
)
async def test_reconfigure_auth_failure(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_setup_entry: AsyncMock,
    mock_envoy: AsyncMock,
    exception: Exception,
    error: str,
) -> None:
    """Test changing credentials for existing host with auth failure."""
    await setup_integration(hass, config_entry)

    result = await config_entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {}

    # existing config
    assert config_entry.data[CONF_HOST] == "1.1.1.1"
    assert config_entry.data[CONF_USERNAME] == "test-username"
    assert config_entry.data[CONF_PASSWORD] == "test-password"

    mock_envoy.authenticate.side_effect = exception

    # mock failing authentication on first try
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_HOST: "1.1.1.2",
            CONF_USERNAME: "test-username",
            CONF_PASSWORD: "wrong-password",
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}

    mock_envoy.authenticate.side_effect = None
    # mock successful authentication and update of credentials
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_HOST: "1.1.1.2",
            CONF_USERNAME: "test-username",
            CONF_PASSWORD: "changed-password",
        },
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"

    # updated config with new ip and changed pw
    assert config_entry.data[CONF_HOST] == "1.1.1.2"
    assert config_entry.data[CONF_USERNAME] == "test-username"
    assert config_entry.data[CONF_PASSWORD] == "changed-password"


async def test_reconfigure_change_ip_to_existing(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_setup_entry: AsyncMock,
    mock_envoy: AsyncMock,
) -> None:
    """Test reconfiguration to existing entry with same ip does not harm existing one."""
    await setup_integration(hass, config_entry)
    other_entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="65432155aaddb2007c5f6602e0c38e72",
        title="Envoy 654321",
        unique_id="654321",
        data={
            CONF_HOST: "1.1.1.2",
            CONF_NAME: "Envoy 654321",
            CONF_USERNAME: "other-username",
            CONF_PASSWORD: "other-password",
        },
    )
    other_entry.add_to_hass(hass)

    # original other entry
    assert other_entry.data[CONF_HOST] == "1.1.1.2"
    assert other_entry.data[CONF_USERNAME] == "other-username"
    assert other_entry.data[CONF_PASSWORD] == "other-password"

    result = await config_entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    assert result["errors"] == {}

    # original entry
    assert config_entry.data[CONF_HOST] == "1.1.1.1"
    assert config_entry.data[CONF_USERNAME] == "test-username"
    assert config_entry.data[CONF_PASSWORD] == "test-password"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_HOST: "1.1.1.2",
            CONF_USERNAME: "test-username",
            CONF_PASSWORD: "test-password2",
        },
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"

    # updated entry
    assert config_entry.data[CONF_HOST] == "1.1.1.2"
    assert config_entry.data[CONF_USERNAME] == "test-username"
    assert config_entry.data[CONF_PASSWORD] == "test-password2"

    # unchanged other entry
    assert other_entry.data[CONF_HOST] == "1.1.1.2"
    assert other_entry.data[CONF_USERNAME] == "other-username"
    assert other_entry.data[CONF_PASSWORD] == "other-password"
