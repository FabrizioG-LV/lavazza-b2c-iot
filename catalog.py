"""Device catalog loader — maps model codes to families and loads state/sensor/error/command metadata."""

import json
import logging
from functools import lru_cache
from pathlib import Path

from .models import ModelCatalog, StateMeta, SensorMeta, ErrorMeta, CommandMeta

_LOGGER = logging.getLogger(__name__)

# Model code → family mapping (real data provided by user)
MODEL_TO_FAMILY = {
    # VCY family
    "18000497": "VCY",
    "18000498": "VCY",
    "18000500": "VCY",
    "18000502": "VCY",
    # BTC (ASSOLUTA) family
    "18101314": "BTC",
    "18101323": "BTC",
    "18101324": "BTC",
    "18101325": "BTC",
    # TAB MONO
    "18001575": "TAB",
    "18001577": "TAB",
    "18001578": "TAB",
    # TAB BIDOSE
    "18001380": "TAB",
    "18001384": "TAB",
    "18001448": "TAB",
    "18001449": "TAB",
    "18001450": "TAB",
    "18001451": "TAB",
    "18001452": "TAB",
    "18001453": "TAB",
    "18001576": "TAB",
}


def family_of(model_code: str) -> str:
  """Derive family from model code.

  Args:
    model_code: Device model code (e.g., "18001577" for BTC).

  Returns:
    Family name (e.g., "BTC"). Defaults to model_code itself if unknown.
  """
  return MODEL_TO_FAMILY.get(model_code, model_code)


@lru_cache(maxsize=256)
def load_catalog(model_code: str) -> ModelCatalog:
  """Load and merge catalog: family base + model override (if exists).

  Caches result per model_code.

  Args:
    model_code: Device model code.

  Returns:
    Merged ModelCatalog for the model.

  Raises:
    FileNotFoundError: If family base catalog not found.
    ValueError: If catalog JSON is malformed.
  """
  family = family_of(model_code)
  base_path = Path(__file__).parent / "catalogs" / "families" / f"{family}.json"
  model_path = Path(__file__).parent / "catalogs" / "models" / f"{model_code}.json"

  # Load family base catalog
  if not base_path.exists():
    _LOGGER.warning("Family catalog not found: %s (model %s)", base_path, model_code)
    return _empty_catalog(model_code)

  try:
    with open(base_path) as f:
      family_data = json.load(f)
  except Exception as e:
    _LOGGER.error("Failed to load family catalog %s: %s", base_path, e)
    return _empty_catalog(model_code)

  catalog = _build_catalog_from_dict(model_code, family_data)

  # Load and merge model override if exists
  if model_path.exists():
    try:
      with open(model_path) as f:
        model_data = json.load(f)
      _merge_catalog_override(catalog, model_data)
    except Exception as e:
      _LOGGER.warning("Failed to load model override %s: %s", model_path, e)

  return catalog


def _empty_catalog(model_code: str) -> ModelCatalog:
  """Return empty catalog as fallback."""
  return ModelCatalog(model_code=model_code)


