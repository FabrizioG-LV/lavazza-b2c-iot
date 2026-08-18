"""Response parsers for non-standard API shapes.

Registered by family for shapes that deviate from default.
Only families with unusual response formats need entries here.
"""

from typing import Any, Callable

from .models import RawState


def parse_state_default(raw: dict[str, Any]) -> RawState:
  """Parse device state response (msg + data.errors/warnings structure).

  Expected raw structure:
    {
      "msg": "1" | "20" | "KO (device offline)" | ... (numeric or special string),
      "data": {
        "lastUpdate": <unix timestamp>,
        "errors": {<key>: bool, ...},
        "warnings": {<key>: bool | int, ...}
      },
      "status": 1,
      "operationId": <uuid>
    }

  Returns:
    RawState with state_code (int or str), error_flags, and warning_flags.
    - state_code: Numeric (1, 20) for normal operation, or string ("offline")
      for special states.
    - error_flags: Error keys (e.g., "tempError") → bool (active/inactive).
    - warning_flags: Warning keys (e.g., "doorOpen", "aromaLevel") → bool|int.
      Most are bool, but some (aromaLevel, grinderPosition) can be int/enum.
  """
  msg = raw.get("msg")
  if msg is None:
    raise ValueError("Missing 'msg' field in state response")

  # Try to parse as int; if fails, keep as string (special state like "offline")
  state_code: int | str
  try:
    state_code = int(msg) if isinstance(msg, str) else msg
  except (ValueError, TypeError):
    # msg is not numeric (e.g., "KO (device offline)"), use as-is
    state_code = msg

  error_flags = {}
  warning_flags = {}
  data = raw.get("data", {})

  # Collect error flags (separate from warnings, preserve bool value)
  errors = data.get("errors", {})
  if errors:
    error_flags.update(errors)

  # Collect warning flags (preserve bool or numeric value, e.g., aromaLevel)
  warnings = data.get("warnings", {})
  if warnings:
    warning_flags.update(warnings)

  return RawState(state_code=state_code, error_flags=error_flags, warning_flags=warning_flags)


# Specialized parsers for families with non-standard shapes
STATE_PARSERS: dict[str, Callable[[dict[str, Any]], RawState]] = {}


def get_state_parser(family: str) -> Callable[[dict[str, Any]], RawState]:
  """Get parser for family, falls back to default."""
  return STATE_PARSERS.get(family, parse_state_default)
