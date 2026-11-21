"""Immutable profile contracts; runtime services do not interpret model names."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from ..sse import SSEEvent
from .descriptions import (
    FlowStateDescription,
    IngeteamNumberDescription,
    IngeteamSelectDescription,
    IngeteamSensorDescription,
    IngeteamSwitchDescription,
    IngeteamTimeDescription,
    OperatingStateDescription,
)


class UnsupportedProfileError(ValueError):
    """Unknown profile or a map known to belong to another inverter."""


class TelemetryDecoder(Protocol):
    """One decoder instance per config entry; no shared mutable sample state."""

    def decode(self, event: SSEEvent, now: float) -> dict[str, Any] | None: ...
    def is_sample_event(self, event: SSEEvent) -> bool: ...
    def reset(self) -> None: ...


@dataclass(frozen=True, slots=True)
class ReadRange:
    address: int
    length: int

    def payload(self) -> dict[str, int]:
        return {"address": self.address, "length": self.length}


@dataclass(frozen=True, slots=True)
class ModelProfile:
    id: str
    name: str
    reference_firmware: str
    platforms: tuple[str, ...]
    holding_ranges: tuple[ReadRange, ...]
    online_ranges: tuple[ReadRange, ...]
    alarm_fields: Mapping[int, str]
    alarm_hex_widths: Mapping[int, int]
    create_decoder: Callable[[], TelemetryDecoder]
    map_validator: Callable[[Mapping[str, Any]], str | None]
    battery_available: Callable[[Mapping[str, Any]], bool]
    sensors: tuple[IngeteamSensorDescription, ...]
    numbers: tuple[IngeteamNumberDescription, ...]
    selects: tuple[IngeteamSelectDescription, ...]
    switches: tuple[IngeteamSwitchDescription, ...]
    times: tuple[IngeteamTimeDescription, ...]
    operating_states: tuple[OperatingStateDescription, ...]
    flow_states: tuple[FlowStateDescription, ...]

    def validate_map(self, capabilities: Mapping[str, Any]) -> None:
        if reason := self.map_validator(capabilities):
            raise UnsupportedProfileError(reason)

    def validate_writes(self, values: list[tuple[int, int, int]]) -> None:
        """Validate a complete operation before any field reaches the API."""
        fields = {}
        for desc in self.numbers:
            fields[desc.register.address, desc.register.startbit] = (
                desc.native_min_value,
                desc.native_max_value,
            )
        for desc in self.selects:
            fields[desc.register.address, desc.register.startbit] = (
                0,
                len(desc.options) - 1,
            )
        for desc in self.switches:
            fields[desc.register.address, desc.register.startbit] = (0, 1)
        for desc in self.times:
            fields[desc.register.address, 0] = (0, 59)
            fields[desc.register.address, 8] = (0, 23)
        if not values:
            raise UnsupportedProfileError("Empty write operation")
        for address, bit, value in values:
            bounds = fields.get((address, bit))
            if (
                type(address) is not int
                or type(bit) is not int
                or bounds is None
                or type(value) is not int
                or not bounds[0] <= value <= bounds[1]
            ):
                raise UnsupportedProfileError(
                    "Unsupported field or value for selected profile"
                )
