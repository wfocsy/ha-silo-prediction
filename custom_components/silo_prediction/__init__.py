"""The Silo Prediction Integration."""
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

DOMAIN = "silo_prediction"

_LOGGER = logging.getLogger(__name__)

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Silo Prediction component."""
    _LOGGER.debug("Setting up Silo Prediction integration via YAML config.")

    hass.data.setdefault(DOMAIN, {})

    # Load sensor platform
    hass.async_create_task(
        hass.helpers.discovery.async_load_platform(
            "sensor", DOMAIN, {}, config # Pass the full config if needed by sensor.py
        )
    )

    return True

async def async_unload_platform(hass: HomeAssistant, config: ConfigType, platform: str) -> bool:
    """Unload a platform."""
    _LOGGER.debug(f"Unloading platform {platform} for Silo Prediction.")
    # Implement additional unload logic if necessary for other platforms later
    return True