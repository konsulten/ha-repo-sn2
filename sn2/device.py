"""
Device client for SystemNexa2 integration.

Handles connection, message processing, and lifecycle events for devices.
"""

import asyncio
import contextlib
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Final
from wsgiref.util import setup_testing_defaults

import aiohttp
import websockets

from sn2.json_model import DeviceInformation, Settings

_LOGGER = logging.getLogger(__name__)

SWITCH_MODELS: Final = ["WBR-01"]
PLUG_MODELS: Final = ["WPR-01", "WPO-01"]
LIGHT_MODELS: Final = ["WBD-01", "WPD-01"]


@dataclass
class InformationData:
    """
    Device information data container.

    Attributes
    ----------
    dimmable : bool
        Whether the device supports dimming.
    model : str | None
        The hardware model of the device.
    sw_version : str | None
        The software version of the device.
    hw_version : str | None
        The hardware version of the device.
    name : str | None
        The name of the device.
    wifi_dbm : int | None
        The WiFi signal strength in dBm.
    wifi_ssid : str | None
        The WiFi SSID the device is connected to.
    unique_id : str | None
        The unique identifier of the device.

    """

    dimmable: bool = False
    model: str | None = None
    sw_version: str | None = None
    hw_version: str | None = None
    name: str | None = None
    wifi_dbm: int | None = None
    wifi_ssid: str | None = None
    unique_id: str | None = None

    @staticmethod
    def convert_device_information_to_data(
        info: DeviceInformation,
    ) -> "InformationData":
        """
        Create InformationData from a DeviceInformation object.

        Parameters
        ----------
        info : DeviceInformation
            The device information object to convert.

        Returns
        -------
        InformationData
            A new InformationData instance populated with the device information.

        """
        d = InformationData()
        if info.hwm in LIGHT_MODELS:
            d.dimmable = True
        d.model = info.hwm
        d.sw_version = info.nswv
        d.hw_version = str(info.nhwv)
        d.name = info.n
        d.wifi_dbm = info.wr
        d.wifi_ssid = info.ws
        d.unique_id = info.lcu

        return d


@dataclass
class ConnectionStatus:
    """Connection status event."""

    connected: bool


@dataclass
class InformationUpdate:
    """Information status event."""

    information: InformationData


@dataclass
class StateChange:
    """
    State change event.

    Attributes
    ----------
    state : float
        The new state value of the device.

    """

    state: float


class Setting:
    name: str


class OnOffSetting(Setting):
    def __init__(self, name: str, param_key: str, current, on_value, off_value):
        self.name = name
        self._param_key = param_key
        self._enable_value = on_value
        self._disable_value = off_value
        self.current_state = current

    async def enable(self, device: "Device") -> None:
        await device.update_setting({self._param_key: self._enable_value})

    async def disable(self, device: "Device") -> None:
        await device.update_setting({self._param_key: self._disable_value})

    def is_enabled(self) -> bool:
        return self.current_state == self._enable_value


@dataclass
class SettingsUpdate:
    """Settings update event."""

    settings: list[Setting]


UpdateEvent = ConnectionStatus | InformationUpdate | SettingsUpdate | StateChange


