"""Bounded SSE framing and curated telemetry, independent of Home Assistant."""

from __future__ import annotations

import codecs
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from math import isfinite
from typing import Any

from .const import SSE_PHASE_EVENT, SSE_STREAM_EVENT

MAX_EVENT_SIZE = 262_144


@dataclass(frozen=True)
class SSEEvent:
    """One complete SSE event, never a network chunk."""

    event: str
    data: str


async def iter_sse(chunks: AsyncIterator[bytes]) -> AsyncIterator[SSEEvent]:
    """Handle split UTF-8, LF/CR/CRLF, comments and multiline data.

    Incomplete events at EOF are discarded. A malformed/oversized stream raises
    ValueError and is reconnected by the caller. No payload is logged.
    """
    decoder = codecs.getincrementaldecoder("utf-8-sig")()
    line = ""
    skip_lf = False
    event_type = "message"
    data: list[str] = []
    size = 0
    async for chunk in chunks:
        for char in decoder.decode(chunk):
            if skip_lf:
                skip_lf = False
                if char == "\n":
                    continue
            if char not in "\r\n":
                line += char
                if len(line) + size > MAX_EVENT_SIZE:
                    raise ValueError("SSE event too large")
                continue
            skip_lf = char == "\r"
            if not line:
                if data:
                    yield SSEEvent(event_type, "\n".join(data))
                event_type, data, size = "message", [], 0
            elif not line.startswith(":"):
                field, _, value = line.partition(":")
                if value.startswith(" "):
                    value = value[1:]
                if field == "event":
                    event_type = value
                elif field == "data":
                    data.append(value)
                    size += len(value) + 1
                    if size > MAX_EVENT_SIZE:
                        raise ValueError("SSE event too large")
            line = ""
    decoder.decode(b"", final=True)


def finite_number(value: Any, *, minimum: float | None = None) -> float | None:
    """Reject absent, boolean, non-numeric, non-finite and invalid-sign values."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except ValueError, OverflowError:
        return None
    if not isfinite(number) or (minimum is not None and number < minimum):
        return None
    return number


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


def decode_telemetry_per_phase(event: SSEEvent) -> dict[str, float | None] | None:
    """STORAGE 1Play: phases 1-3 only, without the aggregate phase 4.

    Observed on comms firmware AAX1055DC (inverter map ABH1002AL): the event
    carries per-phase ``W``, ``PacPVBatt``, ``PdcPVStorage``, ``PacCharge``,
    ``PacDischarge`` and the shared ``EMS_SOC``/``EMS_VBAT``. Battery and
    inverter status codes only arrive in ``/ems/sse/stream`` (see
    ``decode_stream``) and are merged by the telemetry coordinator.

    Grid power is the sum of ``W`` (positive = import). The inverter AC output
    is the sum of ``PacPVBatt``; household load = inverter output + grid.
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
    if any(isinstance(p, dict) and p.get("Phase") == 4 for p in phases):
        # A firmware with the aggregate phase is decoded the ISS way.
        return decode_telemetry(event)
    numbers = [p.get("Phase") if isinstance(p, dict) else None for p in phases]
    if not all(type(n) is int for n in numbers) or sorted(numbers) != [1, 2, 3]:
        # Exactly one phase 1, 2 and 3, as the inverter sends even on
        # single-phase systems. Duplicated or missing phases would add or
        # silently drop power, so the whole event is rejected.
        return None
    rows = sorted(phases, key=lambda p: p["Phase"])

    def total(key: str, minimum: float | None = None) -> float | None:
        values = [finite_number(p.get(key)) for p in rows]
        if any(value is None for value in values):
            return None  # A missing value in any phase is not zero watts.
        value = sum(values)
        return None if minimum is not None and value < minimum else value

    grid = total("W")
    inverter_ac = total("PacPVBatt")
    pv = total("PdcPVStorage", minimum=0)
    if grid is None and inverter_ac is None and pv is None:
        return None
    load = (
        max(inverter_ac + grid, 0)
        if grid is not None and inverter_ac is not None
        else None
    )
    soc = finite_number(rows[0].get("EMS_SOC"), minimum=0)
    if soc is not None and soc > 100:
        soc = None
    charge = total("PacCharge", minimum=0)
    discharge = total("PacDischarge", minimum=0)
    return {
        "pv_total_power": pv,
        "total_load_power": load,
        "external_grid_power": grid,
        "grid_import_power": max(grid, 0) if grid is not None else None,
        "grid_export_power": max(-grid, 0) if grid is not None else None,
        "battery_soc": soc,
        "battery_voltage": finite_number(rows[0].get("EMS_VBAT"), minimum=0),
        "battery_charge_power": charge,
        "battery_discharge_power": discharge,
        "battery_power": discharge - charge
        if charge is not None and discharge is not None
        else None,
        "battery_status": None,
        "inverter_status": None,
    }


def decode_stream(event: SSEEvent) -> dict[str, float] | None:
    """Status codes from ``/ems/sse/stream`` (STORAGE 1Play).

    ``StatusBat`` follows the map's battery status type (1 discharging,
    2 constant-current charging, 7 not configured); ``StatusCode`` 3 is
    reported together with ``"Status": "On-grid"``.
    """
    if event.event != SSE_STREAM_EVENT:
        return None
    try:
        payload = json.loads(event.data)
    except ValueError, RecursionError:
        return None
    devices = payload.get("Devices") if isinstance(payload, dict) else None
    if not isinstance(devices, list):
        return None
    device = next(
        (d for d in devices if isinstance(d, dict) and "StatusCode" in d), None
    )
    if device is None:
        return None
    result = {}
    for source, target in (
        ("StatusBat", "battery_status"),
        ("StatusCode", "inverter_status"),
    ):
        value = finite_number(device.get(source), minimum=0)
        if value is not None and value.is_integer():
            result[target] = value
    return result or None
