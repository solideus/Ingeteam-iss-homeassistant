"""Entity declarations consumed by shared Home Assistant platforms.

A model profile owns instances of these descriptions. Runtime platform classes
must not import model-specific declarations or interpret model identifiers.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.number import NumberEntityDescription
from homeassistant.components.select import SelectEntityDescription
from homeassistant.components.sensor import SensorEntityDescription
from homeassistant.components.switch import SwitchEntityDescription
from homeassistant.components.time import TimeEntityDescription

from ..const import Register


@dataclass(frozen=True, kw_only=True)
class IngeteamSensorDescription(SensorEntityDescription):
    """SSE readings are decoded; remaining online registers require scaling."""

    register: Register = Register(0)
    divisor: float = 1.0
    sse: bool = True
    needs_battery: bool = False


@dataclass(frozen=True, kw_only=True)
class IngeteamNumberDescription(NumberEntityDescription):
    """Writable numeric register description."""

    register: Register
    group: str


@dataclass(frozen=True, kw_only=True)
class IngeteamSelectDescription(SelectEntityDescription):
    """Writable enum register description."""

    register: Register
    group: str


@dataclass(frozen=True, kw_only=True)
class IngeteamSwitchDescription(SwitchEntityDescription):
    """Writable bit-register description."""

    register: Register
    group: str


@dataclass(frozen=True, kw_only=True)
class IngeteamTimeDescription(TimeEntityDescription):
    """Writable hour/minute register description."""

    register: Register
    group: str


@dataclass(frozen=True, kw_only=True)
class OperatingStateDescription:
    """A model-specific binary state and its input channel."""

    key: str
    source: Literal["telemetry", "http"]
    evaluator: Callable[[Mapping[str, Any]], bool | None]
    device_class: BinarySensorDeviceClass | None = None
    enabled_default: bool = True


@dataclass(frozen=True, kw_only=True)
class FlowStateDescription:
    """A normalized model-specific flow state and its stable enum options."""

    key: str
    options: tuple[str, ...]
    evaluator: Callable[[Mapping[str, Any]], str | None]
