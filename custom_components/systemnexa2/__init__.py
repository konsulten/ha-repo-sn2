"""The System Nexa 2 integration."""

import asyncio
import contextlib
import json
import logging

import voluptuous as vol
import websockets
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_DEVICE_ID,
    CONF_HOST,
    CONF_MODEL,
    CONF_NAME,
    CONF_TYPE,
    EVENT_HOMEASSISTANT_STOP,
)
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers.typing import ConfigType

_LOGGER = logging.getLogger(__name__)

# Define constants for the component
DOMAIN = "systemnexa2"
SWITCH_MODELS = ["WBR-01"]
PLUG_MODELS = ["WPR-01", "WPO-01"]
LIGHT_MODELS = ["WBD-01", "WPD-01"]

# Configuration schema
CONFIG_SCHEMA = vol.Schema(
    {DOMAIN: vol.Schema({})},
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, _config: ConfigType) -> bool:
    """Set up the component from configuration.yaml."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Store device info
    device_info = {
        "host": entry.data[CONF_HOST],
        "model": entry.data[CONF_MODEL],
        "name": entry.data[CONF_NAME],
        "device_id": entry.data[CONF_DEVICE_ID],
        "ws_client": None,
        "ws_task": None,
        "available": False,  # Track device availability
        "entities": [],  # Store references to entities for availability updates
    }

    hass.data[DOMAIN][entry.entry_id] = device_info

    # Determine which platform to load based on model
    device_type = entry.data[CONF_TYPE]

    platforms = []
    if device_type == "switch":
        platforms.append("switch")
    elif device_type == "light":
        platforms.append("light")

    if platforms:
        await hass.config_entries.async_forward_entry_setups(entry, platforms)

    # Set up connection and cleanup
    async def start_websocket_client() -> None:
        """Start the websocket client for the device."""
        device_info = hass.data[DOMAIN][entry.entry_id]
        host = device_info["host"]

        uri = f"ws://{host}:3000/live"

        while True:
            try:
                # Set device as unavailable when attempting to connect
                await set_device_availability(available=False)

                async with websockets.connect(uri) as websocket:
                    device_info["ws_client"] = websocket
                    _LOGGER.info("Connected to %s", uri)

                    # Set device as available since connection is established
                    await set_device_availability(available=True)

                    # Send login message immediately after connection
                    login_message = {"type": "login", "value": ""}
                    await websocket.send(json.dumps(login_message))
                    _LOGGER.debug("Sent login message: %s", login_message)

                    # Listen for messages from the device
                    while True:
                        try:
                            message = await websocket.recv()

                            _LOGGER.debug("Received message: %s", message)
                            # Process the message and update entity states
                            match message:
                                case bytes():
                                    await process_message(
                                        hass, entry.entry_id, message.decode("utf-8")
                                    )
                                case str():
                                    await process_message(hass, entry.entry_id, message)

                        except websockets.exceptions.ConnectionClosed:
                            _LOGGER.warning("Connection closed to %s", uri)
                            # Set device as unavailable when connection is lost
                            await set_device_availability(available=False)
                            break

            except (OSError, websockets.exceptions.WebSocketException):
                _LOGGER.exception("Failed to connect to %s", uri)
                device_info["ws_client"] = None
                # Set device as unavailable when connection attempt fails
                await set_device_availability(available=False)

            # Wait before trying to reconnect
            await asyncio.sleep(30)

    async def set_device_availability(*, available: bool) -> None:
        """Set the availability of all entities for this device."""
        device_info = hass.data[DOMAIN][entry.entry_id]

        # Only update if state changes to avoid unnecessary updates
        if device_info["available"] != available:
            device_info["available"] = available
            _LOGGER.debug(
                "Setting %s availability to %s", device_info["name"], available
            )

            # Update all entities for this device
            for entity in device_info["entities"]:
                if hasattr(entity, "set_available"):
                    entity.set_available(available)

    async def stop_websocket_client(_event: Event) -> None:
        """Stop the websocket client."""
        device_info = hass.data[DOMAIN][entry.entry_id]
        if device_info["ws_task"] is not None:
            device_info["ws_task"].cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await device_info["ws_task"]

        if device_info["ws_client"] is not None:
            await device_info["ws_client"].close()
            device_info["ws_client"] = None

        # Set device as unavailable when stopping
        await set_device_availability(available=False)

    # Start websocket client
    device_info["ws_task"] = asyncio.create_task(start_websocket_client())

    # Register stop callback
    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, stop_websocket_client)

    return True


async def process_message(hass: HomeAssistant, entry_id: str, message: str) -> None:
    """Process a message from the device."""
    try:
        data = json.loads(message)
        device_info = hass.data[DOMAIN][entry_id]
        device_type = entry_id in hass.data[DOMAIN] and hass.data[DOMAIN][entry_id].get(
            "type"
        )

        # Handle reset message - device wants to be removed
        if data.get("type") == "device_reset":
            device_name = device_info.get("name", "Unknown device")
            _LOGGER.info(
                "Received reset request from %s. Removing device from Home Assistant.",
                device_name,
            )

            # Schedule the removal to avoid conflicts with the current websocket task
            hass.async_create_task(async_remove_entry(hass, entry_id))
            return

        # Handle state updates
        if data.get("type") == "state":
            state_value = float(data.get("value", 0))

            # Find the entity directly from the device_info
            entity = None
            if device_type == "switch":
                entity_id = f"switch.{device_info['name']}".lower().replace(" ", "_")
                entity = hass.data[DOMAIN].get(entity_id)

                # For switches, convert to boolean
                is_on = bool(state_value)

                if entity is not None:
                    entity.handle_state_update(is_on)
                    _LOGGER.debug(
                        "Updated switch %s state to %s", device_info["name"], is_on
                    )

            elif device_type == "light":
                entity_id = f"light.{device_info['name']}".lower().replace(" ", "_")
                entity = hass.data[DOMAIN].get(entity_id)

                if entity is not None:
                    # For lights, pass the numeric brightness value (0-1)
                    # The entity will handle the conversion to HA brightness
                    entity.handle_state_update(state_value)
                    _LOGGER.debug(
                        "Updated light %s brightness to %s",
                        device_info["name"],
                        state_value,
                    )

            if entity is None:
                _LOGGER.warning("Couldn't find entity for %s", device_info["name"])

    except json.JSONDecodeError:
        _LOGGER.exception("Invalid JSON received: %s", message)
    except Exception:
        _LOGGER.exception("Error processing message")


async def async_remove_entry(hass: HomeAssistant, entry_id: str) -> None:
    """Remove a config entry when requested by the device."""
    # Find the entry by its ID
    entries = hass.config_entries.async_entries(DOMAIN)
    entry = next((entry for entry in entries if entry.entry_id == entry_id), None)

    if entry:
        _LOGGER.info(
            "Removing config entry for %s", entry.data.get(CONF_NAME, "Unknown device")
        )
        await hass.config_entries.async_remove(entry.entry_id)
    else:
        _LOGGER.warning("Could not find entry with ID %s to remove", entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    device_info = hass.data[DOMAIN][entry.entry_id]

    # Stop the websocket client
    if device_info["ws_task"] is not None:
        device_info["ws_task"].cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await device_info["ws_task"]

    if device_info["ws_client"] is not None:
        await device_info["ws_client"].close()

    # Determine which platform to unload
    device_type = entry.data[CONF_TYPE]
    platforms = []

    if device_type == "switch":
        platforms.append("switch")
    elif device_type == "light":
        platforms.append("light")

    # Unload the platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, platforms)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