def _build_catalog_from_dict(model_code: str, data: dict) -> ModelCatalog:
  """Build ModelCatalog from loaded JSON dict."""
  catalog = ModelCatalog(model_code=model_code)

  # Parse states (numeric and string keys)
  for code_key, state_data in data.get("states", {}).items():
    try:
      # Support both numeric (1, 20) and string ("offline") state codes
      try:
        code = int(code_key)
      except ValueError:
        code = code_key

      catalog.states[code] = StateMeta(
          code=code,
          key=state_data.get("key", f"state_{code}"),
          display_name=state_data.get("display_name", f"State {code}"),
      )
    except (KeyError,) as e:
      _LOGGER.warning("Skipping malformed state entry %s: %s", code_key, e)

  # Parse push notification states (FCM livedatastate)
  for code_key, state_data in data.get("states_push", {}).items():
    try:
      try:
        code = int(code_key)
      except ValueError:
        code = code_key

      catalog.states_push[code] = StateMeta(
          code=code,
          key=state_data.get("key", f"state_{code}"),
          display_name=state_data.get("display_name", f"State {code}"),
      )
    except (KeyError,) as e:
      _LOGGER.warning("Skipping malformed push state entry %s: %s", code_key, e)

  # Parse makecoffee status codes (push notification)
  for code_key, status_data in data.get("makecoffee_status", {}).items():
    try:
      try:
        code = int(code_key)
      except ValueError:
        code = code_key

      catalog.makecoffee_status[code] = StateMeta(
          code=code,
          key=status_data.get("key", f"makecoffee_{code}"),
          display_name=status_data.get("display_name", f"Coffee {code}"),
      )
    except (KeyError,) as e:
      _LOGGER.warning("Skipping malformed makecoffee status %s: %s", code_key, e)

  # Parse makecoffee status codes from API (per-family variant)
  for code_key, status_data in data.get("makecoffee_status_api", {}).items():
    try:
      try:
        code = int(code_key)
      except ValueError:
        code = code_key

      catalog.makecoffee_status_api[code] = StateMeta(
          code=code,
          key=status_data.get("key", f"makecoffee_api_{code}"),
          display_name=status_data.get("display_name", f"Coffee {code}"),
      )
    except (KeyError,) as e:
      _LOGGER.warning("Skipping malformed makecoffee_status_api entry %s: %s", code_key, e)

  # Parse descaling status codes
  for code_key, status_data in data.get("descaling_status", {}).items():
    try:
      try:
        code = int(code_key)
      except ValueError:
        code = code_key

      catalog.descaling_status[code] = StateMeta(
          code=code,
          key=status_data.get("key", f"descaling_{code}"),
          display_name=status_data.get("display_name", f"Descaling {code}"),
      )
    except (KeyError,) as e:
      _LOGGER.warning("Skipping malformed descaling status %s: %s", code_key, e)

  # Parse beverages (per-family catalog)
  catalog.beverages = data.get("beverages", {})

  # Parse warning flags (sensors: key is the flag name, e.g., "doorOpen")
  for flag_name, sensor_data in data.get("sensors", {}).items():
    try:
      catalog.sensors[flag_name] = SensorMeta(
          code=flag_name,
          key=sensor_data.get("key", flag_name),
          value_type=sensor_data.get("value_type", "bool"),
          display_name=sensor_data.get("display_name"),
      )
    except (KeyError,) as e:
      _LOGGER.warning("Skipping malformed sensor entry %s: %s", flag_name, e)

  # Parse error flags (errors: key is the flag name, e.g., "tempError")
  for flag_name, error_data in data.get("errors", {}).items():
    try:
      catalog.errors[flag_name] = ErrorMeta(
          code=flag_name,
          key=error_data.get("key", flag_name),
          severity=error_data.get("severity", "error"),
          display_name=error_data.get("display_name"),
      )
    except (KeyError,) as e:
      _LOGGER.warning("Skipping malformed error entry %s: %s", flag_name, e)

  # Parse commands
  for code_str, command_data in data.get("commands", {}).items():
    try:
      code = int(code_str)
      catalog.commands[code] = CommandMeta(
          code=code,
          key=command_data.get("key", f"command_{code}"),
          valid_states=command_data.get("valid_states", []),
          busy_states=command_data.get("busy_states", []),
          max_busy_seconds=command_data.get("max_busy_seconds", 600),
          params=command_data.get("params", {}),
      )
    except (ValueError, KeyError) as e:
      _LOGGER.warning("Skipping malformed command entry %s: %s", code_str, e)

  # Parse API overrides (optional, family may not specify)
  catalog.api = data.get("api", {})

  return catalog


def _merge_catalog_override(catalog: ModelCatalog, override: dict) -> None:
  """Merge model-specific overrides into catalog (in-place).

  Overrides use same structure as base catalog; null value removes an entry.
  """
  # States: override/remove (support both numeric and string keys)
  for code_key, state_data in override.get("states", {}).items():
    try:
      code = int(code_key)
    except ValueError:
      code = code_key

    if state_data is None:
      catalog.states.pop(code, None)
    else:
      existing = catalog.states.get(code)
      catalog.states[code] = StateMeta(
          code=code,
          key=state_data.get("key", existing.key if existing else f"state_{code}"),
          display_name=state_data.get("display_name", existing.display_name if existing else f"State {code}"),
      )

  # Sensors: override/remove (string keys, not numeric)
  for flag_name, sensor_data in override.get("sensors", {}).items():
    if sensor_data is None:
      catalog.sensors.pop(flag_name, None)
    else:
      existing = catalog.sensors.get(flag_name)
      catalog.sensors[flag_name] = SensorMeta(
          code=flag_name,
          key=sensor_data.get("key", existing.key if existing else flag_name),
          value_type=sensor_data.get("value_type", "bool"),
          display_name=sensor_data.get("display_name", existing.display_name if existing else None),
      )

  # Errors: override/remove (string keys, not numeric)
  for flag_name, error_data in override.get("errors", {}).items():
    if error_data is None:
      catalog.errors.pop(flag_name, None)
    else:
      existing = catalog.errors.get(flag_name)
      catalog.errors[flag_name] = ErrorMeta(
          code=flag_name,
          key=error_data.get("key", existing.key if existing else flag_name),
          severity=error_data.get("severity", "error"),
          display_name=error_data.get("display_name", existing.display_name if existing else None),
      )

  # Commands: override/remove
  for code_str, command_data in override.get("commands", {}).items():
    code = int(code_str)
    if command_data is None:
      catalog.commands.pop(code, None)
    else:
      existing = catalog.commands.get(code)
      catalog.commands[code] = CommandMeta(
          code=code,
          key=command_data.get("key", existing.key if existing else f"command_{code}"),
          valid_states=command_data.get("valid_states", []),
          busy_states=command_data.get("busy_states", []),
          max_busy_seconds=command_data.get("max_busy_seconds", 600),
          params=command_data.get("params", {}),
      )

  # API overrides: merge (deep merge could be added if needed)
  catalog.api.update(override.get("api", {}))

  # Beverages: override/replace
  if "beverages" in override:
    catalog.beverages = override["beverages"]
