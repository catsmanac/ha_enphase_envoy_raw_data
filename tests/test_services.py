"""Test the Enphase Envoy services."""

from unittest.mock import AsyncMock, patch, Mock

from pyenphase.const import URL_TARIFF
from pyenphase import EnvoyError
import pytest
from syrupy.assertion import SnapshotAssertion

from custom_components.enphase_envoy_raw_data.const import DOMAIN
from custom_components.enphase_envoy_raw_data.services import (
    ATTR_CONFIG_ENTRY_ID,
    ATTR_DATA,
    ATTR_ENDPOINT,
    ATTR_FROM_CACHE,
    ATTR_METHOD,
    ATTR_RISK_ACKNOWLEDGED,
    ATTR_VALIDATE_MODE
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from . import setup_integration

from pytest_homeassistant_custom_component.common import MockConfigEntry


async def test_has_services(
    hass: HomeAssistant,
    snapshot: SnapshotAssertion,
    mock_envoy: AsyncMock,
    config_entry: MockConfigEntry,
) -> None:
    """Test the existence of the Enphase Envoy Services."""
    await setup_integration(hass, config_entry)
    assert config_entry.state is ConfigEntryState.LOADED
    assert hass.services.has_service(DOMAIN, "read_data")
    assert hass.services.has_service(DOMAIN, "send_data")
    assert snapshot == list(hass.services.async_services_for_domain(DOMAIN).keys())


async def test_service_load_unload(
    hass: HomeAssistant,
    mock_envoy: AsyncMock,
    config_entry: MockConfigEntry,
) -> None:
    """Test service loading and unloading."""
    await setup_integration(hass, config_entry)
    assert config_entry.state is ConfigEntryState.LOADED

    # test with unloaded config entry
    await hass.config_entries.async_unload(config_entry.entry_id)

    with pytest.raises(
        ServiceValidationError,
        match="Enphase_Envoy_raw_data is not yet initialized",
    ):
        await hass.services.async_call(
            DOMAIN,
            "read_data",
            {
                ATTR_CONFIG_ENTRY_ID: config_entry.entry_id,
                ATTR_ENDPOINT : "/api/v1/production/inverters"
            },
            blocking=True,
            return_response=True,
        )

    # test with simulated second loaded envoy for COV on envoylist handling 
    await setup_integration(hass, config_entry)
    assert config_entry.state is ConfigEntryState.LOADED

    await hass.config_entries.async_unload(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.NOT_LOADED


async def test_service_read_data(
    hass: HomeAssistant,
    mock_envoy: AsyncMock,
    config_entry: MockConfigEntry,
) -> None:
    """Test service calls for read_data service."""
    await setup_integration(hass, config_entry)
    assert config_entry.state is ConfigEntryState.LOADED

    mock = Mock()
    mock.status_code = 200
    mock.content = b'{"tariff": {"currency": {"code": "EUR"}}}'
    mock.headers = {"Hello": "World"}
    mock_envoy.request.return_value = mock

    result = await hass.services.async_call(
        DOMAIN,
        "read_data",
        {
            ATTR_CONFIG_ENTRY_ID: config_entry.entry_id,
            ATTR_ENDPOINT : "/tariff"
        },
        blocking=True,
        return_response=True,
    )
    assert result
    assert result["/tariff"] == {"tariff": {"currency": {"code": "EUR"}}}

    test_pattern = {"tariff": {"currency": {"code": "USD"}}}
    mock_envoy.data.raw = {URL_TARIFF: test_pattern}
    result = await hass.services.async_call(
        DOMAIN,
        "read_data",
        {
            ATTR_CONFIG_ENTRY_ID: config_entry.entry_id,
            ATTR_ENDPOINT : URL_TARIFF,
            ATTR_FROM_CACHE: True
        },
        blocking=True,
        return_response=True,
    )
    assert result
    assert result[URL_TARIFF] == {"tariff": {"currency": {"code": "USD"}}}


async def test_service_read_text_data(
    hass: HomeAssistant,
    mock_envoy: AsyncMock,
    config_entry: MockConfigEntry,
) -> None:
    """Test service calls for read_data service."""
    await setup_integration(hass, config_entry)
    assert config_entry.state is ConfigEntryState.LOADED

    mock = Mock()
    mock.status_code = 200
    mock.content = b'Test Ok'
    mock.headers = {"Hello": "World"}
    mock_envoy.request.return_value = mock

    result = await hass.services.async_call(
        DOMAIN,
        "read_data",
        {
            ATTR_CONFIG_ENTRY_ID: config_entry.entry_id,
            ATTR_ENDPOINT : "/tariff"
        },
        blocking=True,
        return_response=True,
    )
    assert result
    assert result["/tariff"] == "Test Ok"

async def test_service_read_data_exceptions(
    hass: HomeAssistant,
    mock_envoy: AsyncMock,
    config_entry: MockConfigEntry,
) -> None:
    """Test service calls for read_data service with faulty service data."""
    await setup_integration(hass, config_entry)
    assert config_entry.state is ConfigEntryState.LOADED

    with pytest.raises(
        ServiceValidationError,
        match=f"No Enphase_Envoy_raw_data configuration entry found: {'123456789'}",
    ):
        await hass.services.async_call(
            DOMAIN,
            "read_data",
            {
                ATTR_CONFIG_ENTRY_ID: "123456789",
                ATTR_ENDPOINT : URL_TARIFF
            },
            blocking=True,
            return_response=True,
        )

    mock_envoy.request.side_effect = EnvoyError("cannot_connect")
    with pytest.raises(
        HomeAssistantError,
        match="Error communicating with Envoy API on",
    ):
        await hass.services.async_call(
            DOMAIN,
            "read_data",
            {
                ATTR_CONFIG_ENTRY_ID: config_entry.entry_id,
                ATTR_ENDPOINT : "/tariff"
            },
            blocking=True,
            return_response=True,
        )

    mock_envoy.request.side_effect = None
    mock = Mock()
    mock.status_code = 300
    mock.content = b'{"tariff": {"currency": {"code": "EUR"}}}'
    mock.headers = {"Hello": "World"}
    mock_envoy.request.return_value = mock

    with pytest.raises(
        HomeAssistantError,
        match="Error communicating with Envoy API on",
    ):
        await hass.services.async_call(
            DOMAIN,
            "read_data",
            {
                ATTR_CONFIG_ENTRY_ID: config_entry.entry_id,
                ATTR_ENDPOINT : "/tariff"
            },
            blocking=True,
            return_response=True,
        )

    mock_envoy.data.raw = None
    with pytest.raises(
        HomeAssistantError,
        match="Enphase_Envoy_raw_data is not yet initialized",
    ):
        await hass.services.async_call(
            DOMAIN,
            "read_data",
            {
                ATTR_CONFIG_ENTRY_ID: config_entry.entry_id,
                ATTR_ENDPOINT : "/tariff"
            },
            blocking=True,
            return_response=True,
        )

async def test_service_send_data(
    hass: HomeAssistant,
    mock_envoy: AsyncMock,
    config_entry: MockConfigEntry,
) -> None:
    """Test service calls for read_data service."""
    await setup_integration(hass, config_entry)
    assert config_entry.state is ConfigEntryState.LOADED

    mock = Mock()
    mock.status_code = 200
    mock.content = b'{"tariff": {"currency": {"code": "EUR"}}}'
    mock.headers = {"Hello": "World"}
    mock_envoy.request.return_value = mock

    result = await hass.services.async_call(
        DOMAIN,
        "send_data",
        {
            ATTR_CONFIG_ENTRY_ID: config_entry.entry_id,
            ATTR_ENDPOINT : "/tariff",
            ATTR_METHOD : "POST",
            ATTR_VALIDATE_MODE: True,
            ATTR_RISK_ACKNOWLEDGED: True,
            ATTR_DATA : {"tariff": {"currency": {"code": "EUR"}}}
        },
        blocking=True,
        return_response=True,
    )
    assert result
    assert result["/tariff"] == {"tariff": {"currency": {"code": "EUR"}}}

    result = await hass.services.async_call(
        DOMAIN,
        "send_data",
        {
            ATTR_CONFIG_ENTRY_ID: config_entry.entry_id,
            ATTR_ENDPOINT : "/tariff",
            ATTR_METHOD : "POST",
            ATTR_VALIDATE_MODE: True,
            ATTR_RISK_ACKNOWLEDGED: True,
            ATTR_DATA : '[{"T1": "V1"}, {"T2": "V2"}]'
        },
        blocking=True,
        return_response=True,
    )
    assert result
    assert result["/tariff"] == [{"T1": "V1"}, {"T2": "V2"}]

    result = await hass.services.async_call(
        DOMAIN,
        "send_data",
        {
            ATTR_CONFIG_ENTRY_ID: config_entry.entry_id,
            ATTR_ENDPOINT : "/tariff",
            ATTR_METHOD : "POST",
            ATTR_VALIDATE_MODE: False,
            ATTR_RISK_ACKNOWLEDGED: True,
            ATTR_DATA : {"tariff": {"currency": {"code": "EUR"}}}
        },
        blocking=True,
        return_response=True,
    )
    assert result
    assert result["/tariff"] == {"tariff": {"currency": {"code": "EUR"}}}


async def test_service_send_data_exceptions(
    hass: HomeAssistant,
    mock_envoy: AsyncMock,
    config_entry: MockConfigEntry,
) -> None:
    """Test service calls for read_data service."""
    await setup_integration(hass, config_entry)
    assert config_entry.state is ConfigEntryState.LOADED

    mock = Mock()
    mock.status_code = 200
    mock.content = b'{"tariff": {"currency": {"code": "EUR"}}}'
    mock.headers = {"Hello": "World"}
    mock_envoy.request.return_value = mock

    with pytest.raises(
        HomeAssistantError,
        match="Risk of using service: send_data, is not acknowledged",
    ):
        await hass.services.async_call(
            DOMAIN,
            "send_data",
            {
                ATTR_CONFIG_ENTRY_ID: config_entry.entry_id,
                ATTR_ENDPOINT : "/tariff",
                ATTR_METHOD : "POST",
                ATTR_VALIDATE_MODE: True,
                ATTR_RISK_ACKNOWLEDGED: False,
                ATTR_DATA : {"tariff": {"currency": {"code": "EUR"}}}
            },
            blocking=True,
            return_response=True,
        )

    with pytest.raises(
        HomeAssistantError,
        match="Invalid parameters , Error:",
    ):
        await hass.services.async_call(
            DOMAIN,
            "send_data",
            {
                ATTR_CONFIG_ENTRY_ID: config_entry.entry_id,
                ATTR_ENDPOINT : "/tariff",
                ATTR_METHOD : "POST",
                ATTR_VALIDATE_MODE: True,
                ATTR_RISK_ACKNOWLEDGED: True,
                ATTR_DATA : 'tariff : {"currency": {"code": "EUR"}}'
            },
            blocking=True,
            return_response=True,
        )

    with pytest.raises(
        HomeAssistantError,
        match="Invalid parameters , Error:",
    ):
        await hass.services.async_call(
            DOMAIN,
            "send_data",
            {
                ATTR_CONFIG_ENTRY_ID: config_entry.entry_id,
                ATTR_ENDPOINT : "/tariff",
                ATTR_METHOD : "POST",
                ATTR_VALIDATE_MODE: True,
                ATTR_RISK_ACKNOWLEDGED: True,
                ATTR_DATA : None
            },
            blocking=True,
            return_response=True,
        )
    with (
        patch(
            "custom_components.enphase_envoy_raw_data.services._envoy_request",
            side_effect=TypeError("Test"),
        ),
        pytest.raises(
            HomeAssistantError,
            match="Invalid parameters , Error:",
        )
    ):
        await hass.services.async_call(
            DOMAIN,
            "send_data",
            {
                ATTR_CONFIG_ENTRY_ID: config_entry.entry_id,
                ATTR_ENDPOINT : "/tariff",
                ATTR_METHOD : "POST",
                ATTR_VALIDATE_MODE: False,
                ATTR_RISK_ACKNOWLEDGED: True,
                ATTR_DATA : {"tariff": {"currency": {"code": "EUR"}}}
            },
            blocking=True,
            return_response=True,
        )
