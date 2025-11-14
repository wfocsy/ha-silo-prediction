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
    await hass.helpers.discovery.async_load_platform(
        "sensor", DOMAIN, {}, config # Pass the full config if needed by sensor.py
    )

    return True

# No unload function is needed since this integration does not use config entries or config_flow.# No unload function is needed since this integration does not use config entries or config_flow.
# If you later add an unload function, use logger formatting like:
# _LOGGER.debug("Unloading platform %s for Silo Prediction.", platform)