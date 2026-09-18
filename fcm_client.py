"""Push notification receiver for real-time device state updates."""

import asyncio
import logging
from typing import Any, Callable, Optional

from firebase_messaging import FcmPushClient, FcmRegisterConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_APP_PACKAGE_NAME,
    CONF_FCM_CONFIG,
    CONF_FCM_CREDENTIALS,
    CONF_FIREBASE_API_KEY,
    CONF_FIREBASE_APP_ID,
    CONF_FIREBASE_PROJECT_ID,
    CONF_FIREBASE_SENDER_ID,
)

_LOGGER = logging.getLogger(__name__)


class FcmPushManager:
  """Manage push notifications for device state updates."""

  def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Initialize push manager."""
    self.hass = hass
    self.entry = entry
    self._fcm_client: Optional[FcmPushClient] = None

  async def async_start(
      self,
      on_notification: Callable[[dict[str, Any]], None],
  ) -> None:
    """Start push receiver.

    Args:
      on_notification: Callback fired when a push notification arrives.
        Receives the decoded payload dict.
    """
    try:
      # Get push config from entry data (populated by config_flow from broker)
      fcm_config_dict = self.entry.data.get(CONF_FCM_CONFIG, {})
      if not fcm_config_dict:
        _LOGGER.error("FCM config not found in entry data")
        return

      # Load saved credentials if they exist (from previous checkin).
      # FcmPushClient's `credentials` param is a plain dict, not a wrapper
      # object — there's no Credentials class in the installed library.
      credentials: Optional[dict[str, Any]] = self.entry.data.get(CONF_FCM_CREDENTIALS) or None

      # Build FcmRegisterConfig from entry data. bundle_id must be the real
      # app package name — FcmRegisterConfig defaults it to a generic
      # "receiver.push.com" placeholder, which doesn't match the configured
      # project/API key and would break registration if left unset.
      fcm_register_config = FcmRegisterConfig(
          project_id=fcm_config_dict.get(CONF_FIREBASE_PROJECT_ID, ""),
          app_id=fcm_config_dict.get(CONF_FIREBASE_APP_ID, ""),
          api_key=fcm_config_dict.get(CONF_FIREBASE_API_KEY, ""),
          messaging_sender_id=fcm_config_dict.get(CONF_FIREBASE_SENDER_ID, ""),
          bundle_id=fcm_config_dict.get(CONF_APP_PACKAGE_NAME, "receiver.push.com"),
      )

      # Create push client
      self._fcm_client = FcmPushClient(
          callback=self._on_notification_callback(on_notification),
          fcm_config=fcm_register_config,
          credentials=credentials,
          credentials_updated_callback=self._on_credentials_updated,
      )

      # Register or checkin. checkin_or_register/start are
      # asyncio-native (the library schedules its own background listen +
      # heartbeat-monitor tasks internally) — must be awaited directly, not
      # run via async_add_executor_job (that's for blocking sync calls; on
      # an `async def` it just builds a coroutine object without ever
      # running it, so nothing happens and no exception is raised either).
      _LOGGER.debug("Registering/checking in with FCM")
      await self._fcm_client.checkin_or_register()
      await self._fcm_client.start()
      _LOGGER.info("FCM push receiver started")

    except Exception as e:
      _LOGGER.error("Failed to start FCM push receiver: %s", e)
      raise

  async def async_stop(self) -> None:
    """Stop push receiver and clean up."""
    if self._fcm_client:
      try:
        await self._fcm_client.stop()
        _LOGGER.info("FCM push receiver stopped")
      except Exception as e:
        _LOGGER.error("Error stopping FCM client: %s", e)
      self._fcm_client = None

  def _on_notification_callback(
      self, on_notification: Callable[[dict[str, Any]], None]
  ) -> Callable[[dict[str, Any], str, Any], None]:
    """Create notification callback that parses payload and updates coordinator.

    The push library invokes this as callback(notification_dict, persistent_id,
    callback_context) — notification_dict is already the decrypted/parsed JSON
    payload, no object-to-dict conversion needed.

    Payload format:
      {
        "dsn": "18000498_0000002108S001007676",
        "updateStatus": {
          "action": "livedatastate" | "makecoffee" | "descaling",
          "status": <int>
        },
        ...
      }
    """

    def callback(payload: dict[str, Any], persistent_id: str, context: Any) -> None:
      try:
        _LOGGER.debug("Received FCM notification: %s", payload)

        # Parse payload
        dsn = payload.get("dsn")
        update_status = payload.get("updateStatus", {})
        action = update_status.get("action")
        status_code = update_status.get("status")

        if not dsn or not action or status_code is None:
          _LOGGER.warning(
              "Skipping incomplete FCM payload (missing dsn/action/status): %s",
              payload,
          )
          return

        # Normalized payload for coordinator update
        parsed = {
            "device_serial": dsn,
            "action": action,
            "status_code": status_code,
            "raw_payload": payload,
        }

        on_notification(parsed)

      except Exception as e:
        _LOGGER.error("Error processing FCM notification: %s", e)

    return callback

  def _on_credentials_updated(self, credentials: dict[str, Any]) -> None:
    """Save updated push credentials to config entry.

    Called by the push library when new credentials are obtained.
    Saves them so we don't need to re-register a new Instance ID on restart.

    credentials is the library's own {"keys":..., "gcm":..., "fcm":...,
    "config":...} dict — stored as-is, since checkin_or_register() reads
    credentials["gcm"]["android_id"]/["security_token"] specifically on
    next start; picking out individual fields would lose what it needs.
    """

    async def save_credentials() -> None:
      try:
        self.hass.config_entries.async_update_entry(
            self.entry,
            data={**self.entry.data, CONF_FCM_CREDENTIALS: credentials},
        )
        _LOGGER.debug("FCM credentials saved to entry")
      except Exception as e:
        _LOGGER.error("Failed to save FCM credentials: %s", e)

    # Schedule credential save as a task
    asyncio.create_task(save_credentials())
