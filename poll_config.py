"""Polling configuration registry."""

from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING, Any, Awaitable, Callable

if TYPE_CHECKING:
  from .api import ApiClient

# TODO: These intervals are starting values — verify against actual vendor rate limits
# before going to production.


@dataclass
class PollConfig:
  """Poll configuration for an API."""

  interval: timedelta
  fetch: Callable[[], Awaitable[dict[str, Any]]]


def build_poll_config(api_client: "ApiClient") -> dict[str, PollConfig]:
  """Build poll config with API client closures.

  Factory function that creates fetchers bound to api_client instance.
  Called from __init__.py after api_client is created.
  """
  from .device_fetchers import (
      fetch_device_list,
      fetch_all_device_states,
      fetch_all_device_errors,
  )

  # Closure: capture api_client for each fetch function
  async def fetch_device_list_bound() -> dict[str, Any]:
    return await fetch_device_list(api_client)

  async def fetch_device_state_bound() -> dict[str, Any]:
    # Read current devices from device_list coordinator (will be set up first)
    # For now, pass empty dict — coordinator.data will be populated during init
    devices = {}
    return await fetch_all_device_states(api_client, devices)

  async def fetch_device_errors_bound() -> dict[str, Any]:
    devices = {}
    return await fetch_all_device_errors(api_client, devices)

  return {
      "device_list": PollConfig(
          interval=timedelta(hours=24),
          fetch=fetch_device_list_bound,
      ),
      "device_state": PollConfig(
          interval=timedelta(minutes=10),
          fetch=fetch_device_state_bound,
      ),
      "device_errors": PollConfig(
          interval=timedelta(seconds=15),
          fetch=fetch_device_errors_bound,
      ),
  }
