"""API client for device cloud backend."""

import hashlib
import hmac
import logging
import time
from typing import Any
from uuid import uuid4

import aiohttp

_LOGGER = logging.getLogger(__name__)


class AuthError(Exception):
  """Authentication failed (401, token expired)."""


class ApiError(Exception):
  """Generic API error."""


class ApiClient:
  """Cloud API client."""

  def __init__(
      self,
      token: str,
      session: aiohttp.ClientSession,
      endpoints: dict[str, str],
      country: str,
      installation_id: str,
      client_secret: str,
      app_version: str = "V99.99.99",
  ) -> None:
    """Initialize API client.

    Args:
      token: OAuth2 access token (opaque).
      session: aiohttp ClientSession.
      endpoints: Semantic key → full URL mapping from worker GET /api-config.
      country: Country code (IT, GB, AU, etc.).
      installation_id: HA instance UUID (for signature verification).
      client_secret: HA instance secret (for HMAC signing).
      app_version: App version string (WAF bypass; default V99.99.99).
    """
    self.token = token
    self.session = session
    self.endpoints = endpoints
    self.country = country
    self.installation_id = installation_id
    self.client_secret = client_secret
    self.app_version = app_version
    self.user_agent = f"HA/{app_version}(com.lavazza.HA.worker;build:99999;Android)"

  async def list_devices(self) -> dict[str, Any]:
    """Fetch list of devices for account.

    Returns:
      Raw API response (dict). Parsing deferred until response example provided.

    Raises:
      AuthError: Token invalid/expired (401).
      ApiError: Other API errors.
    """
    url = self.endpoints["device_list"]
    path = "/apiconsumerapp/iotpreset/device/list"
    try:
      headers = {
          **self._common_headers(),
          **self._sign_request("GET", path),
      }
      async with self.session.get(url, headers=headers) as resp:
        if resp.status == 401:
          raise AuthError("Token expired or invalid")
        if resp.status >= 400:
          raise ApiError(f"list_devices failed: {resp.status}")
        return await resp.json()
    except aiohttp.ClientError as e:
      raise ApiError(f"list_devices network error: {e}") from e

  async def get_state(self, unit_matricola: str) -> dict[str, Any]:
    """Fetch current device state.

    Args:
      unit_matricola: Device identifier (model_matricola format).

    Returns:
      Raw API response (dict). Parsing deferred until response example provided.
    """
    url = self.endpoints["device_state"].replace("{unit_matricola}", unit_matricola)
    try:
      async with self.session.get(
          url,
          headers=self._device_headers(),
      ) as resp:
        if resp.status == 401:
          raise AuthError("Token expired or invalid")
        if resp.status >= 400:
          raise ApiError(f"get_state failed: {resp.status}")
        return await resp.json()
    except aiohttp.ClientError as e:
      raise ApiError(f"get_state network error: {e}") from e

  async def get_errors(self, unit_matricola: str) -> dict[str, Any]:
    """Fetch device error list.

    Args:
      unit_matricola: Device identifier (model_matricola format).

    Returns:
      Raw API response (dict/list). Parsing deferred until response example provided.
    """
    url = self.endpoints["device_errors"].replace("{unit_matricola}", unit_matricola)
    try:
      async with self.session.get(
          url,
          headers=self._device_headers(),
      ) as resp:
        if resp.status == 401:
          raise AuthError("Token expired or invalid")
        if resp.status >= 400:
          raise ApiError(f"get_errors failed: {resp.status}")
        return await resp.json()
    except aiohttp.ClientError as e:
      raise ApiError(f"get_errors network error: {e}") from e

  async def send_command(
      self,
      unit_matricola: str,
      command_key: str,
      params: dict[str, Any] | None = None,
  ) -> dict[str, Any]:
    """Send command to device.

    Args:
      unit_matricola: Device identifier (model_matricola format).
      command_key: Semantic command key (power_on, power_off, stop_brewing, prepare_preset, etc.).
      params: Command parameters dict (passed as-is in request body).

    Returns:
      Raw API response (dict). Parsing deferred until response example provided.
    """
    url = self.endpoints[command_key].replace("{unit_matricola}", unit_matricola)
    payload = params or {}
    try:
      async with self.session.post(
          url,
          headers=self._device_headers(),
          json=payload,
      ) as resp:
        if resp.status == 401:
          raise AuthError("Token expired or invalid")
        if resp.status >= 400:
          raise ApiError(f"send_command failed: {resp.status}")
        return await resp.json()
    except aiohttp.ClientError as e:
      raise ApiError(f"send_command network error: {e}") from e

  async def check_token_valid(self, email: str, uid: str) -> bool:
    """Check if token is still valid (for 24h periodic verification).

    Args:
      email: User email (login_ID parameter).
      uid: User ID from Gigya (UID parameter).

    Returns:
      True if user is logged (isLogged=true), False otherwise.

    Raises:
      AuthError: Token invalid (401).
      ApiError: Other API errors.
    """
    url = self.endpoints["user_logged"]
    params = {
        "login_ID": email,
        "UID": uid,
        "country": self.country,
        "lang": self.country,
    }
    try:
      async with self.session.get(
          url,
          params=params,
          headers=self._auth_headers(),
      ) as resp:
        if resp.status == 401:
          raise AuthError("Token expired or invalid")
        if resp.status >= 400:
          raise ApiError(f"check_token_valid failed: {resp.status}")
        data = await resp.json()
        return data.get("isLogged", False)
    except aiohttp.ClientError as e:
      raise ApiError(f"check_token_valid network error: {e}") from e

  async def get_recipe_list(self, unit_matricola: str) -> dict[str, Any]:
    """Fetch available recipes/presets for device.

    Args:
      unit_matricola: Device identifier (model_matricola format).

    Returns:
      Raw API response (dict). Parsing deferred until response example provided.
    """
    url = self.endpoints["recipe_list"].replace("{unit_matricola}", unit_matricola)
    try:
      async with self.session.get(
          url,
          headers=self._device_headers(),
      ) as resp:
        if resp.status == 401:
          raise AuthError("Token expired or invalid")
        if resp.status >= 400:
          raise ApiError(f"get_recipe_list failed: {resp.status}")
        return await resp.json()
    except aiohttp.ClientError as e:
      raise ApiError(f"get_recipe_list network error: {e}") from e

  async def get_device_info(self, unit_matricola: str) -> dict[str, Any]:
    """Fetch detailed device information.

    Args:
      unit_matricola: Device identifier (model_matricola format).

    Returns:
      Raw API response (dict). Parsing deferred until response example provided.
    """
    url = self.endpoints["device_info"]
    try:
      async with self.session.get(
          url,
          params={"unit_matricola": unit_matricola},
          headers=self._device_headers(),
      ) as resp:
        if resp.status == 401:
          raise AuthError("Token expired or invalid")
        if resp.status >= 400:
          raise ApiError(f"get_device_info failed: {resp.status}")
        return await resp.json()
    except aiohttp.ClientError as e:
      raise ApiError(f"get_device_info network error: {e}") from e

  async def get_debug_status(self, unit_matricola: str) -> dict[str, Any]:
    """Fetch debug status for device.

    Args:
      unit_matricola: Device identifier (model_matricola format).

    Returns:
      Raw API response (dict). Parsing deferred until response example provided.
    """
    url = self.endpoints["debug_status"].replace("{unit_matricola}", unit_matricola)
    try:
      async with self.session.get(
          url,
          headers=self._device_headers(),
      ) as resp:
        if resp.status == 401:
          raise AuthError("Token expired or invalid")
        if resp.status >= 400:
          raise ApiError(f"get_debug_status failed: {resp.status}")
        return await resp.json()
    except aiohttp.ClientError as e:
      raise ApiError(f"get_debug_status network error: {e}") from e

  async def get_buzzer_info(self) -> dict[str, Any]:
    """Fetch buzzer configuration.

    Returns:
      Raw API response (dict). Parsing deferred until response example provided.
    """
    url = self.endpoints["buzzer_info"]
    try:
      async with self.session.get(
          url,
          headers=self._device_headers(),
      ) as resp:
        if resp.status == 401:
          raise AuthError("Token expired or invalid")
        if resp.status >= 400:
          raise ApiError(f"get_buzzer_info failed: {resp.status}")
        return await resp.json()
    except aiohttp.ClientError as e:
      raise ApiError(f"get_buzzer_info network error: {e}") from e

  async def register_fcm_token(self, fcm_token: str) -> dict[str, Any]:
    """Register FCM token for push notifications.

    Args:
      fcm_token: Firebase Cloud Messaging registration token.

    Returns:
      Raw API response (dict). Parsing deferred until response example provided.
    """
    url = self.endpoints["register_token"]
    payload = {"token": fcm_token}
    try:
      async with self.session.post(
          url,
          headers=self._device_headers(),
          json=payload,
      ) as resp:
        if resp.status == 401:
          raise AuthError("Token expired or invalid")
        if resp.status >= 400:
          raise ApiError(f"register_fcm_token failed: {resp.status}")
        return await resp.json()
    except aiohttp.ClientError as e:
      raise ApiError(f"register_fcm_token network error: {e}") from e

  async def get_account_linking_status(self) -> dict[str, Any]:
    """Fetch account linking status.

    Returns:
      Raw API response (dict). Parsing deferred until response example provided.
    """
    url = self.endpoints["account_linking_status"]
    try:
      async with self.session.get(
          url,
          headers=self._common_headers(),
      ) as resp:
        if resp.status == 401:
          raise AuthError("Token expired or invalid")
        if resp.status >= 400:
          raise ApiError(f"get_account_linking_status failed: {resp.status}")
        return await resp.json()
    except aiohttp.ClientError as e:
      raise ApiError(f"get_account_linking_status network error: {e}") from e

  def _auth_headers(self) -> dict[str, str]:
    """Build authorization header (common to all requests)."""
    return {
        "X-Authorization": f"Bearer {self.token}",
    }

  def _common_headers(self) -> dict[str, str]:
    """Build common headers (account-level APIs)."""
    return {
        **self._auth_headers(),
        "User-Agent": self.user_agent,
        "appVersion": self.app_version,
        "country_value": self.country,
    }

  def _with_brand_header(
      self, headers: dict[str, str], app_brand: str | None = None
  ) -> dict[str, str]:
    """Add appBrand header (nullable; Lavazza if not specified)."""
    if app_brand:
      return {**headers, "appBrand": app_brand}
    return headers

  def _device_headers(self) -> dict[str, str]:
    """Build headers for device-scoped APIs (IoT commands/queries)."""
    return {
        **self._common_headers(),
        "actor": "app-android",
        "correlationId": str(uuid4()),
    }

  def _sign_request(self, method: str, path: str, body: str = "") -> dict[str, str]:
    """Generate HMAC signature headers for request verification.

    Returns:
      Dict with X-Installation-ID, X-Timestamp, X-Signature headers.
    """
    timestamp = str(int(time.time()))
    message = f"{method}{path}{body}{timestamp}"
    signature = hmac.new(
        self.client_secret.encode(),
        message.encode(),
        hashlib.sha256,
    ).hexdigest()

    return {
        "X-Installation-ID": self.installation_id,
        "X-Timestamp": timestamp,
        "X-Signature": signature,
    }
