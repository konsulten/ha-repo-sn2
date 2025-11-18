from collections.abc import Callable
import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, SIGNAL_STRENGTH_DECIBELS_MILLIWATT
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from custom_components.systemnexa2.entity import SystemNexa2Entity
from custom_components.systemnexa2.helpers import SystemNexa2ConfigEntry
from sn2.device import Device, OnOffSetting

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: SystemNexa2ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up lights based on a config entry."""
    device = entry.runtime_data.device
    entities = []
    info = device.info_data
    if info:
        if info.wifi_dbm is not None:
            entities.append(
                SensorValue(
                    device=entry.runtime_data.device,
                    device_info=entry.runtime_data.device_info,
                    unique_id=f"sensor-wifi-dbm",
                    name="Wifi",
                    entry_id=entry.entry_id,
                    entity_description=SensorEntityDescription(
                        key=f"sensor-wifi-dbm",
                        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
                        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
                        state_class=SensorStateClass.MEASUREMENT,
                        entity_category=EntityCategory.DIAGNOSTIC,
                    ),
                    # device_class=SensorDeviceClass.SIGNAL_STRENGTH,
                    # state_class=SensorStateClass.MEASUREMENT,
                    #
                    # value=info.wifi_dbm,
                    # entity_category=EntityCategory.DIAGNOSTIC,
                )
            )

    entry.runtime_data.config_entries.extend(entities)
    async_add_entities(entities)


class SensorValue(SystemNexa2Entity, SensorEntity):
    """Configuration switch entity for SystemNexa2 devices."""

    def __init__(
        self,
        device: Device,
        device_info: DeviceInfo,
        name: str,
        entry_id: str,
        unique_id: str,
        # value: str | int | float,
        entity_description: SensorEntityDescription,
    ) -> None:
        """Initialize the configuration switch."""
        super().__init__(
            device,
            entry_id=entry_id,
            unique_entity_id=unique_id,
            device_info=device_info,
            name=name,
        )
        self.entity_description = entity_description
        self._attr_translation_key = name

    @callback
    def handle_state_update(self, value) -> None:
        self._attr_native_value = value
        self.async_write_ha_state()
