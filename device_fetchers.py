"""Device-scoped API fetchers."""

import asyncio
import logging
import time

from .api import ApiClient, ApiError, AuthError
from .catalog import KNOWN_BRANDS, brand_of, load_catalog
from .models import Device

_LOGGER = logging.getLogger(__name__)

ERRORS_404_BACKOFF_SECONDS = 86400  # 1 day


async def fetch_device_list(api_client: ApiClient) -> dict[str, Device]:
  """Fetch list of devices across all known brands, build Device instances.

  The account-level device list is brand-scoped server-side per request
  (see ApiClient.list_devices()) -- confirmed live, a plain call only ever
  returns Lavazza devices, a Tabli-brand device only shows up when the
  request is scoped to that brand. So this queries once per brand in
  KNOWN_BRANDS (in parallel) and merges the results. One brand erroring
  doesn't stop discovery of the others -- same per-item isolation principle
  used for state/error fetches below, just at brand granularity.

  Note: a device registered under a country other than the account's
  configured country would still be missed -- this only varies brand, not
  country, per call.

  Returns:
    Dict keyed by device serial, values are Device objects with state/errors
    populated from subsequent API calls.

  Raises:
    ApiError: If list_devices fails for every known brand.
    AuthError: Token invalid/expired -- propagates immediately, not isolated
      per-brand, since it means every subsequent call would fail the same way.
  """
  devices: dict[str, Device] = {}
  any_success = False

  async def fetch_brand(app_brand: str) -> None:
    nonlocal any_success
    try:
      raw_list = await api_client.list_devices(app_brand=app_brand)
    except ApiError as e:
      _LOGGER.warning("list_devices failed for brand %s: %s", app_brand, e)
      return

    any_success = True
    if not isinstance(raw_list, list):
      _LOGGER.error(
          "device_list response is not a list for brand %s: %s", app_brand, type(raw_list)
      )
      return

    for item in raw_list:
      try:
        if not isinstance(item, dict) or "dsn" not in item or "model" not in item:
          _LOGGER.warning("Skipping malformed device item (missing dsn/model): %s", item)
          continue

        model_code = item["model"]
        catalog = load_catalog(model_code)
        # app_brand here is which brand-scoped query surfaced this device --
        # only useful for discovery. The three brand queries run concurrently
        # and get merged into one dict, so if the same device is returned
        # under more than one brand's scope (seen live: a device came back
        # tagged "cartenoire" even though it's a real Lavazza Voicy -- the
        # vendor API likely doesn't treat "cartenoire" as a distinct filter
        # for every account/model and falls back to the default set),
        # whichever async task finishes last would silently win a race and
        # store the wrong brand. brand_of(model_code) is a deterministic,
        # pure function of the model code -- always correct regardless of
        # which query happened to find the device or in what order.
        device = Device.from_list_item(item, catalog=catalog, app_brand=brand_of(model_code))
        devices[device.serial] = device
      except (KeyError, ValueError) as e:
        _LOGGER.warning("Skipping malformed device item: %s (%s)", item, e)
        continue

  # AuthError isn't caught here -- it propagates out of gather() immediately,
  # same contract as fetch_all_device_states/fetch_all_device_errors below.
  await asyncio.gather(*[fetch_brand(brand) for brand in KNOWN_BRANDS])

  if not any_success:
    raise ApiError("list_devices failed for all known brands")

  return devices


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
  except AuthError:
    # Let AuthError propagate as-is — coordinator.py maps it to
    # ConfigEntryAuthFailed to trigger reauth. Wrapping it in ApiError here
    # would silently downgrade a 401 into a generic UpdateFailed instead.
    raise
  except Exception as e:
    _LOGGER.error("fetch_all_device_states unexpected error: %s", e)
    raise ApiError(str(e)) from e


async def fetch_all_device_errors(
    api_client: ApiClient,
    devices: dict[str, Device],
) -> dict[str, Device]:
  """Fetch error list for all devices in parallel.

  Isolates errors per-device: one failed fetch doesn't abort others. A
  device that 404s (endpoint doesn't exist for it) is backed off for
  ERRORS_404_BACKOFF_SECONDS instead of being retried every poll forever --
  a 404 means the route isn't there, not a transient failure, and won't
  start working again on its own. Other failures (5xx, network errors)
  keep retrying every poll as before.

  Args:
    api_client: API client.
    devices: Current device dict from device_list coordinator.

  Returns:
    Updated device dict with errors applied.
  """

  async def fetch_one(device: Device) -> None:
    if device.errors_backoff_until and time.time() < device.errors_backoff_until:
      return

    try:
      raw_errors = await api_client.get_errors(device.serial)
      device.apply_errors(raw_errors)
      device.errors_backoff_until = None
    except ApiError as e:
      if e.status_code == 404:
        device.errors_backoff_until = time.time() + ERRORS_404_BACKOFF_SECONDS
        _LOGGER.debug(
            "get_errors 404 for %s, backing off %ds", device.serial, ERRORS_404_BACKOFF_SECONDS
        )
      else:
        _LOGGER.warning(
            "fetch_errors failed for %s: %s",
            device.serial,
            e,
        )

  try:
    await asyncio.gather(*[fetch_one(d) for d in devices.values()])
    return devices
  except AuthError:
    raise
  except Exception as e:
    _LOGGER.error("fetch_all_device_errors unexpected error: %s", e)
    raise ApiError(str(e)) from e
