"""Configuration flow for the lavazza_b2c_iot integration."""

import logging
import os
import secrets
from typing import Any
from uuid import uuid4

import aiohttp
import voluptuous as vol
from homeassistant import config_entries, core
from homeassistant.data_entry_flow import FlowResult

from .const import (
    BROKER_KEY,
    BROKER_URL,
    CONF_ACCESS_TOKEN,
    CONF_API_ENDPOINTS,
    CONF_CLIENT_SECRET,
    CONF_COUNTRY,
    CONF_EMAIL,
    CONF_FCM_CONFIG,
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
        token_response = await self._get_token(BROKER_URL, country, email, password)
        user_input[CONF_ACCESS_TOKEN] = token_response["access_token"]
        user_input[CONF_UID] = token_response["uid"]
        user_input[CONF_TOKEN_TYPE] = token_response.get("token_type", "Bearer")
        user_input[CONF_INSTALLATION_ID] = installation_id
        user_input[CONF_CLIENT_SECRET] = client_secret

        # Step 4: Fetch FCM config for this country (per-country static config)
        fcm_config = await self._get_fcm_config(BROKER_URL, country)
        user_input[CONF_FCM_CONFIG] = fcm_config

        # Step 5: Fetch API endpoints map (base URL + semantic key -> path mapping)
        api_endpoints = await self._get_api_endpoints(BROKER_URL)
        user_input[CONF_API_ENDPOINTS] = api_endpoints

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
        token_response = await self._get_token(BROKER_URL, country, email, password)

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
    """Register this HA installation with the broker (one-time setup).

    Sends installation_id + client_secret so broker can verify HMAC signatures.
    """
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

  async def _get_token(
      self, broker_url: str, country: str, email: str, password: str
  ) -> dict[str, Any]:
    """Call broker token endpoint.

    TODO: Fill in actual endpoint path and handle actual response.
    """
    async with aiohttp.ClientSession() as session:
      async with session.post(
          f"{broker_url}/token",
          headers={"X-Broker-Key": BROKER_KEY},
          json={
              "country": country,
              "email": email,
              "password": password,
          },
      ) as resp:
        if resp.status != 200:
          raise Exception(f"Token request failed: {resp.status}")
        return await resp.json()

  async def _get_fcm_config(
      self, broker_url: str, country: str
  ) -> dict[str, Any]:
    """Fetch FCM config for country from broker.

    TODO: Fill in actual endpoint path and handle actual response.
    """
    async with aiohttp.ClientSession() as session:
      async with session.get(
          f"{broker_url}/fcm-config",
          headers={"X-Broker-Key": BROKER_KEY},
          params={"country": country},
      ) as resp:
        if resp.status != 200:
          raise Exception(f"FCM config request failed: {resp.status}")
        return await resp.json()

  async def _get_api_endpoints(self, broker_url: str) -> dict[str, Any]:
    """Fetch API endpoint map from broker.

    Returns base_url + semantic key → path mapping for all device/account APIs.
    """
    async with aiohttp.ClientSession() as session:
      async with session.get(
          f"{broker_url}/api-config",
          headers={"X-Broker-Key": BROKER_KEY},
      ) as resp:
        if resp.status != 200:
          raise Exception(f"API config request failed: {resp.status}")
        return await resp.json()
