"""Dynamic polling interval override manager for in-progress device operations."""

import logging
from datetime import timedelta
from typing import Callable

_LOGGER = logging.getLogger(__name__)


class PollOverrideManager:
  """Manage dynamic polling interval overrides tied to command execution state."""

  def __init__(self, on_override_changed: Callable[[timedelta], None]) -> None:
    """Initialize manager.

    Args:
      on_override_changed: Callback fired when active override interval changes.
    """
    self._on_override_changed = on_override_changed
    # device_serial -> (interval, busy_states, max_busy_seconds)
    self._active_overrides: dict[str, tuple[timedelta, set[int], int]] = {}
    self._current_min_interval: timedelta | None = None

  def apply(
      self,
      device_serial: str,
      interval: timedelta,
      busy_states: set[int],
      max_busy_seconds: int = 600,
  ) -> None:
    """Apply polling override for device.

    Args:
      device_serial: Device identifier.
      interval: Override interval during busy state.
      busy_states: Set of state codes indicating in-progress operation.
      max_busy_seconds: Fallback timeout if device stays busy too long.
    """
    self._active_overrides[device_serial] = (interval, busy_states, max_busy_seconds)
    self._recompute()

  def on_device_state_update(self, device_serial: str, state_code: int) -> None:
    """Called when device state updates.

    Removes override if device is no longer in busy_states.
    """
    if device_serial in self._active_overrides:
      _, busy_states, _ = self._active_overrides[device_serial]
      if state_code not in busy_states:
        del self._active_overrides[device_serial]
        self._recompute()

  def _recompute(self) -> None:
    """Recompute minimum active interval and notify if changed."""
    if not self._active_overrides:
      new_min = None
    else:
      intervals = [interval for interval, _, _ in self._active_overrides.values()]
      new_min = min(intervals) if intervals else None

    if new_min != self._current_min_interval:
      self._current_min_interval = new_min
      if new_min is not None:
        self._on_override_changed(new_min)

  def current_override(self) -> timedelta | None:
    """Get currently active minimum override interval."""
    return self._current_min_interval
