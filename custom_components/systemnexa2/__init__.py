"""The System Nexa 2 integration."""

from decimal import Decimal
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
from custom_components.systemnexa2.sensor import SensorValue
from custom_components.systemnexa2.switch import ConfigurationSwitch, SN2SwitchPlug
from sn2.device import (
    ConnectionStatus,
    Device,
    InformationUpdate,
    OnOffSetting,
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
PLATFORMS: Final = [Platform.SWITCH, Platform.LIGHT, Platform.SENSOR]


async def async_setup(hass: HomeAssistant, _config: ConfigType) -> bool:
    """Set up the component from configuration.yaml."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: SystemNexa2ConfigEntry) -> bool:
    """Set up from a config entry."""
    entry_process_update = partial(_process_update, entry)
    device = Device(host=entry.data[CONF_HOST], on_update=entry_process_update)
    await device.initialize()
    if device.info_data is None:
        return False  # TODO
    # Store device info
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        manufacturer="NEXA",
        name=device.info_data.name,
        model=device.info_data.model,
        sw_version=device.info_data.sw_version,
        hw_version=str(device.info_data.hw_version),
    )
    device_info = DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        manufacturer="NEXA",
        name=device.info_data.name,
        model=device.info_data.model,
        sw_version=device.info_data.sw_version,
        hw_version=str(device.info_data.hw_version),
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
            for entity in entry.runtime_data.config_entries:
                if isinstance(entity, ConfigurationSwitch):
                    for setting in settings:
                        if (
                            isinstance(setting, OnOffSetting)
                            and entity.name == setting.name
                        ):
                            entity.handle_state_update(is_on=setting.is_enabled())
        case InformationUpdate(information):
            for entity in entry.runtime_data.config_entries:
                if isinstance(entity, SensorValue):
                    if entity.name == "Wifi":
                        entity.handle_state_update(information.wifi_dbm)
                pass  # TODO


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
