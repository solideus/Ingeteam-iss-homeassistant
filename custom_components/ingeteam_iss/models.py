"""Model profiles: each supported inverter family declares what it can do.

The ISS profile is the original, validated behaviour (reference firmware
ABH1007AE). The STORAGE 1Play map assigns different meanings to several
addresses used by the ISS controls, so that profile only creates the controls
listed in ``control_keys``, each confirmed by its own map and validated with a
write/readback on a real inverter.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from .alarms import ALARM_FIELDS
from .const import HOLDING_RANGES, ONLINE_RANGES
from .sse import SSEEvent, decode_stream, decode_telemetry, decode_telemetry_per_phase

MODEL_ISS = "iss"
MODEL_STORAGE_1PLAY = "storage_1play"
CONF_MODEL = "model"

ISS_ALARM_FIELDS = ALARM_FIELDS

STORAGE_1PLAY_ALARM_FIELDS = {
    10: "inverter_alarm",
    8: "inverter_code_1",
    9: "inverter_code_2",
    55: "inverter_code_3",
    47: "battery_bms_alarm",
}

# Every online register declared by the STORAGE 1Play map (firmware ABH1002AL).
STORAGE_1PLAY_ONLINE_RANGES = (
    {"address": 6, "length": 1},
    {"address": 8, "length": 3},
    {"address": 12, "length": 11},
    {"address": 23, "length": 8},
    {"address": 34, "length": 15},
    {"address": 49, "length": 2},
    {"address": 52, "length": 5},
    {"address": 59, "length": 3},
)


# Only settings whose address, range and meaning are confirmed by the 1Play
# map and validated with a write/readback on a real inverter.
STORAGE_1PLAY_HOLDING_RANGES = ({"address": 123, "length": 1},)
STORAGE_1PLAY_CONTROL_KEYS = ("soc_max",)

CONTROL_DOMAINS = ("number", "switch", "select", "time")


@dataclass(frozen=True, slots=True)
class ModelProfile:
    """Capabilities and register layout of one inverter family."""

    key: str
    platforms: tuple[str, ...]
    online_ranges: tuple[dict, ...]
    holding_ranges: tuple[dict, ...] = ()
    alarm_fields: Mapping[int, str] = field(default_factory=dict)
    decode_telemetry: Callable[[SSEEvent], dict[str, Any] | None] = decode_telemetry
    decode_stream: Callable[[SSEEvent], dict[str, Any] | None] | None = None
    # Online address whose non-zero value means "active power reduction".
    power_reduction_register: int | None = None
    # ISS entity keys whose registers mean something else on this model.
    retired_keys: tuple[str, ...] = ()
    # Writable entities this profile creates; None = the full ISS set.
    control_keys: tuple[str, ...] | None = None

    @property
    def writable(self) -> bool:
        return bool(self.holding_ranges)


PROFILES: dict[str, ModelProfile] = {
    MODEL_ISS: ModelProfile(
        key=MODEL_ISS,
        platforms=("sensor", "binary_sensor", "number", "switch", "select", "time"),
        online_ranges=ONLINE_RANGES,
        holding_ranges=HOLDING_RANGES,
        alarm_fields=ISS_ALARM_FIELDS,
        power_reduction_register=41,
    ),
    MODEL_STORAGE_1PLAY: ModelProfile(
        key=MODEL_STORAGE_1PLAY,
        platforms=("sensor", "binary_sensor", "number"),
        online_ranges=STORAGE_1PLAY_ONLINE_RANGES,
        holding_ranges=STORAGE_1PLAY_HOLDING_RANGES,
        control_keys=STORAGE_1PLAY_CONTROL_KEYS,
        alarm_fields=STORAGE_1PLAY_ALARM_FIELDS,
        decode_telemetry=decode_telemetry_per_phase,
        decode_stream=decode_stream,
        power_reduction_register=59,
        # HTTP 33 does not exist and HTTP 36 is the grid frequency.
        retired_keys=("pv_1_power", "pv_2_power"),
    ),
}

# Firmware families declared in the "compatible" block of /inverter/map.
_FIRMWARE_PREFIXES = {
    "ABH1007": MODEL_ISS,
    "ABH1002": MODEL_STORAGE_1PLAY,
}


def get_profile(model: str | None) -> ModelProfile:
    """Entries created before model selection keep the original ISS profile."""
    return PROFILES.get(model or MODEL_ISS, PROFILES[MODEL_ISS])


def detect_model(capabilities: Mapping[str, Any]) -> str | None:
    """Suggest a profile from the device's own map; None when unknown."""
    compatible = capabilities.get("compatible")
    for item in compatible if isinstance(compatible, list) else []:
        firmware = item.get("firmware") if isinstance(item, dict) else None
        if not isinstance(firmware, str):
            continue
        for prefix, model in _FIRMWARE_PREFIXES.items():
            if firmware.upper().startswith(prefix):
                return model
    return None


def map_firmware(capabilities: Mapping[str, Any]) -> str | None:
    """Firmware reference declared by the inverter map, for diagnostics."""
    compatible = capabilities.get("compatible")
    for item in compatible if isinstance(compatible, list) else []:
        if isinstance(item, dict) and isinstance(item.get("firmware"), str):
            return item["firmware"]
    return None