class Device:
    """
    Represents a client for SystemNexa2 device integration.

    Handles connection, message processing, and lifecycle events for devices.

    """

    @staticmethod
    def _is_version_compatible(version: str, min_version: str) -> bool:
        """Check if a version string meets minimum version requirements."""
        try:
            # Clean up version strings - remove any pre-release indicators
            # Example: "0.9.5-beta.2" becomes "0.9.5"
            clean_version = version.split("-")[0].split("+")[0]
            clean_min_version = min_version.split("-")[0].split("+")[0]

            # Split version strings into components
            version_parts = [int(part) for part in clean_version.split(".")]
            min_version_parts = [int(part) for part in clean_min_version.split(".")]

            # Pad shorter lists with zeros
            while len(version_parts) < len(min_version_parts):
                version_parts.append(0)
            while len(min_version_parts) < len(version_parts):
                min_version_parts.append(0)

            # Compare version components
            for v, m in zip(version_parts, min_version_parts, strict=False):
                if v > m:
                    return True
                if v < m:
                    return False

            # All components are equal, so versions are equal

        except (ValueError, IndexError):
            # If parsing fails, log the error and reject the version
            _LOGGER.exception(
                "Error parsing version strings '%s' and '%s'",
                version,
                min_version,
            )
            return False
        return True

    @staticmethod
    def is_device_supported(
        model: str | None, device_version: str | None
    ) -> tuple[bool, str]:
        """Check if a device is supported based on model and firmware version."""
        # Check if this is a supported device
        if model is None:
            return False, "Missing model information"

        # Verify model is in our supported lists
        if (
            model not in SWITCH_MODELS
            and model not in LIGHT_MODELS
            and model not in PLUG_MODELS
        ):
            return False, f"Unsupported model: {model}"

        # Check firmware version requirement
        if device_version is None:
            return False, "Missing firmware version"

        # Version check - require at least 0.9.5
        if not Device._is_version_compatible(device_version, min_version="0.9.5"):
            return (
                False,
                f"Incompatible firmware version {device_version} (min required: 0.9.5)",
            )

        return True, ""

    def __init__(
        self,
        host: str,
        on_update: Callable[[UpdateEvent], Awaitable[None] | None] | None = None,
    ) -> None:
        """
        Initialize the Device client.

        Args:
            host (str): The host address of the device.
            on_update (Callable[[UpdateEvent], Awaitable[None] | None] | None):
                Callback for device update events.

        """
        self.host = host
        # self.dimmable = False
        self._connected = False
        self._websocket: websockets.ClientConnection | None = None
        self._ws_task = None
        self._login_key = None
        self.info_data: InformationData | None = None
        # Info
        # self.model: str | None = None
        # self.sw_version: str | None = None
        # self.hw_version: str | None = None
        # self.name: str | None = None
        # self.wifi_dbm: int | None = None
        # self.wifi_ssid: str | None = None
        # self.unique_id: str | None = None

        # Setttings

        # Callbacks
        self._on_update = on_update

    async def initialize(self) -> None:
        settings = await self.get_settings()
        info = await self.get_info()
        if info and settings:
            self.settings = settings
            self.info_data = info.information
            self.initialized = True
        else:
            msg = "Failed to initialize device"
            raise RuntimeError(msg)

    async def _emit(self, event: UpdateEvent) -> None:
        """Invoke unified callback if provided."""
        if not self._on_update:
            return
        try:
            result = self._on_update(event)
            if isinstance(result, Awaitable):
                await result
        except Exception:
            _LOGGER.exception("on_update callback failed for %s", event)

    async def connect(self) -> None:
        """
        Establish a connection to the device via websocket.

        Starts the websocket client task for handling device communication.
        """
        self._ws_task = asyncio.create_task(self._handle_connection())

    # Set up connection and cleanup
    async def _handle_connection(self) -> None:
        """Start the websocket client for the device."""
        uri = f"ws://{self.host}:3000/live"

        while True:
            try:
                async with websockets.connect(uri) as websocket:
                    self._websocket = websocket
                    # Set device as available since connection is established

                    # Send login message immediately after connection
                    login_message = {"type": "login", "value": ""}
                    await websocket.send(json.dumps(login_message))

                    await self._emit(ConnectionStatus(connected=True))
                    _LOGGER.debug("Sent login message: %s", login_message)

                    # Listen for messages from the device
                    while True:
                        try:
                            message = await websocket.recv()
                            _LOGGER.debug("Received message: %s", message)
                            # Process the message and update entity states
                            match message:
                                case bytes():
                                    await self._process_message(message.decode("utf-8"))
                                case str():
                                    await self._process_message(message)

                        except websockets.exceptions.ConnectionClosed:
                            await self._emit(ConnectionStatus(connected=False))

                            break
                        await asyncio.sleep(1)
            except asyncio.CancelledError:
                break
            except BaseException:
                self._websocket = None
                # Set device as unavailable when connection attempt fails
                await self._emit(ConnectionStatus(connected=False))
                _LOGGER.exception("Lost connection to: %s", self.host)
            # Wait before trying to reconnect
            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                break

    async def disconnect(self) -> None:
        """Stop the websocket client."""
        if self._ws_task is not None:
            self._ws_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._ws_task

        if self._websocket is not None:
            await self._websocket.close()
            self._websocket = None
        await self._emit(ConnectionStatus(connected=False))

    async def _process_message(self, message: str) -> None:
        """Process a message from the device."""
        try:
            data = json.loads(message)

            # Handle reset message - device wants to be removed
            match data.get("type"):
                case "device_reset":
                    _LOGGER.info("device_reset")
                    return
                case "state":
                    # Handle state updates
                    state_value = float(data.get("value", 0))
                    # Find the entity directly from the device_info
                    await self._emit(StateChange(state_value))
                case "information":
                    info_message = data.get("value")
                    information = DeviceInformation(**info_message)
                    _LOGGER.debug("information received %s", information)
                    await self._emit(
                        InformationUpdate(
                            InformationData.convert_device_information_to_data(
                                information
                            )
                        )
                    )
                case "settings":
                    settings = data.get("value")
                    settings = Settings(**settings)
                    await self._emit(
                        SettingsUpdate(settings=await self._parse_settings(settings))
                    )
                case unknown:
                    _LOGGER.error("unknown data received %s", unknown)

        except json.JSONDecodeError:
            _LOGGER.exception("Invalid JSON received %s", unknown)
        except Exception:
            _LOGGER.exception("Error processing message %s", message)

    async def set_brightness(self, value: float) -> None:
        """
        Set the brightness level of the device.

        Parameters
        ----------
        value : float
            The brightness value between 0.0 (off) and 1.0 (full brightness).

        Raises
        ------
        ValueError
            If the brightness value is not between 0 and 1.

        """
        if not 0 <= value <= 1:
            msg = f"Brightness value must be between 0 and 1, got {value}"
            raise ValueError(msg)
        await self.send_command({"type": "state", "value": value})

    async def toggle(self) -> None:
        """Toggle the device state between on and off."""
        await self.send_command({"type": "state", "value": -1})

    async def turn_off(self) -> None:
        """Turn off the device."""
        await self.send_command({"type": "state", "value": 0})

    async def turn_on(self) -> None:
        """Turn on the device."""
        await self.send_command({"type": "state", "value": -1})

    async def send_command(self, command: dict[str, Any]) -> None:
        _LOGGER.error(command)
        if self._websocket is None:
            _LOGGER.error(
                "Cannot send command to %s - no WebSocket connection available",
                self.host,
            )
            return

        try:
            command_str = json.dumps(command)
            _LOGGER.info("Sending command to %s: %s", self.host, command_str)
            await self._websocket.send(command_str)
            _LOGGER.debug("Command sent successfully to %s", self.host)
        except websockets.exceptions.ConnectionClosed as err:
            _LOGGER.exception(
                "Failed to send command to %s - connection closed: %s %s",
                self.host,
                err.code,
                err.reason,
            )
            # Mark entity as unavailable when command fails due to connection issues
            await self._emit(ConnectionStatus(connected=False))
        except Exception:
            _LOGGER.exception("Failed to send command to %s", self.host)

    async def is_supported(self) -> bool:
        """Check if the device is supported based on model and firmware version."""
        info = await self.get_info()
        if info is None:
            return False  # Could be unavailable ?
        supported, _ = Device.is_device_supported(
            model=info.information.model, device_version=info.information.sw_version
        )
        return supported

    async def _parse_settings(self, settings: Settings) -> list[Setting]:
        settings_list = []
        if settings.disable_433 is not None:
            settings_list.append(
                OnOffSetting(
                    param_key="disable_433",
                    name="433Mhz",
                    off_value=1,
                    on_value=0,
                    current=settings.disable_433,
                )
            )
        if settings.disable_physical_button is not None:
            settings_list.append(
                OnOffSetting(
                    param_key="disable_physical_button",
                    name="Physical Button",
                    off_value=1,
                    on_value=0,
                    current=settings.disable_physical_button,
                )
            )
        if settings.disable_led is not None:
            settings_list.append(
                OnOffSetting(
                    param_key="disable_led",
                    name="Led",
                    off_value=1,
                    on_value=0,
                    current=settings.disable_led,
                )
            )
        if settings.diy_mode is not None:
            settings_list.append(
                OnOffSetting(
                    param_key="diy_mode",
                    name="Cloud Access",
                    off_value=1,
                    on_value=0,
                    current=settings.diy_mode,
                )
            )
        return settings_list

    async def update_setting(self, settings: dict[str, Any]) -> None:
        """Update device settings via REST API."""
        url = f"http://{self.host}:3000/settings"
        try:
            async with (
                aiohttp.ClientSession() as session,
                session.post(url, json=settings) as response,
            ):
                response.raise_for_status()

                _LOGGER.error("Updated settings at %s with %s", url, settings)
        except Exception:
            _LOGGER.exception("Failed to update settings at %s", url)
            raise

    async def get_settings(self) -> list[Setting] | None:
        """Fetch device settings via REST API."""
        url = f"http://{self.host}:3000/settings"
        try:
            async with aiohttp.ClientSession() as session, session.get(url) as response:
                response.raise_for_status()
                json_resp = await response.json()
                return await self._parse_settings(Settings(**json_resp))
        except Exception:
            _LOGGER.exception("Failed to fetch settings from %s", url)
            raise

    async def get_info(self) -> InformationUpdate | None:
        """Fetch device information via REST API."""
        url = f"http://{self.host}:3000/info"
        try:
            async with aiohttp.ClientSession() as session, session.get(url) as response:
                response.raise_for_status()
                json_resp = await response.json()
                information = DeviceInformation(**json_resp)
                self.info_data = InformationData.convert_device_information_to_data(
                    information
                )
                return InformationUpdate(self.info_data)
        except Exception:
            _LOGGER.exception("Failed to fetch device information from %s:", url)
            return None
