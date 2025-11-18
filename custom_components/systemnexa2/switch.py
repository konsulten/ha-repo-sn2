"""Switch entity for the SystemNexa2 integration."""

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from custom_components.systemnexa2.entity import SystemNexa2Entity
from custom_components.systemnexa2.helpers import SystemNexa2ConfigEntry
from sn2.device import Device

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: SystemNexa2ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up lights based on a config entry."""
    device = entry.runtime_data.device
    entities = []
    if device.settings.can_disable_433mhz():
        entities.append(
            ConfigurationSwitch(
                device=entry.runtime_data.device,
                device_info=entry.runtime_data.device_info,
                unique_id="enable-433",
                name="433Mhz",
                entry_id=entry.entry_id,
            )
        )
    if device.settings.can_disable_led():
        entities.append(
            ConfigurationSwitch(
                device=entry.runtime_data.device,
                device_info=entry.runtime_data.device_info,
                unique_id="Led",
                name="led",
                entry_id=entry.entry_id,
            )
        )

    entry.runtime_data.config_entries.extend(entities)
    if not device.dimmable:
        entry.runtime_data.main_entry = SN2SwitchPlug(
            device=device,
            device_info=entry.runtime_data.device_info,
            entry_id=entry.entry_id,
        )
        entities.append(entry.runtime_data.main_entry)
    async_add_entities(entities)


class ConfigurationSwitch(SystemNexa2Entity, SwitchEntity):
    """Configuration switch entity for SystemNexa2 devices."""

    def __init__(
        self,
        device: Device,
        device_info: DeviceInfo,
        name: str,
        entry_id: str,
        unique_id: str,
    ) -> None:
        """
        Initialize the configuration switch.

        Args:
            device: The SystemNexa2 device instance.
            device_info: Device registry information.
            name: The name of the switch.
            entry_id: The config entry ID.
            unique_id: The unique identifier for this entity.

        """
        super().__init__(
            device,
            entry_id=entry_id,
            unique_entity_id=unique_id,
            device_info=device_info,
            name=name,
        )
        self.entity_description = SwitchEntityDescription(key=unique_id)
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_translation_key = name

    async def async_turn_on(self, **_kwargs: Any) -> None:
        """Turn on the light."""
        await self._device.turn_on()

    async def async_turn_off(self, **_kwargs: Any) -> None:
        """Turn off the light."""
        await self._device.turn_off()


class SN2SwitchPlug(SystemNexa2Entity, SwitchEntity):
    """Representation of a Light."""

    def __init__(self, device: Device, device_info: DeviceInfo, entry_id: str) -> None:
        """Initialize the light."""
        super().__init__(
            device,
            entry_id=entry_id,
            unique_entity_id="switch1",
            name="Switch",
            device_info=device_info,
        )

        self._attr_available = True

    async def async_turn_on(self, **_kwargs: Any) -> None:
        """Turn on the light."""
        await self._device.turn_on()

    async def async_turn_off(self, **_kwargs: Any) -> None:
        """Turn off the light."""
        await self._device.turn_off()

    async def async_toggle(self, **_kwargs: Any) -> None:
        """Toggle the light."""
        await self._device.toggle()

    @callback
    def handle_state_update(self, *, state: bool) -> None:
        """Handle state updates from the device."""
        if self._attr_is_on != state:
            self._attr_is_on = state
            self.async_write_ha_state()
