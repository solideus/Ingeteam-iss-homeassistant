"""Reference TL M decoder, extracted unchanged from v0.5.3."""

import json

from ...const import SSE_PHASE_EVENT
from ...sse import SSEEvent, finite_number


def decode_telemetry(event: SSEEvent) -> dict[str, float | None] | None:
    """Select the observed aggregate phase (4); never sum it with phases 1–3.

    Retain only existing sensors and the four directional energy sources.
    Missing values replace previous values with None, rather than staying stale.
    """
    if event.event != SSE_PHASE_EVENT:
        return None
    try:
        payload = json.loads(event.data)
    except ValueError, RecursionError:
        return None
    phases = payload.get("Phases") if isinstance(payload, dict) else None
    if not isinstance(phases, list):
        return None
    selected = [p for p in phases if isinstance(p, dict) and p.get("Phase") == 4]
    if len(selected) != 1:
        return None
    phase = selected[0]
    pv = finite_number(phase.get("pv"), minimum=0)
    load = finite_number(phase.get("cons"), minimum=0)
    grid = finite_number(phase.get("W"))
    if all(value is None for value in (pv, load, grid)):
        return None
    status = finite_number(phase.get("StatusBat"), minimum=0)
    if status is not None and not status.is_integer():
        status = None
    # Code 7 is observed with "battery not available" on the reference firmware.
    # Do not infer disconnection from a legitimate SOC=0 or power=0 alone.
    battery_valid = status is not None and status != 7
    soc = finite_number(phase.get("soc"), minimum=0) if battery_valid else None
    if soc is not None and soc > 100:
        soc = None
    charge = finite_number(phase.get("PacCharge"), minimum=0) if battery_valid else None
    discharge = (
        finite_number(phase.get("PacDischarge"), minimum=0) if battery_valid else None
    )
    result = {
        "pv_total_power": pv,
        "total_load_power": load,
        "external_grid_power": grid,
        "grid_import_power": max(grid, 0) if grid is not None else None,
        "grid_export_power": max(-grid, 0) if grid is not None else None,
        "battery_soc": soc,
        "battery_voltage": finite_number(phase.get("vbat"), minimum=0)
        if battery_valid
        else None,
        "battery_charge_power": charge,
        "battery_discharge_power": discharge,
        "battery_power": discharge - charge
        if charge is not None and discharge is not None
        else None,
        "battery_status": status,
    }
    result["inverter_status"] = finite_number(phase.get("S1P_StatusCode"))
    return result


class TLMTelemetryDecoder:
    def decode(self, event: SSEEvent, now: float) -> dict | None:
        return decode_telemetry(event)

    def is_sample_event(self, event: SSEEvent) -> bool:
        return event.event == SSE_PHASE_EVENT

    def reset(self) -> None:
        """The TL M decoder has no cross-event state."""
