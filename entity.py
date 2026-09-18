"""Base entity classes."""

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ApiCoordinator
from .models import Device

BRAND_MANUFACTURER = {
    "lavazza": "Lavazza",
    "tabli": "Tablì",
    "cartenoire": "Carte Noire",
}


class IntegrationEntity(CoordinatorEntity[ApiCoordinator]):
  """Base entity for this integration."""

  def __init__(
      self,
      coordinator: ApiCoordinator,
      description: EntityDescription,
      device: Device,
  ) -> None:
    """Initialize entity."""
    super().__init__(coordinator)
    self.entity_description = description
    self._attr_name = description.name
    self.device = device

  @property
  def device_info(self) -> DeviceInfo:
    """Group this entity under one HA Device per physical machine."""
    return DeviceInfo(
        identifiers={(DOMAIN, self.device.serial)},
        name=self.device.name,
        manufacturer=BRAND_MANUFACTURER.get(self.device.app_brand, "Lavazza"),
        model=self.device.model_code,
    )

  @callback
  def _handle_coordinator_update(self) -> None:
    """Handle updated data from coordinator."""
    self.async_write_ha_state()
