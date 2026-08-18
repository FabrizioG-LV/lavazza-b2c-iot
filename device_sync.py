"""Device sync helpers for add/remove during periodic polls."""

import logging
from typing import Any, Callable, Coroutine

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


def async_setup_device_sync(
    hass: HomeAssistant,
    coordinator: DataUpdateCoordinator[dict[str, Any]],
    async_add_entities: AddEntitiesCallback,
    entity_factory: Callable[[str, Any], list[Any]],
) -> None:
  """Set up device sync helper.

  Listens to coordinator updates and adds/removes entities as devices appear/disappear.

  Args:
    hass: Home Assistant instance.
    coordinator: Device list coordinator.
    async_add_entities: Callback to add entities.
    entity_factory: Function that builds entities from device data.
  """
  known_ids: set[str] = set()

  @callback
  def sync_devices() -> None:
    """Sync device list with entity registry."""
    current = set(coordinator.data.keys()) if coordinator.data else set()
    new_ids = current - known_ids
    removed_ids = known_ids - current

    if new_ids:
      entities = []
      for did in new_ids:
        device_data = coordinator.data[did]
        entities.extend(entity_factory(did, device_data))
      if entities:
        async_add_entities(entities)

    for did in removed_ids:
      _remove_device(hass, did)

    known_ids.clear()
    known_ids.update(current)

  coordinator.async_add_listener(sync_devices)
  sync_devices()


def _remove_device(hass: HomeAssistant, device_id: str) -> None:
  """Remove device and associated entities."""
  dev_reg = dr.async_get(hass)
  if device := dev_reg.async_get_device(identifiers={(DOMAIN, device_id)}):
    dev_reg.async_remove_device(device.id)
    _LOGGER.debug("Removed device: %s", device_id)
