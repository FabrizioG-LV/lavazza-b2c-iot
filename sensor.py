"""Sensor entities — device state + warnings + errors."""

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.entity import EntityDescription

from .const import DOMAIN, COORDINATOR_DEVICE_STATE
from .coordinator import ApiCoordinator
from .device_sync import async_setup_device_sync
from .entity import IntegrationEntity
from .models import Device

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigType,
    async_add_entities: AddEntitiesCallback,
) -> None:
  """Set up sensor platform from config entry.

  Builds sensor entities dynamically from device catalog + coordinator data.
  Listens to device list changes and creates/removes entities as needed.
  """
  coordinators: dict[str, ApiCoordinator] = config_entry.runtime_data["coordinators"]
  device_list_coordinator = coordinators.get("device_list")
  device_state_coordinator = coordinators.get(COORDINATOR_DEVICE_STATE)

  if not device_list_coordinator or not device_state_coordinator:
    _LOGGER.error("Required coordinators not found")
    return

  def entity_factory(device_serial: str, device: Device) -> list[SensorEntity]:
    """Build sensor entities for a device."""
    entities = []

    # Device state sensor
    if device.state_code is not None:
      entities.append(
          DeviceStateSensor(
              coordinator=device_state_coordinator,
              description=EntityDescription(
                  key=f"{device_serial}_state",
                  name=f"{device.name} State",
              ),
              device=device,
          )
      )

    # Warning flag sensors
    if device.catalog and device.catalog.sensors:
      for flag_name, sensor_meta in device.catalog.sensors.items():
        entities.append(
            DeviceWarningSensor(
                coordinator=device_state_coordinator,
                description=EntityDescription(
                    key=f"{device_serial}_{flag_name}",
                    name=f"{device.name} {sensor_meta.display_name or flag_name}",
                ),
                device=device,
                flag_name=flag_name,
            )
        )

    # Error flag sensors
    if device.catalog and device.catalog.errors:
      for flag_name, error_meta in device.catalog.errors.items():
        entities.append(
            DeviceErrorSensor(
                coordinator=device_state_coordinator,
                description=EntityDescription(
                    key=f"{device_serial}_{flag_name}",
                    name=f"{device.name} {error_meta.display_name or flag_name}",
                ),
                device=device,
                flag_name=flag_name,
            )
        )

    return entities

  async_setup_device_sync(
      hass,
      device_list_coordinator,
      async_add_entities,
      entity_factory,
  )


class DeviceStateSensor(SensorEntity, IntegrationEntity):
  """Device state sensor."""

  def __init__(
      self,
      coordinator: ApiCoordinator,
      description: EntityDescription,
      device: Device,
  ) -> None:
    """Initialize sensor."""
    super().__init__(coordinator, description)
    self.device = device
    self._attr_unique_id = f"{DOMAIN}_{device.serial}_state"

  @property
  def native_value(self) -> str | None:
    """Return current state display name."""
    if not self.device.state_code or not self.device.catalog:
      return None
    state_meta = self.device.catalog.states.get(self.device.state_code)
    return state_meta.display_name if state_meta else str(self.device.state_code)


class DeviceWarningSensor(SensorEntity, IntegrationEntity):
  """Device warning flag sensor."""

  def __init__(
      self,
      coordinator: ApiCoordinator,
      description: EntityDescription,
      device: Device,
      flag_name: str,
  ) -> None:
    """Initialize sensor."""
    super().__init__(coordinator, description)
    self.device = device
    self.flag_name = flag_name
    self._attr_unique_id = f"{DOMAIN}_{device.serial}_{flag_name}"

  @property
  def native_value(self) -> str | int | None:
    """Return warning flag value."""
    if self.flag_name not in self.device.warnings:
      return None
    value = self.device.warnings[self.flag_name]
    if isinstance(value, bool):
      return "on" if value else "off"
    return value


class DeviceErrorSensor(SensorEntity, IntegrationEntity):
  """Device error flag sensor."""

  def __init__(
      self,
      coordinator: ApiCoordinator,
      description: EntityDescription,
      device: Device,
      flag_name: str,
  ) -> None:
    """Initialize sensor."""
    super().__init__(coordinator, description)
    self.device = device
    self.flag_name = flag_name
    self._attr_unique_id = f"{DOMAIN}_{device.serial}_{flag_name}"

  @property
  def native_value(self) -> str | None:
    """Return error flag status."""
    if self.flag_name not in self.device.errors:
      return None
    is_active = self.device.errors[self.flag_name]
    return "error" if is_active else "ok"
