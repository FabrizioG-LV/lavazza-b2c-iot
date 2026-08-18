"""Data models for device catalogs and API responses."""

import logging
from dataclasses import dataclass, field
from typing import Any

_LOGGER = logging.getLogger(__name__)


@dataclass
class StateMeta:
  """State code metadata from catalog."""

  code: int | str
  key: str
  display_name: str


@dataclass
class SensorMeta:
  """Sensor/warning metadata from catalog."""

  code: str
  key: str
  value_type: str = "bool"
  display_name: str | None = None


@dataclass
class ErrorMeta:
  """Error flag metadata from catalog."""

  code: str
  key: str
  severity: str = "error"
  display_name: str | None = None


@dataclass
class CommandMeta:
  """Command metadata from catalog."""

  code: int
  key: str
  valid_states: list[int]
  busy_states: list[int] = field(default_factory=list)
  max_busy_seconds: int = 600
  params: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class ModelCatalog:
  """Full catalog for a device model."""

  model_code: str
  states: dict[int | str, StateMeta] = field(default_factory=dict)
  states_push: dict[int | str, StateMeta] = field(default_factory=dict)
  makecoffee_status: dict[int | str, StateMeta] = field(default_factory=dict)
  makecoffee_status_api: dict[int | str, StateMeta] = field(default_factory=dict)
  descaling_status: dict[int | str, StateMeta] = field(default_factory=dict)
  sensors: dict[str, SensorMeta] = field(default_factory=dict)
  errors: dict[str, ErrorMeta] = field(default_factory=dict)
  beverages: dict[int, dict[str, str]] = field(default_factory=dict)
  commands: dict[int, CommandMeta] = field(default_factory=dict)
  api: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class RawState:
  """Intermediate normalized state before catalog decoding.

  state_code: device state as int (normal operation) or str (special states).
    Examples: 1, 20 (numeric), "offline", "error" (string special states).
  error_flags: dict of error flag names → bool (true = error active).
  warning_flags: dict of warning flag names → bool|int (value can be bool or numeric).
  """

  state_code: int | str
  error_flags: dict[str, bool] = field(default_factory=dict)
  warning_flags: dict[str, bool | int] = field(default_factory=dict)


@dataclass
class Device:
  """Device instance."""

  serial: str
  model_code: str
  matricola: str
  name: str
  catalog: ModelCatalog | None = None
  app_brand: str | None = None
  state_code: int | str | None = None
  makecoffee_status: int | str | None = None
  descaling_status: int | str | None = None
  errors: dict[str, bool] = field(default_factory=dict)
  warnings: dict[str, bool | int] = field(default_factory=dict)

  @classmethod
  def from_list_item(cls, raw: dict[str, Any], catalog: ModelCatalog) -> "Device":
    """Create device from API list response (device_list endpoint).

    Expected fields from API: dsn, model, machineName, appBrand (nullable).
    Serial (dsn) is format: model_matricola (e.g., 18001577_0000002522E219000039).
    """
    dsn = raw["dsn"]
    model_code = raw["model"]
    # Extract matricola from dsn (format: model_matricola)
    parts = dsn.split("_", 1)
    matricola = parts[1] if len(parts) > 1 else ""

    return cls(
        serial=dsn,
        model_code=model_code,
        matricola=matricola,
        name=raw.get("machineName", raw.get("friendlyName", dsn)),
        catalog=catalog,
        app_brand=raw.get("appBrand"),  # nullable; null → Lavazza
    )

  def apply_state(self, raw: dict[str, Any]) -> None:
    """Apply state from get_state API response using catalog decoder.

    Parses raw response into RawState (state_code + error/warning flags),
    then stores state_code, error_flags, warning_flags.
    """
    try:
      from .catalog import family_of
      from .parsers import get_state_parser

      family = family_of(self.model_code)
      parser = get_state_parser(family)
      raw_state = parser(raw)

      self.state_code = raw_state.state_code
      self.errors = raw_state.error_flags.copy()
      self.warnings = raw_state.warning_flags.copy()
    except Exception as e:
      _LOGGER.warning("Failed to apply state for %s: %s", self.serial, e)

  def apply_errors(self, raw: list[dict[str, Any]]) -> None:
    """Apply errors from get_errors API response.

    TODO: Response format not yet specified. Expected to be list of
    error dicts with code/message/timestamp. Parsing deferred until
    example response provided.
    """
    try:
      self.errors.clear()
      # Placeholder: iterate over raw list (assuming list of error dicts)
      for item in raw:
        # TODO: Parse error code/key and message once format is known
        pass
    except Exception as e:
      _LOGGER.warning("Failed to apply errors for %s: %s", self.serial, e)
