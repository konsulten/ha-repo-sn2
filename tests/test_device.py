"""
Test suite for the Device class in the SystemNexa2 integration.

This module contains tests for the Device class, including positive and
negative test cases for WebSocket communication, message processing, and
lifecycle events.
"""

import asyncio
import contextlib
import json
from unittest.mock import AsyncMock, patch, MagicMock
from typing import TYPE_CHECKING
import logging, sys
import pytest
from sn2.device import Device

if TYPE_CHECKING:
    from collections.abc import Generator


@pytest.fixture(autouse=True)
def configure_logger():
    """Configure the logger to output to stdout during tests."""
    logger = logging.getLogger("sn2.device")  # Replace with your logger name
    logger.setLevel(logging.DEBUG)  # Set the desired log level
    handler = logging.StreamHandler(sys.stdout)  # Log to stdout
    handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    logger.handlers = [handler]  # Replace existing handlers with this one


@pytest.mark.asyncio
class TestDevice:
    """Test suite for the Device class."""

    @pytest.fixture
    def device(self) -> Device:
        """Fixture to create a Device instance."""
        self.on_connect_mock = AsyncMock()
        self.on_disconnect_mock = AsyncMock()
        self.on_information_update_mock = AsyncMock()
        self.on_settings_update_mock = AsyncMock()

        return Device(
            host="192.168.1.100",
            on_connected=self.on_connect_mock,
            on_disconnect=self.on_disconnect_mock,
            on_information_update=self.on_information_update_mock,
            on_settings_update=self.on_settings_update_mock,
        )

    @pytest.fixture
    def mock_websocket(self) -> "Generator":
        """Properly patch websockets.connect to work with any URL."""
        with patch("websockets.connect") as mocked_connect:

            async def mock_aenter(_) -> AsyncMock:
                mocked_websocket = AsyncMock()
                mocked_websocket.recv = AsyncMock(return_value="mocked_message")
                mocked_websocket.send = AsyncMock()
                mocked_websocket.close = AsyncMock()
                return mocked_websocket

            async def mock_aexit(obj: object, exc: Exception, tb: object) -> None:
                return

            mocked_connect.__aexit__ = mock_aexit
            mocked_connect.__aenter__ = mock_aenter

            yield mocked_connect

    async def test_connect_disconnect_success(
        self, mock_websocket: AsyncMock, device: Device
    ) -> None:
        """Test successful connection to the device."""
        mock_ws = mock_websocket.return_value.__aenter__.return_value

        await device.connect()
        await asyncio.sleep(0)  # Allow the task to start

        # Replace private member access with a public method or property
        mock_ws.send.assert_called_with(json.dumps({"type": "login", "value": ""}))
        self.on_connect_mock.assert_called_once()
        self.on_disconnect_mock.assert_not_called()
        await device.disconnect()
        self.on_disconnect_mock.assert_called_once()

    async def test_connect_failure(
        self, device: Device, mock_websocket: AsyncMock
    ) -> None:
        """Test connection failure to the device."""
        mock_ws = mock_websocket.return_value

        mock_ws.side_effect = ConnectionError("Connection error")

        # with capsys.disabled():
        await device.connect()
        await asyncio.sleep(0)  # Allow the task to start

        # self.on_disconnect_mock.assert_called_once()

    async def test_information_message(self, device: Device, mock_websocket: AsyncMock):
        info_message = '{"type": "information", "value": {"fhs": 90752, "u": 261970, "wr": -60, "ss": "0.00", "t": "68.20", "n": "Köks", "tsc": 3, "lcu": "34f0237d-f2b0-471f-8b4e-94eed5abfa6d", "lat": 62, "lon": 15, "cs": true, "sr_h": 8, "sr_m": 1, "ss_h": 15, "ss_m": 25, "tz_o": 3600, "tz_i": 1, "tz_dst": 0, "c": false, "ws": "Edmark_v2", "rr": 1, "hwm": "WBD-01", "nhwv": 1, "nswv": "1.1.1", "b": {"s": 1, "v": 0, "bp": 0, "bpr": 0, "bi": 0}}}'

        mock_ws = mock_websocket.return_value.__aenter__.return_value
        mock_ws.recv.return_value = info_message
        await device.connect()
        await asyncio.sleep(0)
        self.on_information_update_mock.assert_called_once()
        assert False

    async def test_settings_message(self, device: Device, mock_websocket: AsyncMock):
        settings_message = '{"type": "settings", "value": {"name": "DeviceName", "tz_id": 1, "auto_on_seconds": 0, "auto_off_seconds": 0, "enable_local_security": 0, "vacation_mode": 0, "state_after_powerloss": 2, "disable_physical_button": 0, "disable_433": 1, "disable_multi_press": 0, "disable_network_ctrl": 0, "disable_led": 0, "disable_on_transmitters": 0, "disable_off_transmitters": 0, "dimmer_edge": 0, "blink_on_433_on": 0, "button_type": 0, "diy_mode": 1, "toggle_433": 0, "position_man_set": 0, "dimmer_on_start_level": 0, "dimmer_off_level": 0, "dimmer_min_dim": 0, "remote_log": 1, "notifcation_on": 1, "notifcation_off": 0}}'

    # async def test_get_settings_success(self, device: Device) -> None:
    #     """Test fetching device settings via REST API."""
    #     with patch("aiohttp.ClientSession.get", new_callable=AsyncMock) as mock_get:
    #         mock_response = AsyncMock()
    #         mock_response.json = AsyncMock(return_value={"toggle_433": 1})
    #         mock_get.return_value.__aenter__.return_value = mock_response

    #         settings = await device.get_settings()
    #         assert settings == {"toggle_433": 1}

    # async def test_get_settings_failure(self, device: Device) -> None:
    #     """Test failure when fetching device settings via REST API."""
    #     with patch("aiohttp.ClientSession.get", new_callable=AsyncMock) as mock_get:
    #         mock_get.side_effect = RuntimeError("HTTP error")

    #         settings = await device.get_settings()
    #         assert settings is None
