"""Reference TL M register layout and conservative mismatch detection."""

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

from ..base import ReadRange

# These ranges cover only the selected user-facing controls.
HOLDING_RANGES = (
    {"address": 58, "length": 8},
    {"address": 86, "length": 1},
    {"address": 100, "length": 1},
    {"address": 117, "length": 17},
    {"address": 142, "length": 1},
)

# Only telemetry not provided by the selected SSE event. This endpoint returns
# raw scaled values; /properties/read returns already-decoded values instead.
ONLINE_RANGES = (
    {"address": 9, "length": 7},
    {"address": 26, "length": 4},
    {"address": 40, "length": 3},
    {"address": 68, "length": 1},
    {"address": 73, "length": 5},
    {"address": 18, "length": 1},
    {"address": 33, "length": 4},
)


HOLDING_READS = tuple(ReadRange(**r) for r in HOLDING_RANGES)
ONLINE_READS = tuple(ReadRange(**r) for r in ONLINE_RANGES)
ALARM_FIELDS = MappingProxyType(
    {
        10: "inverter_alarm",
        12: "inverter_code_1",
        13: "inverter_code_2",
        14: "inverter_code_3",
        28: "battery_alarm",
        73: "bms_warning",
        74: "bms_error",
        75: "bms_fault",
        76: "bms_protection",
    }
)


ALARM_HEX_WIDTHS = MappingProxyType({10: 8})


def validate_map(mapping: Mapping[str, Any]) -> str | None:
    """Reject known old-generation maps; do not certify by firmware ordering.

    Missing maps preserve the previously validated TL M fallback. Unknown
    firmware strings alone do not reject the reference installation.
    """
    compatible = mapping.get("compatible")
    for entry in compatible if isinstance(compatible, list) else ():
        firmware = entry.get("firmware") if isinstance(entry, dict) else None
        if isinstance(firmware, str) and firmware.upper().startswith("ABH1002"):
            return "1Play TL without M is not supported by the TL M profile"
    langs = mapping.get("langs", {})
    labels = langs.get("ENGLISH", {}) if isinstance(langs, dict) else {}
    if not isinstance(labels, dict):
        return None
    signatures = (
        ("holding", 58, "Low battery voltage value for digital output"),
        ("holding", 86, "Duration of Absorption charge"),
        ("holding", 130, "Time for Minimum voltage"),
        ("online", 36, "Grid/Genset. Frequency"),
    )
    for section, address, prefix in signatures:
        items = mapping.get(section)
        for item in items if isinstance(items, list) else ():
            if (
                isinstance(item, dict)
                and item.get("add") == address
                and item.get("start", 0) == 0
            ):
                tid = item.get("tid")
                label = labels.get(tid) if isinstance(tid, str) else None
                if isinstance(label, str) and label.startswith(prefix):
                    return "Map field belongs to unsupported 1Play TL without M"
    return None
