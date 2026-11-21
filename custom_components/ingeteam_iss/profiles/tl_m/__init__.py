"""Only production profile in 0.6.0: INGECON SUN STORAGE 1Play TL M."""

from ..base import ModelProfile
from .entities import NUMBERS, SELECTS, SENSORS, SWITCHES, TIMES
from .registers import (
    ALARM_FIELDS,
    ALARM_HEX_WIDTHS,
    HOLDING_READS,
    ONLINE_READS,
    validate_map,
)
from .states import FLOW_STATES, OPERATING_STATES, battery_available
from .telemetry import TLMTelemetryDecoder

PROFILE = ModelProfile(
    id="tl_m",
    name="INGECON SUN STORAGE 1Play TL M — 2 MPPT",
    reference_firmware="ABH1007AE",
    platforms=("sensor", "binary_sensor", "number", "switch", "select", "time"),
    holding_ranges=HOLDING_READS,
    online_ranges=ONLINE_READS,
    alarm_fields=ALARM_FIELDS,
    alarm_hex_widths=ALARM_HEX_WIDTHS,
    create_decoder=TLMTelemetryDecoder,
    map_validator=validate_map,
    battery_available=battery_available,
    sensors=SENSORS,
    numbers=NUMBERS,
    selects=SELECTS,
    switches=SWITCHES,
    times=TIMES,
    operating_states=OPERATING_STATES,
    flow_states=FLOW_STATES,
)
