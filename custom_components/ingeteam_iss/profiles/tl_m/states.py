"""Operating-state interpretation of the reference INGECON SUN STORAGE TL M."""

from collections.abc import Mapping
from typing import Any

from ...sse import finite_number
from ..descriptions import FlowStateDescription, OperatingStateDescription


def battery_available(sample: Mapping[str, Any]) -> bool:
    """Keep the 0.5.3 battery-current availability rule unchanged."""
    return sample.get("battery_status") not in (None, 7)


def pv_active(data: Mapping[str, Any]) -> bool | None:
    power = data.get("pv_total_power")
    return power > 10 if power is not None else None


def grid_connected(data: Mapping[str, Any]) -> bool | None:
    status = data.get("inverter_status")
    return True if status in (3, 4, 8) else False if status in (2, 11) else None


def power_reduction(data: Mapping[str, Any]) -> bool | None:
    reason = finite_number(data.get("online", {}).get((41, 0)), minimum=0)
    if reason is None or not reason.is_integer():
        return None
    return reason != 0


OPERATING_STATES = (
    OperatingStateDescription(key="pv_active", source="telemetry", evaluator=pv_active),
    OperatingStateDescription(
        key="grid_connected", source="telemetry", evaluator=grid_connected
    ),
    OperatingStateDescription(
        key="power_reduction",
        source="http",
        evaluator=power_reduction,
        enabled_default=False,
    ),
)


def _flow_state(value, positive: str, negative: str) -> str | None:
    value = finite_number(value)
    if value is None:
        return None
    return positive if value > 10 else negative if value < -10 else "idle"


def grid_flow(data: Mapping[str, Any]) -> str | None:
    return _flow_state(data.get("external_grid_power"), "importing", "exporting")


def battery_flow(data: Mapping[str, Any]) -> str | None:
    # Missing status and status 7 intentionally differ in the original TL M
    # behavior: only the explicit observed status 7 publishes not_available.
    if data.get("battery_status") == 7:
        return "not_available"
    return _flow_state(data.get("battery_power"), "discharging", "charging")


FLOW_STATES = (
    FlowStateDescription(
        key="grid_flow",
        options=("importing", "exporting", "idle"),
        evaluator=grid_flow,
    ),
    FlowStateDescription(
        key="battery_flow",
        options=("charging", "discharging", "idle", "not_available"),
        evaluator=battery_flow,
    ),
)
