"""Config flow for the SystemNexa2 integration."""

import logging
from typing import Any

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
    CONF_TYPE,
)
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from . import DOMAIN, LIGHT_MODELS, PLUG_MODELS, SWITCH_MODELS

_LOGGER = logging.getLogger(__name__)


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
        """Handle zeroconf discovery and automatically set up the device."""
        # Extract device information
        host = discovery_info.host
        name = discovery_info.name.split(".")[0]
        properties = discovery_info.properties

        # Check if this is a supported device
        if "model" not in properties:
            _LOGGER.warning(
                "Device %s at %s missing model information in mDNS record", name, host
            )
            return self.async_abort(reason="not_supported")

        model = properties["model"]

        # Verify model is in our supported lists
        if (
            model not in SWITCH_MODELS
            and model not in LIGHT_MODELS
            and model not in PLUG_MODELS
        ):
            _LOGGER.warning(
                "Device %s at %s has unsupported model: %s", name, host, model
            )
            return self.async_abort(reason="unsupported_model")

        # Check firmware version requirement
        if "version" not in properties:
            _LOGGER.warning(
                "Device %s at %s doesn't advertise firmware version - skipping",
                name,
                host,
            )
            return self.async_abort(reason="firmware_version_missing")

        # Version check - require at least 0.9.5
        device_version = properties["version"]
        if not self._is_version_compatible(device_version, min_version="0.9.5"):
            _LOGGER.warning(
                (
                    "Device %s at %s has incompatible firmware version %s "
                    "(min required: 0.9.5)"
                ),
                name,
                host,
                device_version,
            )
            return self.async_abort(reason="firmware_version_incompatible")

        device_id = properties.get("id", name)

        # Determine device type based on model
        if model in SWITCH_MODELS:
            device_type = "switch"
        if model in PLUG_MODELS:
            device_type = "switch"
        elif model in LIGHT_MODELS:
            device_type = "light"
        else:
            return self.async_abort(reason="not_supported")

        # Set unique ID and check if already configured
        await self.async_set_unique_id(device_id)
        self._abort_if_unique_id_configured(updates={CONF_HOST: host})

        # Log the discovered device
        _LOGGER.info(
            "Automatically configuring discovered %s: %s (%s) at %s",
            device_type,
            name,
            model,
            host,
        )

        # Automatically create the config entry without any user interaction
        return self.async_create_entry(
            title=f"{name} ({model})",
            data={
                CONF_HOST: host,
                CONF_NAME: name,
                CONF_MODEL: model,
                CONF_DEVICE_ID: device_id,
                CONF_TYPE: device_type,
            },
        )

    def _is_version_compatible(self, version: str, min_version: str) -> bool:
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
