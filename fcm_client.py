"""Firebase Cloud Messaging push receiver for real-time device state updates."""

import asyncio
import logging
from typing import Any, Callable, Optional

from firebase_messaging import (
    Credentials,
    FcmPushClient,
    FcmRegisterConfig,
    NotificationCallback,
)
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
  """Manage Firebase Cloud Messaging push notifications for device state updates."""

  def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Initialize FCM manager."""
    self.hass = hass
    self.entry = entry
    self._fcm_client: Optional[FcmPushClient] = None
    self._task: Optional[asyncio.Task[None]] = None

  async def async_start(
      self,
      on_notification: Callable[[dict[str, Any]], None],
  ) -> None:
    """Start FCM push receiver.

    Args:
      on_notification: Callback fired when a push notification arrives.
        Receives the decoded payload dict.
    """
    try:
      # Get FCM config from entry data (populated by config_flow from broker)
      fcm_config_dict = self.entry.data.get(CONF_FCM_CONFIG, {})
      if not fcm_config_dict:
        _LOGGER.error("FCM config not found in entry data")
        return

      # Load saved credentials if they exist (from previous checkin)
      saved_credentials = self.entry.data.get(CONF_FCM_CREDENTIALS)
      credentials: Optional[Credentials] = None
      if saved_credentials:
        try:
          credentials = Credentials(**saved_credentials)
        except Exception as e:
          _LOGGER.warning("Failed to load saved FCM credentials: %s", e)
          credentials = None

      # Build FcmRegisterConfig from entry data
      fcm_register_config = FcmRegisterConfig(
          project_id=fcm_config_dict.get(CONF_FIREBASE_PROJECT_ID, ""),
          app_id=fcm_config_dict.get(CONF_FIREBASE_APP_ID, ""),
          api_key=fcm_config_dict.get(CONF_FIREBASE_API_KEY, ""),
          messaging_sender_id=fcm_config_dict.get(CONF_FIREBASE_SENDER_ID, ""),
      )

      # Create FCM push client
      self._fcm_client = FcmPushClient(
          callback=self._on_notification_callback(on_notification),
          fcm_config=fcm_register_config,
          credentials=credentials,
          credentials_updated_callback=self._on_credentials_updated,
      )

      # Register or checkin with FCM
      _LOGGER.debug("Registering/checking in with FCM")
      await self.hass.async_add_executor_job(
          self._fcm_client.checkin_or_register
      )

      # Start receiving push notifications in background
      self._task = self.hass.async_create_background_task(
          self._run_fcm_receiver(),
          name="fcm_push_receiver",
      )
      _LOGGER.info("FCM push receiver started")

    except Exception as e:
      _LOGGER.error("Failed to start FCM push receiver: %s", e)
      raise

  async def async_stop(self) -> None:
    """Stop FCM push receiver and clean up."""
    if self._task:
      self._task.cancel()
      try:
        await self._task
      except asyncio.CancelledError:
        pass
      self._task = None

    if self._fcm_client:
      try:
        await self.hass.async_add_executor_job(self._fcm_client.stop)
        _LOGGER.info("FCM push receiver stopped")
      except Exception as e:
        _LOGGER.error("Error stopping FCM client: %s", e)
      self._fcm_client = None

  def _on_notification_callback(
      self, on_notification: Callable[[dict[str, Any]], None]
  ) -> NotificationCallback:
    """Create notification callback that parses payload and updates coordinator.

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

    def callback(obj: Any, notification: Any) -> None:
      try:
        # Convert notification to dict
        if hasattr(notification, "__dict__"):
          payload = notification.__dict__
        else:
          payload = dict(notification) if notification else {}

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

  def _on_credentials_updated(self, credentials: Credentials) -> None:
    """Save updated FCM credentials to config entry.

    Called by firebase-messaging library when new credentials are obtained.
    Saves them so we don't need to re-register a new Instance ID on restart.
    """

    async def save_credentials() -> None:
      try:
        # Convert Credentials object to dict for storage
        creds_dict = {
            "android_id": getattr(credentials, "android_id", None),
            "security_token": getattr(credentials, "security_token", None),
            "fcm_token": getattr(credentials, "fcm_token", None),
        }
        # Remove None values
        creds_dict = {k: v for k, v in creds_dict.items() if v is not None}

        # Update entry with credentials
        self.hass.config_entries.async_update_entry(
            self.entry,
            data={**self.entry.data, CONF_FCM_CREDENTIALS: creds_dict},
        )
        _LOGGER.debug("FCM credentials saved to entry")
      except Exception as e:
        _LOGGER.error("Failed to save FCM credentials: %s", e)

    # Schedule credential save as a task
    asyncio.create_task(save_credentials())

  async def _run_fcm_receiver(self) -> None:
    """Run FCM receiver socket in the background.

    Handles socket start/stop with reconnection logic.
    """
    retry_count = 0
    max_retries = 10
    backoff_base = 2

    while True:
      try:
        if not self._fcm_client:
          _LOGGER.debug("FCM client not available, stopping receiver")
          break

        _LOGGER.debug("Starting FCM socket listener")
        await self.hass.async_add_executor_job(self._fcm_client.start)
        retry_count = 0  # Reset retries on successful start

      except asyncio.CancelledError:
        _LOGGER.debug("FCM receiver task cancelled")
        break

      except Exception as e:
        retry_count += 1
        if retry_count > max_retries:
          _LOGGER.error(
              "FCM receiver failed after %d retries, giving up: %s",
              max_retries,
              e,
          )
          break

        backoff_seconds = min(backoff_base**retry_count, 300)  # Cap at 5 min
        _LOGGER.warning(
            "FCM receiver error (retry %d/%d in %ds): %s",
            retry_count,
            max_retries,
            backoff_seconds,
            e,
        )
        await asyncio.sleep(backoff_seconds)
