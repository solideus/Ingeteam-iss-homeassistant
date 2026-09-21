"""Constants and curated register definitions for Ingeteam ISS."""

from __future__ import annotations

from dataclasses import dataclass

DOMAIN = "ingeteam_iss"
DEFAULT_NAME = "Ingeteam ISS"
DEFAULT_PORT = 80
DEFAULT_SCAN_INTERVAL = 15
DEFAULT_DEVICE_ID = 1
DEFAULT_SSE_TIMEOUT = 30
ENERGY_MAX_GAP = 5.0
ENERGY_SAVE_INTERVAL = 60
ENERGY_PUBLISH_INTERVAL = 30
SSE_PATH = "/system/events/sse/stream"
SSE_PHASE_EVENT = "/ems/sse/phases"

CONF_DEVICE_ID = "device_id"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_SSE_TIMEOUT = "sse_timeout"

PLATFORMS = ["sensor", "binary_sensor", "number", "switch", "select", "time"]

GROUP_BATTERY = "battery"
GROUP_GRID_CHARGE = "grid_charge"
GROUP_SCHEDULED_DISCHARGE = "scheduled_discharge"
GROUP_GRID_EXPORT = "grid_export"
GROUP_ENERGY = "energy"

GROUP_NAMES = {
    GROUP_BATTERY: "Gestión de batería",
    GROUP_GRID_CHARGE: "Carga programada desde red",
    GROUP_SCHEDULED_DISCHARGE: "Descarga programada",
    GROUP_GRID_EXPORT: "Red y excedentes",
    GROUP_ENERGY: "Energía",
}


@dataclass(frozen=True, slots=True)
class Register:
    """Decoded register exposed by the inverter HTTP API."""

    address: int
    startbit: int = 0


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
    {"address": 18, "length": 1},
    {"address": 33, "length": 4},
)
