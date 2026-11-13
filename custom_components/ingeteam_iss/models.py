"""Model profiles: each supported inverter family declares what it can do.

Both families are INGECON SUN STORAGE 1Play inverters:

* ``iss`` - **1Play TL M, 2 MPPT**: the original, validated behaviour
  (reference portal firmware ABH1007AE, tested on a 6TL M).
* ``storage_1play`` - **1Play TL without M, 1 MPPT**: experimental profile
  based on one 6TL installation (inverter map ABH1002AL).

Several holding and online addresses exist in both maps with different
meanings, so a profile is only accepted when the device's own map does not
contradict it (``profile_conflict``), and writes are limited to the fields of
the controls the profile creates.
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
STORAGE_1PLAY_HOLDING_RANGES = (
    {"address": 116, "length": 1},
    {"address": 123, "length": 3},
    {"address": 128, "length": 2},
    {"address": 132, "length": 1},
)
STORAGE_1PLAY_CONTROL_KEYS = (
    "soc_max",
    "soc_grid",
    "soc_min",
    "max_grid_charge_power",
    "max_grid_injection_power",
    "bms_max_charge_current",
    "battery_charge_priority",
    "battery_backup",
)


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
        platforms=("sensor", "binary_sensor", "number", "switch", "select"),
        online_ranges=STORAGE_1PLAY_ONLINE_RANGES,
        holding_ranges=STORAGE_1PLAY_HOLDING_RANGES,
        control_keys=STORAGE_1PLAY_CONTROL_KEYS,
        alarm_fields=STORAGE_1PLAY_ALARM_FIELDS,
        decode_telemetry=decode_telemetry_per_phase,
        decode_stream=decode_stream,
        power_reduction_register=59,
    ),
}

# Firmware families declared in the "compatible" block of /inverter/map.
# The TL M reference distinguishes portal firmware ABH1007AE from the internal
# map ABH1006AC, so both prefixes identify that family.
_FIRMWARE_PREFIXES = {
    "ABH1007": MODEL_ISS,
    "ABH1006": MODEL_ISS,
    "ABH1002": MODEL_STORAGE_1PLAY,
}

# Map entries characteristic of the 1Play TL without M (map ABH1002AL). Each
# one contradicts a field the TL M profile reads or writes at that address.
STORAGE_1PLAY_SIGNATURES = (
    ("holding", 58, 0, "Low battery voltage value for digital output"),
    ("holding", 86, 0, "Duration of Absorption charge"),
    ("holding", 130, 0, "Time for Minimum voltage"),
    ("online", 36, 0, "Grid/Genset. Frequency"),
)

# English label each 1Play control must have in the device map.
STORAGE_1PLAY_CONTROL_LABELS = {
    (123, 0): "SOCmax",
    (124, 0): "SOCgrid",
    (125, 0): "SOCmin",
    (128, 0): "Maximum battery charging power from the grid",
    (129, 0): "Maximum power injected to the grid",
    (116, 0): "Maximum Charge Current",
    (132, 4): "Battery Charging Priority",
    (132, 1): "Battery-Backup Function",
}


def get_profile(model: str | None) -> ModelProfile:
    """Entries created before model selection keep the original ISS profile."""
    return PROFILES.get(model or MODEL_ISS, PROFILES[MODEL_ISS])


def _firmware_model(capabilities: Mapping[str, Any]) -> str | None:
    compatible = capabilities.get("compatible")
    for item in compatible if isinstance(compatible, list) else []:
        firmware = item.get("firmware") if isinstance(item, dict) else None
        if not isinstance(firmware, str):
            continue
        for prefix, model in _FIRMWARE_PREFIXES.items():
            if firmware.upper().startswith(prefix):
                return model
    return None


def map_label(
    capabilities: Mapping[str, Any], section: str, address: int, bit: int = 0
) -> str | None:
    """English label of one map field, or None when it is not declared."""
    fields = capabilities.get(section)
    langs = capabilities.get("langs")
    labels = langs.get("ENGLISH") if isinstance(langs, dict) else None
    for item in fields if isinstance(fields, list) else []:
        if (
            isinstance(item, dict)
            and item.get("add") == address
            and item.get("start", 0) == bit
        ):
            tid = item.get("tid")
            label = labels.get(tid) if isinstance(labels, dict) else None
            return label if isinstance(label, str) else ""
    return None


def storage_1play_evidence(capabilities: Mapping[str, Any]) -> list[str]:
    """Map entries that identify a 1Play TL without M."""
    found = []
    for section, address, bit, prefix in STORAGE_1PLAY_SIGNATURES:
        label = map_label(capabilities, section, address, bit)
        if label and label.startswith(prefix):
            found.append(f"{section} {address}.{bit}: {label}")
    return found


def detect_model(capabilities: Mapping[str, Any]) -> str | None:
    """Suggest a profile from the device's own map; None when unknown."""
    if storage_1play_evidence(capabilities):
        return MODEL_STORAGE_1PLAY
    return _firmware_model(capabilities)


def profile_conflict(model: str | None, capabilities: Mapping[str, Any]) -> str | None:
    """Reason why the map contradicts the profile, or None when compatible.

    Entries created before model selection (``model`` None) are checked as
    TL M. Without a map the TL M profile keeps its historical behaviour,
    whereas the experimental 1Play profile needs positive identification.
    """
    profile = get_profile(model)
    evidence = storage_1play_evidence(capabilities)
    firmware_model = _firmware_model(capabilities)
    if profile.key == MODEL_ISS:
        if evidence:
            return "1Play TL (without M) map: " + "; ".join(evidence)
        if firmware_model == MODEL_STORAGE_1PLAY:
            return f"map firmware {map_firmware(capabilities)}"
        return None
    if firmware_model == MODEL_ISS:
        return f"1Play TL M map firmware {map_firmware(capabilities)}"
    if not evidence:
        return "the map does not identify a 1Play TL without M"
    for (address, bit), prefix in STORAGE_1PLAY_CONTROL_LABELS.items():
        label = map_label(capabilities, "holding", address, bit)
        if not label or not label.startswith(prefix):
            return f"holding {address}.{bit} is not '{prefix}' in this map"
    return None


def map_firmware(capabilities: Mapping[str, Any]) -> str | None:
    """Firmware reference declared by the inverter map, for diagnostics."""
    compatible = capabilities.get("compatible")
    for item in compatible if isinstance(compatible, list) else []:
        if isinstance(item, dict) and isinstance(item.get("firmware"), str):
            return item["firmware"]
    return None
