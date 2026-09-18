"""Diagnostics support for lavazza_b2c_iot."""

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_ACCESS_TOKEN,
    CONF_CLIENT_SECRET,
    CONF_EMAIL,
    CONF_FCM_CREDENTIALS,
    CONF_FIREBASE_API_KEY,
    CONF_INSTALLATION_ID,
    CONF_PASSWORD,
    CONF_UID,
)

TO_REDACT = {
    CONF_PASSWORD,
    CONF_ACCESS_TOKEN,
    CONF_UID,
    CONF_INSTALLATION_ID,
    CONF_CLIENT_SECRET,
    CONF_FIREBASE_API_KEY,
    CONF_FCM_CREDENTIALS,
    CONF_EMAIL,
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
  """Return diagnostics for a config entry."""
  return {
      "entry_data": async_redact_data(entry.data, TO_REDACT),
  }
