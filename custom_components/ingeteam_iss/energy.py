"""Left-rule energy accumulation with per-channel validity and gap protection."""

from __future__ import annotations

from collections.abc import Mapping

from .const import ENERGY_MAX_GAP
from .sse import finite_number

ENERGY_SOURCES = {
    "pv_energy": "pv_total_power",
    "load_energy": "total_load_power",
    "grid_import_energy": "grid_import_power",
    "grid_export_energy": "grid_export_power",
    "battery_charge_energy": "battery_charge_power",
    "battery_discharge_energy": "battery_discharge_power",
}


class EnergyAccumulator:
    """Integrate W to kWh using actual monotonic reception intervals.

    Both ends must be valid and no more than max_gap seconds apart. Identical
    samples still count; no time is invented beyond the last received sample.
    Persistence restores totals ONLY, never an integration time anchor.
    """

    def __init__(self, max_gap: float = ENERGY_MAX_GAP) -> None:
        self.max_gap = max_gap
        self.totals = dict.fromkeys(ENERGY_SOURCES, 0.0)
        self._previous: dict[str, tuple[float, float]] = {}

    def restore(self, totals: Mapping) -> None:
        for key in ENERGY_SOURCES:
            value = finite_number(totals.get(key), minimum=0)
            if value is not None:
                self.totals[key] = value
        self.break_interval()

    def break_interval(self) -> None:
        """Discard all anchors on disconnection, stop or restart."""
        self._previous.clear()

    def update(self, sample: Mapping[str, float | None], now: float) -> bool:
        """Advance only channels having a complete trustworthy interval."""
        changed = False
        for key, source in ENERGY_SOURCES.items():
            value = finite_number(sample.get(source), minimum=0)
            previous = self._previous.pop(key, None)
            if value is None:
                continue
            if previous is not None:
                then, power = previous
                elapsed = now - then
                if 0 < elapsed <= self.max_gap:
                    increment = power * elapsed / 3_600_000
                    total = finite_number(self.totals[key] + increment, minimum=0)
                    if total is not None and increment > 0:
                        self.totals[key] = total
                        changed = True
            self._previous[key] = (now, value)
        return changed
