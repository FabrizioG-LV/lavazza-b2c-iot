"""Button entities — device commands."""

import logging
from typing import Any

from homeassistant.components.button import ButtonEntity
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
  """Set up button platform from config entry.

  Builds button entities dynamically from device catalog + coordinator data.
  Listens to device list changes and creates/removes buttons as needed.
  """
  coordinators: dict[str, ApiCoordinator] = config_entry.runtime_data["coordinators"]
  api_client = config_entry.runtime_data["api_client"]
  device_list_coordinator = coordinators.get("device_list")
  device_state_coordinator = coordinators.get(COORDINATOR_DEVICE_STATE)

  if not device_list_coordinator or not device_state_coordinator:
    _LOGGER.error("Required coordinators not found")
    return

  def entity_factory(device_serial: str, device: Device) -> list[ButtonEntity]:
    """Build button entities for a device."""
    entities = []

    if not device.catalog or not device.catalog.commands:
      return entities

    for command_code, command_meta in device.catalog.commands.items():
      entities.append(
          DeviceCommandButton(
              coordinator=device_state_coordinator,
              description=EntityDescription(
                  key=f"{device_serial}_cmd_{command_code}",
                  name=f"{device.name} {command_meta.key}",
              ),
              device=device,
              api_client=api_client,
              command_code=command_code,
              command_meta=command_meta,
          )
      )

    return entities

  async_setup_device_sync(
      hass,
      device_list_coordinator,
      async_add_entities,
      entity_factory,
  )


class DeviceCommandButton(ButtonEntity, IntegrationEntity):
  """Device command button."""

  def __init__(
      self,
      coordinator: ApiCoordinator,
      description: EntityDescription,
      device: Device,
      api_client: Any,
      command_code: int,
      command_meta: Any,
  ) -> None:
    """Initialize button."""
    super().__init__(coordinator, description)
    self.device = device
    self.api_client = api_client
    self.command_code = command_code
    self.command_meta = command_meta
    self._attr_unique_id = f"{DOMAIN}_{device.serial}_cmd_{command_code}"

  @property
  def available(self) -> bool:
    """Button available only if device state is in command valid_states."""
    if not self.device.state_code:
      return False
    # Check if current state is in valid_states
    return self.device.state_code in self.command_meta.valid_states

  async def async_press(self) -> None:
    """Send command to device."""
    try:
      await self.api_client.send_command(
          self.device.serial,
          self.command_meta.key,
          params={},  # TODO: Params from entity config or service call
      )
      _LOGGER.debug("Command %s sent to %s", self.command_meta.key, self.device.serial)
    except Exception as e:
      _LOGGER.error("Failed to send command %s to %s: %s", self.command_meta.key, self.device.serial, e)
