"""The System Nexa 2 integration."""

import logging
from functools import partial
from typing import Final

import voluptuous as vol
from homeassistant.const import (
    CONF_HOST,
    CONF_NAME,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.typing import ConfigType

from custom_components.systemnexa2.light import SN2Light
from custom_components.systemnexa2.switch import SN2SwitchPlug
from sn2.device import (
    ConnectionStatus,
    Device,
    SettingsUpdate,
    StateChange,
    UpdateEvent,
)

from .helpers import NexaSystem2RuntimeData, SystemNexa2ConfigEntry

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
PLATFORMS: Final = [
    Platform.SWITCH,
    Platform.LIGHT,
]


async def async_setup(hass: HomeAssistant, _config: ConfigType) -> bool:
    """Set up the component from configuration.yaml."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: SystemNexa2ConfigEntry) -> bool:
    """Set up from a config entry."""
    entry_process_update = partial(_process_update, entry)
    device = Device(host=entry.data[CONF_HOST], on_update=entry_process_update)
    info = await device.get_info()

    if info is None:
        return False

    # Store device info
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        manufacturer="NEXA",
        name=info.information.name,
        model=info.information.model,
        sw_version=info.information.sw_version,
        hw_version=str(info.information.hw_version),
    )
    device_info = DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        manufacturer="NEXA",
        name=info.information.name,
        model=info.information.model,
        sw_version=info.information.sw_version,
        hw_version=str(info.information.hw_version),
    )
    entry.runtime_data = NexaSystem2RuntimeData(device=device, device_info=device_info)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await device.connect()

    return True


async def _process_update(
    entry: SystemNexa2ConfigEntry, update_event: UpdateEvent
) -> None:
    match update_event:
        case ConnectionStatus(connected):
            _LOGGER.info("conn %s, %s ", connected, entry.as_dict())
            for entity in entry.runtime_data.config_entries:
                _LOGGER.info("avail %s,", entity.name)
                if entity.available != connected:
                    entity.available = connected
                    entity.async_write_ha_state()
        case StateChange(state):
            main_entry = entry.runtime_data.main_entry
            _LOGGER.info("state %s,", state)
            match main_entry:
                case SN2Light():
                    main_entry.handle_state_update(state)
                case SN2SwitchPlug():
                    main_entry.handle_state_update(state=bool(state))
        case SettingsUpdate(settings):
            main_entry = entry.runtime_data.main_entry
            if settings.disable_433 != main_entry:
                pass


async def async_remove_entry(
    hass: HomeAssistant, entry: SystemNexa2ConfigEntry
) -> None:
    """Remove a config entry when requested by the device."""
    # Find the entry by its ID
    if entry:
        _LOGGER.info(
            "Removing config entry for %s", entry.data.get(CONF_NAME, "Unknown device")
        )
        await hass.config_entries.async_remove(entry.entry_id)
    else:
        _LOGGER.warning("Could not find entry with ID %s to remove", entry.entry_id)


async def async_unload_entry(
    hass: HomeAssistant, entry: SystemNexa2ConfigEntry
) -> bool:
    """Unload a config entry."""
    if entry.runtime_data.device:
        _LOGGER.info("Unload")
        await entry.runtime_data.device.disconnect()

    # Unload the platforms
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
