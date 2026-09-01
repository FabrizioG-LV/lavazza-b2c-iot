"""Generic polling coordinator."""

import logging
from datetime import timedelta
from typing import Any, Awaitable, Callable

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ApiError, AuthError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class ApiCoordinator(DataUpdateCoordinator[dict[str, Any]]):
  """Generic API coordinator for polling with configurable interval and fetch function."""

  def __init__(
      self,
      hass: HomeAssistant,
      name: str,
      interval: timedelta,
      fetch: Callable[[], Awaitable[dict[str, Any]]],
  ) -> None:
    """Initialize coordinator.

    Args:
      hass: Home Assistant instance.
      name: Coordinator name (for logging).
      interval: Poll interval.
      fetch: Async callable that returns data dict.
    """
    super().__init__(hass, _LOGGER, name=name, update_interval=interval)
    self._fetch = fetch

  async def _async_update_data(self) -> dict[str, Any]:
    """Fetch data from API.

    Raises:
      ConfigEntryAuthFailed: On authentication error (401) — triggers reauth.
      UpdateFailed: On generic API error.
    """
    try:
      return await self._fetch()
    except AuthError as err:
      raise ConfigEntryAuthFailed(str(err)) from err
    except ApiError as err:
      raise UpdateFailed(str(err)) from err
