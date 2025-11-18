"""Config flow for the SystemNexa2 integration."""

import logging
from typing import Any

from attr import dataclass
from homeassistant.config_entries import (
    CONN_CLASS_LOCAL_PUSH,
    ConfigFlow,
    ConfigFlowResult,
)
from homeassistant.const import (
    CONF_DEVICE_ID,
    CONF_HOST,
    CONF_MODEL,
    CONF_NAME,
)
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

import sn2
import sn2.device

from . import DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclass
class _DiscoveryInfo:
    name: str
    host: str
    model: str | None
    device_id: str | None
    device_version: str | None


class SN2ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the devices."""

    VERSION = 1

    # This integration creates config entries automatically from discovery
    # and doesn't require any user interaction
    CONNECTION_CLASS = CONN_CLASS_LOCAL_PUSH

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovered_devices = {}

    async def async_step_user(
        self, _user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle user-initiated flow but don't actually show any UI."""
        # This will be called if the user adds the integration manually,
        # but we want all setup to be automatic, so just return to show
        # that setup is complete.
        return self.async_abort(reason="already_auto_configured")

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        """Handle zeroconf discovery."""
        # Extract device information
        self._discovered_device = _DiscoveryInfo(
            name=discovery_info.name.split(".")[0],
            host=discovery_info.host,
            device_id=discovery_info.properties.get("id"),
            model=discovery_info.properties.get("model"),
            device_version=discovery_info.properties.get("version"),
        )
        # Check if device model and version are supported
        if not sn2.device.Device.is_device_supported(
            model=self._discovered_device.model,
            device_version=self._discovered_device.device_version,
        ):
            return self.async_abort(reason="unsupported_model")
        # Set unique ID and check if already configured
        await self.async_set_unique_id(self._discovered_device.device_id)
        # Update host if device is already configured
        self._abort_if_unique_id_configured(
            updates={CONF_HOST: discovery_info.host}
        )

        # Log the discovered device
        _LOGGER.info(
            "Automatically configuring discovered %s: %s at %s",
            # device_type,
            self._discovered_device.name,
            self._discovered_device.model,
            self._discovered_device.host,
        )
        self.context["title_placeholders"] = {
            "name": self._discovered_device.name,
            "model": self._discovered_device.model or "",
        }
        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm discovery."""
        if user_input is not None:
            device_name = self._discovered_device.name
            device_model = self._discovered_device.model
            return self.async_create_entry(
                title=f"{device_name} ({device_model})",
                data={
                    CONF_HOST: self._discovered_device.host,
                    CONF_NAME: self._discovered_device.name,
                    CONF_MODEL: self._discovered_device.model,
                    CONF_DEVICE_ID: self._discovered_device.device_id,
                },
            )
        self._set_confirm_only()
        return self.async_show_form(
            step_id="discovery_confirm",
            description_placeholders={"name": self._discovered_device.name},
        )
