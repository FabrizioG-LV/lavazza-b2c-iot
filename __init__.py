"""The lavazza_b2c_iot integration."""

import asyncio
import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval

from .api import ApiClient
from .catalog import set_catalog_data
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_API_ENDPOINTS,
    CONF_CATALOGS,
    CONF_CLIENT_SECRET,
    CONF_COUNTRY,
    CONF_EMAIL,
    CONF_INSTALLATION_ID,
    CONF_PASSWORD,
    CONF_UID,
    COORDINATOR_DEVICE_LIST,
    COORDINATOR_DEVICE_STATE,
    DOMAIN,
)
from .coordinator import ApiCoordinator
from .fcm_client import FcmPushManager
from .poll_config import build_poll_config

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "button"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
  """Set up config entry.

  Creates API client and coordinators from poll_config registry.
  """
  token = entry.data.get(CONF_ACCESS_TOKEN, "")
  country = entry.data.get(CONF_COUNTRY, "IT")
  endpoints = entry.data.get(CONF_API_ENDPOINTS, {})
  email = entry.data.get(CONF_EMAIL, "")
  uid = entry.data.get(CONF_UID, "")
  password = entry.data.get(CONF_PASSWORD, "")
  installation_id = entry.data.get(CONF_INSTALLATION_ID, "")
  client_secret = entry.data.get(CONF_CLIENT_SECRET, "")

  session = async_get_clientsession(hass)
  api_client = ApiClient(
      token=token,
      session=session,
      endpoints=endpoints,
      country=country,
      installation_id=installation_id,
      client_secret=client_secret,
  )

  # Build poll config with API client closures
  poll_config = build_poll_config(api_client)

  # Instantiate all coordinators from poll_config
  coordinators: dict[str, ApiCoordinator] = {}
  for name, poll_cfg in poll_config.items():
    coordinator = ApiCoordinator(
        hass,
        name=f"{DOMAIN}_{name}",
        interval=poll_cfg.interval,
        fetch=poll_cfg.fetch,
    )
    coordinators[name] = coordinator

  # Wire device_state and device_errors to read from device_list coordinator
  device_list_coordinator = coordinators.get("device_list")
  if device_list_coordinator:
    from .device_fetchers import fetch_all_device_states, fetch_all_device_errors

    async def fetch_device_states_with_list() -> dict[str, Any]:
      devices = device_list_coordinator.data or {}
      return await fetch_all_device_states(api_client, devices)

    async def fetch_device_errors_with_list() -> dict[str, Any]:
      devices = device_list_coordinator.data or {}
      return await fetch_all_device_errors(api_client, devices)

    if "device_state" in coordinators:
      coordinators["device_state"]._fetch = fetch_device_states_with_list
    if "device_errors" in coordinators:
      coordinators["device_errors"]._fetch = fetch_device_errors_with_list

  # Schedule first refresh for all coordinators in parallel
  await asyncio.gather(
      *[
          coordinator.async_config_entry_first_refresh()
          for coordinator in coordinators.values()
      ]
  )

  # Fetch catalogs from worker for each model in device list
  catalogs: dict[str, dict] = {}
  try:
    device_list_data = device_list_coordinator.data if device_list_coordinator else {}
    model_codes = set()
    for device in device_list_data.values():
      model_code = device.get("model")
      if model_code:
        model_codes.add(model_code)

    # Fetch each unique model's catalog
    for model_code in model_codes:
      try:
        catalog_data = await api_client.get_catalogs(model_code)
        catalogs[model_code] = catalog_data
        _LOGGER.debug("Fetched catalog for model %s", model_code)
      except Exception as e:
        _LOGGER.warning("Failed to fetch catalog for %s: %s", model_code, e)
        # Continue — catalog loading will fallback to local JSON if needed
  except Exception as e:
    _LOGGER.warning("Failed to fetch catalogs: %s", e)

  # Store catalogs in config entry and populate cache
  if catalogs:
    entry.data[CONF_CATALOGS] = catalogs
    set_catalog_data(catalogs)
    _LOGGER.debug("Loaded %d catalogs from worker", len(catalogs))

  # Store coordinators and api_client in entry runtime data
  entry.runtime_data = {"coordinators": coordinators, "api_client": api_client}

  # Set up FCM push receiver for real-time device state updates
  device_state_coordinator = coordinators.get(COORDINATOR_DEVICE_STATE)
  if device_state_coordinator:

    def on_fcm_notification(parsed_payload: dict) -> None:
      """Handle FCM notification by updating device state coordinator.

      Args:
        parsed_payload: {
          "device_serial": dsn,
          "action": "livedatastate" | "makecoffee" | "descaling",
          "status_code": <int>,
          "raw_payload": {...}
        }
      """
      try:
        device_serial = parsed_payload.get("device_serial")
        action = parsed_payload.get("action")
        status_code = parsed_payload.get("status_code")

        if not device_serial or not device_state_coordinator.data:
          _LOGGER.debug("FCM update skipped (no device_serial or coordinator data)")
          return

        devices = device_state_coordinator.data
        device = devices.get(device_serial)
        if not device:
          _LOGGER.warning("FCM update: device %s not found in coordinator data", device_serial)
          return

        # Update device state based on action type
        if action == "livedatastate":
          device.state_code = status_code
        elif action == "makecoffee":
          device.makecoffee_status = status_code
        elif action == "descaling":
          device.descaling_status = status_code
        else:
          _LOGGER.warning("FCM update: unknown action %s for device %s", action, device_serial)
          return

        # Notify coordinator of updated data
        device_state_coordinator.async_set_updated_data(devices)
        _LOGGER.debug(
            "FCM update: device %s action %s status %s", device_serial, action, status_code
        )
      except Exception as e:
        _LOGGER.error("Error processing FCM notification: %s", e)

    fcm_manager = FcmPushManager(hass, entry)
    try:
      await fcm_manager.async_start(on_notification=on_fcm_notification)
      entry.async_on_unload(fcm_manager.async_stop)
    except Exception as e:
      _LOGGER.error("Failed to start FCM manager: %s", e)

  # Schedule periodic token validation every 24 hours
  async def async_check_token_validity() -> None:
    """Check if token is still valid; refresh if needed."""
    try:
      is_valid = await api_client.check_token_valid(email, uid)
      if is_valid:
        _LOGGER.debug("Token still valid for %s", email)
        return

      _LOGGER.warning("Token expired for %s; refreshing...", email)
      # Token is invalid, refresh by calling broker
      try:
        from .config_flow import YourDomainNameConfigFlow

        flow = YourDomainNameConfigFlow()
        token_response = await flow._get_token(
            "https://your-broker-url.workers.dev", country, email, password
        )

        # Update config entry with new token
        new_data = {
            **entry.data,
            CONF_ACCESS_TOKEN: token_response["access_token"],
            CONF_UID: token_response["uid"],
        }
        hass.config_entries.async_update_entry(entry, data=new_data)
        _LOGGER.info("Token refreshed for %s", email)

        # Update API client token (next request will use it)
        api_client.token = token_response["access_token"]

      except Exception as e:
        _LOGGER.error("Failed to refresh token for %s: %s", email, e)
    except Exception as e:
      _LOGGER.error("Token validity check failed for %s: %s", email, e)

  # Schedule check every 24 hours
  entry.async_on_unload(
      async_track_time_interval(
          hass,
          async_check_token_validity,
          interval=timedelta(hours=24),
      )
  )

  # Forward to platform setups
  await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

  return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
  """Unload config entry."""
  unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
  if unload_ok:
    entry.runtime_data = None
  return unload_ok
