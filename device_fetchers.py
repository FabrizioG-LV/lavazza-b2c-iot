"""Device-scoped API fetchers."""

import asyncio
import logging
from typing import Any

from .api import ApiClient, ApiError
from .catalog import load_catalog
from .models import Device

_LOGGER = logging.getLogger(__name__)


async def fetch_device_list(api_client: ApiClient) -> dict[str, Device]:
  """Fetch list of devices, build Device instances.

  Returns:
    Dict keyed by device serial, values are Device objects with state/errors
    populated from subsequent API calls.

  Raises:
    ApiError: If list_devices fails.
  """
  try:
    raw_list = await api_client.list_devices()
    devices = {}

    # raw_list is expected to be a list of device dicts
    if not isinstance(raw_list, list):
      _LOGGER.error("device_list response is not a list: %s", type(raw_list))
      raise ApiError(f"Invalid device_list response type: {type(raw_list)}")

    for item in raw_list:
      try:
        # Validate required fields
        if not isinstance(item, dict) or "dsn" not in item or "model" not in item:
          _LOGGER.warning("Skipping malformed device item (missing dsn/model): %s", item)
          continue

        model_code = item["model"]
        catalog = load_catalog(model_code)
        device = Device.from_list_item(item, catalog=catalog)
        devices[device.serial] = device
      except (KeyError, ValueError) as e:
        _LOGGER.warning("Skipping malformed device item: %s (%s)", item, e)
        continue

    return devices
  except ApiError as e:
    _LOGGER.error("fetch_device_list failed: %s", e)
    raise


async def fetch_all_device_states(
    api_client: ApiClient,
    devices: dict[str, Device],
) -> dict[str, Device]:
  """Fetch state for all devices in parallel.

  Isolates errors per-device: one failed fetch doesn't abort others.

  Args:
    api_client: API client.
    devices: Current device dict from device_list coordinator.

  Returns:
    Updated device dict with state applied.
  """

  async def fetch_one(device: Device) -> None:
    try:
      raw_state = await api_client.get_state(device.serial)
      device.apply_state(raw_state)
    except ApiError as e:
      _LOGGER.warning(
          "fetch_state failed for %s: %s",
          device.serial,
          e,
      )

  try:
    await asyncio.gather(*[fetch_one(d) for d in devices.values()])
    return devices
  except Exception as e:
    _LOGGER.error("fetch_all_device_states unexpected error: %s", e)
    raise ApiError(str(e)) from e


async def fetch_all_device_errors(
    api_client: ApiClient,
    devices: dict[str, Device],
) -> dict[str, Device]:
  """Fetch error list for all devices in parallel.

  Isolates errors per-device: one failed fetch doesn't abort others.

  Args:
    api_client: API client.
    devices: Current device dict from device_list coordinator.

  Returns:
    Updated device dict with errors applied.
  """

  async def fetch_one(device: Device) -> None:
    try:
      raw_errors = await api_client.get_errors(device.serial)
      device.apply_errors(raw_errors)
    except ApiError as e:
      _LOGGER.warning(
          "fetch_errors failed for %s: %s",
          device.serial,
          e,
      )

  try:
    await asyncio.gather(*[fetch_one(d) for d in devices.values()])
    return devices
  except Exception as e:
    _LOGGER.error("fetch_all_device_errors unexpected error: %s", e)
    raise ApiError(str(e)) from e
