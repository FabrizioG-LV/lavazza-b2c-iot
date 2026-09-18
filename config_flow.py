"""Configuration flow for the lavazza_b2c_iot integration."""

import hashlib
import hmac
import logging
import secrets
import time
from typing import Any
from uuid import uuid4

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import (
    BROKER_KEY,
    BROKER_URL,
    CONF_ACCESS_TOKEN,
    CONF_API_ENDPOINTS,
    CONF_APP_PACKAGE_NAME,
    CONF_CLIENT_SECRET,
    CONF_COUNTRY,
    CONF_EMAIL,
    CONF_FCM_CONFIG,
    CONF_FIREBASE_API_KEY,
    CONF_FIREBASE_APP_ID,
    CONF_FIREBASE_PROJECT_ID,
    CONF_FIREBASE_SENDER_ID,
    CONF_INSTALLATION_ID,
    CONF_PASSWORD,
    CONF_TOKEN_TYPE,
    CONF_UID,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

# Country list — must match keys in worker/src/countries.ts
COUNTRIES = ["IT", "AU", "UK", "GB", "DK", "DE", "FR", "US"]


class YourDomainNameConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
  """Config flow for lavazza_b2c_iot."""

  VERSION = 1

  async def async_step_user(
      self, user_input: dict[str, Any] | None = None
  ) -> FlowResult:
    """Handle user-initiated config (step 1: credentials)."""
    errors: dict[str, str] = {}

    if user_input is not None:
      country = user_input[CONF_COUNTRY]
      email = user_input[CONF_EMAIL]
      password = user_input[CONF_PASSWORD]

      try:
        # Step 1: Generate installation credentials
        installation_id = str(uuid4())
        client_secret = secrets.token_hex(32)  # 64-char hex string

        # Step 2: Register installation with worker
        await self._register_installation(
            BROKER_URL, installation_id, client_secret, email
        )

        # Step 3: Get token
        token_response = await self._get_token(
            BROKER_URL, country, email, password, installation_id, client_secret
        )
        user_input[CONF_ACCESS_TOKEN] = token_response["access_token"]
        user_input[CONF_UID] = token_response["uid"]
        user_input[CONF_TOKEN_TYPE] = token_response.get("token_type", "Bearer")
        user_input[CONF_INSTALLATION_ID] = installation_id
        user_input[CONF_CLIENT_SECRET] = client_secret

        # Step 4: Fetch push config for this country/brand. Non-fatal on its own —
        # register+token already succeeded above (a real login + broker
        # registration), and __init__.py/fcm_client.py already tolerate a
        # missing push config (push just doesn't start, polling fallback still
        # works). Failing the whole flow here would force a fresh login on
        # every retry for a step that doesn't actually need to block setup.
        try:
          fcm_config_raw = await self._get_fcm_config(
              BROKER_URL, country, installation_id, client_secret
          )
          # Broker returns {project_id, app_id, sender_id, api_key,
          # package_name} — remap to the CONF_FIREBASE_* keys fcm_client.py
          # reads, since they don't match 1:1 (this mismatch silently
          # defaulted every field to "" and broke push registration until
          # caught).
          user_input[CONF_FCM_CONFIG] = {
              CONF_FIREBASE_PROJECT_ID: fcm_config_raw["project_id"],
              CONF_FIREBASE_APP_ID: fcm_config_raw["app_id"],
              CONF_FIREBASE_SENDER_ID: fcm_config_raw["sender_id"],
              CONF_FIREBASE_API_KEY: fcm_config_raw["api_key"],
              CONF_APP_PACKAGE_NAME: fcm_config_raw["package_name"],
          }
        except Exception as e:  # noqa: BLE001
          _LOGGER.warning(
              "FCM config fetch failed, continuing without push notifications: %s", e
          )

        # Step 5: Fetch API endpoints map. Response is {base_url, endpoints:
        # {key: {url, path}}} — ApiClient expects just the inner "endpoints"
        # map (it indexes it directly, e.g. self.endpoints["device_list"]),
        # not the whole wrapper.
        api_config = await self._get_api_endpoints(
            BROKER_URL, installation_id, client_secret
        )
        user_input[CONF_API_ENDPOINTS] = api_config["endpoints"]

        return self.async_create_entry(title=f"{country} / {email}", data=user_input)
      except Exception as e:  # noqa: BLE001
        _LOGGER.error("Config flow failed: %s", e)
        errors["base"] = "invalid_auth"

    schema = vol.Schema(
        {
            vol.Required(CONF_COUNTRY): vol.In(COUNTRIES),
            vol.Required(CONF_EMAIL): str,
            vol.Required(CONF_PASSWORD): str,
        }
    )

    return self.async_show_form(
        step_id="user",
        data_schema=schema,
        errors=errors,
    )

  async def async_step_reauth(
      self, user_input: dict[str, Any] | None = None
  ) -> FlowResult:
    """Handle reauthentication (token expired/invalid).

    Triggered automatically by ConfigEntryAuthFailed in coordinator.
    """
    config_entry = self.hass.config_entries.async_get_entry(
        self.context["entry_id"]
    )
    if not config_entry:
      return self.async_abort(reason="reauth_failed")

    errors: dict[str, str] = {}

    if user_input is not None:
      country = config_entry.data.get(CONF_COUNTRY)
      email = user_input.get(CONF_EMAIL, config_entry.data.get(CONF_EMAIL))
      password = user_input.get(CONF_PASSWORD)

      try:
        installation_id = config_entry.data.get(CONF_INSTALLATION_ID)
        client_secret = config_entry.data.get(CONF_CLIENT_SECRET)
        token_response = await self._get_token(
            BROKER_URL, country, email, password, installation_id, client_secret
        )

        # Update config entry with new token
        self.hass.config_entries.async_update_entry(
            config_entry,
            data={
                **config_entry.data,
                CONF_ACCESS_TOKEN: token_response["access_token"],
                CONF_UID: token_response["uid"],
                CONF_TOKEN_TYPE: token_response.get("token_type", "Bearer"),
                CONF_EMAIL: email,
                CONF_PASSWORD: password,
            },
        )
        await self.hass.config_entries.async_reload(config_entry.entry_id)
        return self.async_abort(reason="reauth_successful")
      except Exception as e:  # noqa: BLE001
        _LOGGER.error("Reauth failed: %s", e)
        errors["base"] = "invalid_auth"

    schema = vol.Schema(
        {
            vol.Required(
                CONF_EMAIL, default=config_entry.data.get(CONF_EMAIL)
            ): str,
            vol.Required(CONF_PASSWORD): str,
        }
    )

    return self.async_show_form(
        step_id="reauth",
        data_schema=schema,
        errors=errors,
        description_placeholders={"username": config_entry.data.get(CONF_EMAIL)},
    )

  async def _register_installation(
      self,
      broker_url: str,
      installation_id: str,
      client_secret: str,
      email: str,
  ) -> None:
    """Register this HA installation with the broker (one-time setup)."""
    async with aiohttp.ClientSession() as session:
      async with session.post(
          f"{broker_url}/register",
          headers={"X-Broker-Key": BROKER_KEY},
          json={
              "installation_id": installation_id,
              "client_secret": client_secret,
              "email": email,
          },
      ) as resp:
        if resp.status != 200:
          raise Exception(f"Registration failed: {resp.status}")
        _LOGGER.debug("Installation registered: %s", installation_id)

  def _sign_broker_request(
      self, method: str, path: str, client_secret: str, body: str = ""
  ) -> dict[str, str]:
    """Build signing headers for a broker request."""
    timestamp = str(int(time.time()))
    message = f"{method}{path}{body}{timestamp}"
    signature = hmac.new(
        client_secret.encode(), message.encode(), hashlib.sha256
    ).hexdigest()
    return {"X-Timestamp": timestamp, "X-Signature": signature}

  async def _get_token(
      self,
      broker_url: str,
      country: str,
      email: str,
      password: str,
      installation_id: str,
      client_secret: str,
  ) -> dict[str, Any]:
    """Call broker token endpoint."""
    import json

    payload = {"country": country, "email": email, "password": password}
    body = json.dumps(payload)
    sig_headers = self._sign_broker_request("POST", "/token", client_secret, body)
    async with aiohttp.ClientSession() as session:
      async with session.post(
          f"{broker_url}/token",
          headers={
              "X-Broker-Key": BROKER_KEY,
              "X-Installation-ID": installation_id,
              **sig_headers,
          },
          json=payload,
      ) as resp:
        if resp.status != 200:
          raise Exception(f"Token request failed: {resp.status}")
        return await resp.json()

  async def _get_fcm_config(
      self, broker_url: str, country: str, installation_id: str, client_secret: str
  ) -> dict[str, Any]:
    """Fetch push config for country from broker.

    Defaults to the "lavazza" brand — at this point in setup the device list
    isn't known yet, so the real brand(s) in use can't be determined. Correct
    for the large majority of users; Carte Noire/Tablì-only setups need the
    still-deferred multi-brand push wiring (multiple push managers keyed by
    each brand actually present in the device list, set up after __init__.py
    fetches it) to get push notifications for those devices specifically.
    """
    sig_headers = self._sign_broker_request("GET", "/fcm-config", client_secret)
    async with aiohttp.ClientSession() as session:
      async with session.get(
          f"{broker_url}/fcm-config",
          headers={
              "X-Broker-Key": BROKER_KEY,
              "X-Installation-ID": installation_id,
              **sig_headers,
          },
          params={"country": country, "brand": "lavazza"},
      ) as resp:
        if resp.status != 200:
          raise Exception(f"FCM config request failed: {resp.status}")
        return await resp.json()

  async def _get_api_endpoints(
      self, broker_url: str, installation_id: str, client_secret: str
  ) -> dict[str, Any]:
    """Fetch API endpoint map from broker.

    Returns base_url + semantic key → {url, path} mapping for all device/account APIs.
    """
    sig_headers = self._sign_broker_request("GET", "/api-config", client_secret)
    async with aiohttp.ClientSession() as session:
      async with session.get(
          f"{broker_url}/api-config",
          headers={
              "X-Broker-Key": BROKER_KEY,
              "X-Installation-ID": installation_id,
              **sig_headers,
          },
      ) as resp:
        if resp.status != 200:
          raise Exception(f"API config request failed: {resp.status}")
        return await resp.json()
