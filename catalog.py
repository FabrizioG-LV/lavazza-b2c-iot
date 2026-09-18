"""Device catalog loader — maps model codes to families and loads state/sensor/error/command metadata."""

import logging

from .models import ModelCatalog, StateMeta, SensorMeta, ErrorMeta, CommandMeta

_LOGGER = logging.getLogger(__name__)

# Family → model codes mapping (scalable: add model by appending to family list)
FAMILIES = {
    "VCY": ["18000497", "18000498", "18000500", "18000502"],
    "BTC": ["18101314", "18101323", "18101324", "18101325"],
    "TAB": [
        "18001575", "18001577", "18001578",  # MONO
        "18001380", "18001384", "18001448", "18001449", "18001450", "18001451", "18001452", "18001453", "18001576",  # BIDOSE
    ],
}


def family_of(model_code: str) -> str:
  """Derive family from model code.

  Args:
    model_code: Device model code (e.g., "18001577").

  Returns:
    Family name (e.g., "TAB"). Defaults to model_code itself if unknown.
  """
  for family, models in FAMILIES.items():
    if model_code in models:
      return family
  return model_code


# Model codes that deviate from their family's default brand (see brand_of()).
BRAND_OVERRIDES = {
    "18101324": "cartenoire",  # BTC "Aroma Signature", Carte Noire, FR market only
}

# All brands device discovery needs to query for (server-side filtered by
# request, not reported back on individual device objects -- see
# ApiClient.list_devices()).
KNOWN_BRANDS = ("lavazza", "tabli", "cartenoire")


def brand_of(model_code: str) -> str:
  """Derive brand from model code.

  A family can span multiple brands (e.g. BTC has both Lavazza and Carte
  Noire models), so brand is a separate mapping from family — checked via
  BRAND_OVERRIDES first, falling back to family-based defaults (TAB is a
  single-brand family; everything else defaults to Lavazza).

  Args:
    model_code: Device model code (e.g., "18101324").

  Returns:
    Brand key ("lavazza", "tabli", or "cartenoire").
  """
  if model_code in BRAND_OVERRIDES:
    return BRAND_OVERRIDES[model_code]
  return "tabli" if family_of(model_code) == "TAB" else "lavazza"


_catalog_cache: dict[str, dict] = {}


def set_catalog_data(catalogs: dict[str, dict]) -> None:
  """Load catalog data from config_entry (fetched from worker).

  Args:
    catalogs: dict[model_code] → raw catalog dict from GET /catalogs
  """
  _catalog_cache.update(catalogs)


def load_catalog(model_code: str) -> ModelCatalog:
  """Load catalog for a model from the worker-fetched cache.

  The worker's GET /catalogs already returns a fully merged catalog per model
  (common + family + model override applied server-side) — no local merging
  needed here. _catalog_cache (a plain dict, populated by set_catalog_data())
  is already the cache — this must NOT also be @lru_cache'd, or a call made
  before set_catalog_data() runs gets permanently stuck returning that first,
  empty result even after the real data arrives.

  Args:
    model_code: Device model code.

  Returns:
    ModelCatalog for the model, or an empty one if not yet in cache (e.g.
    set_catalog_data() hasn't run for this model — caller should retry after
    the worker fetch completes, not treat this as a permanent failure).
  """
  if model_code not in _catalog_cache:
    _LOGGER.warning("No cached catalog for model %s — worker fetch pending or failed", model_code)
    return _empty_catalog(model_code)

  return _build_catalog_from_dict(model_code, _catalog_cache[model_code])


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

  # Parse push notification states
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
