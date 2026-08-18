"""Base entity classes."""

from typing import Any

from homeassistant.core import callback
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import ApiCoordinator


class IntegrationEntity(CoordinatorEntity[ApiCoordinator]):
  """Base entity for this integration."""

  def __init__(
      self,
      coordinator: ApiCoordinator,
      description: EntityDescription,
  ) -> None:
    """Initialize entity."""
    super().__init__(coordinator)
    self.entity_description = description
    self._attr_name = description.name

  @callback
  def _handle_coordinator_update(self) -> None:
    """Handle updated data from coordinator."""
    self.async_write_ha_state()
