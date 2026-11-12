"""Curated SSE/HTTP telemetry and persistent integrated energy sensors."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfReactivePower,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .accounting import ACCOUNTING_KEYS
from .alarms import flow_state, label_for, raw_integer
from .const import ENERGY_PUBLISH_INTERVAL, GROUP_ENERGY, Register
from .coordinator import IngeteamCoordinator
from .diagnostics import telemetry_diagnostics
from .energy import ENERGY_SOURCES
from .entity import IngeteamEntity
from .models import MODEL_STORAGE_1PLAY
from .values import scaled_sum


@dataclass(frozen=True, kw_only=True)
class IngeteamSensorDescription(SensorEntityDescription):
    """SSE readings are decoded; remaining online registers require scaling."""

    register: Register = Register(0)
    divisor: float = 1.0
    sse: bool = True
    # Gate the reading on a valid battery status (ISS battery current).
    needs_battery: bool = False


def power_description(
    key: str, *, register: Register = Register(0), sse: bool = True
) -> IngeteamSensorDescription:
    return IngeteamSensorDescription(
        key=key,
        translation_key=key,
        register=register,
        sse=sse,
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    )


SENSORS: tuple[IngeteamSensorDescription, ...] = (
    power_description("pv_total_power"),
    IngeteamSensorDescription(
        key="battery_soc",
        translation_key="battery_soc",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    power_description("battery_power"),
    IngeteamSensorDescription(
        key="battery_voltage",
        translation_key="battery_voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    IngeteamSensorDescription(
        key="battery_current",
        translation_key="battery_current",
        register=Register(18),
        divisor=100,
        sse=False,
        needs_battery=True,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    power_description("pv_1_power", register=Register(33), sse=False),
    power_description("pv_2_power", register=Register(36), sse=False),
    power_description("total_load_power"),
    power_description("external_grid_power"),
    power_description("grid_import_power"),
    power_description("grid_export_power"),
    power_description("battery_charge_power"),
    power_description("battery_discharge_power"),
)

# SSE readings shared by every model (same keys, so same unique IDs).
_COMMON_SSE_KEYS = (
    "pv_total_power",
    "battery_soc",
    "battery_power",
    "battery_voltage",
    "total_load_power",
    "external_grid_power",
    "grid_import_power",
    "grid_export_power",
    "battery_charge_power",
    "battery_discharge_power",
)


def online_description(
    key: str,
    address: int,
    divisor: float,
    unit: str | None,
    device_class: SensorDeviceClass | None,
    *,
    diagnostic: bool = False,
    enabled: bool = True,
    state_class: SensorStateClass | None = SensorStateClass.MEASUREMENT,
) -> IngeteamSensorDescription:
    """One scaled online register of the STORAGE 1Play map.

    Divisors follow the map's ``sc`` field: value = raw * sc / 100000.
    """
    return IngeteamSensorDescription(
        key=key,
        translation_key=key,
        register=Register(address),
        divisor=divisor,
        sse=False,
        native_unit_of_measurement=unit,
        device_class=device_class,
        state_class=state_class,
        entity_category=EntityCategory.DIAGNOSTIC if diagnostic else None,
        entity_registry_enabled_default=enabled,
    )


_V = UnitOfElectricPotential.VOLT
_A = UnitOfElectricCurrent.AMPERE
_W = UnitOfPower.WATT
_HZ = UnitOfFrequency.HERTZ
_C = UnitOfTemperature.CELSIUS
_VAR = UnitOfReactivePower.VOLT_AMPERE_REACTIVE
_SDC = SensorDeviceClass

STORAGE_1PLAY_SENSORS: tuple[IngeteamSensorDescription, ...] = (
    *(desc for desc in SENSORS if desc.key in _COMMON_SSE_KEYS),
    online_description("battery_current", 15, 100, _A, _SDC.CURRENT),
    online_description("battery_soh", 18, 1, PERCENTAGE, None),
    online_description("battery_temperature", 22, 10, _C, _SDC.TEMPERATURE),
    online_description(
        "battery_max_charge_current", 19, 100, _A, _SDC.CURRENT, diagnostic=True
    ),
    online_description(
        "battery_max_discharge_current", 20, 100, _A, _SDC.CURRENT, diagnostic=True
    ),
    online_description(
        "battery_charge_voltage", 52, 10, _V, _SDC.VOLTAGE, diagnostic=True
    ),
    online_description(
        "battery_discharge_voltage", 53, 10, _V, _SDC.VOLTAGE, diagnostic=True
    ),
    online_description("pv_voltage", 23, 1, _V, _SDC.VOLTAGE),
    online_description("pv_current", 24, 100, _A, _SDC.CURRENT),
    online_description("ac_loads_voltage", 26, 1, _V, _SDC.VOLTAGE),
    online_description("ac_loads_current", 27, 100, _A, _SDC.CURRENT),
    online_description("ac_loads_frequency", 28, 100, _HZ, _SDC.FREQUENCY),
    online_description("ac_loads_power", 29, 1, _W, _SDC.POWER),
    online_description(
        "ac_loads_reactive_power",
        30,
        1,
        _VAR,
        _SDC.REACTIVE_POWER,
        diagnostic=True,
        enabled=False,
    ),
    online_description("grid_voltage", 34, 1, _V, _SDC.VOLTAGE),
    online_description("grid_current", 35, 100, _A, _SDC.CURRENT),
    online_description("grid_frequency", 36, 100, _HZ, _SDC.FREQUENCY),
    online_description("grid_active_power", 37, 1, _W, _SDC.POWER),
    online_description(
        "grid_reactive_power",
        38,
        1,
        _VAR,
        _SDC.REACTIVE_POWER,
        diagnostic=True,
        enabled=False,
    ),
    online_description(
        "grid_power_factor",
        54,
        1000,
        None,
        _SDC.POWER_FACTOR,
        diagnostic=True,
        enabled=False,
    ),
    online_description("dc_bus_voltage", 39, 1, _V, _SDC.VOLTAGE, diagnostic=True),
    online_description(
        "residual_current",
        48,
        1,
        UnitOfElectricCurrent.MILLIAMPERE,
        _SDC.CURRENT,
        diagnostic=True,
    ),
    online_description("heatsink_temperature", 40, 10, _C, _SDC.TEMPERATURE),
    online_description(
        "electronics_temperature", 41, 10, _C, _SDC.TEMPERATURE, diagnostic=True
    ),
    online_description(
        "pt100_temperature",
        42,
        10,
        _C,
        _SDC.TEMPERATURE,
        diagnostic=True,
        enabled=False,
    ),
    online_description(
        "isolation_resistance_positive",
        43,
        1,
        "kΩ",
        None,
        diagnostic=True,
        enabled=False,
    ),
    online_description(
        "isolation_resistance_negative",
        44,
        1,
        "kΩ",
        None,
        diagnostic=True,
        enabled=False,
    ),
    online_description(
        "operation_time",
        6,
        1,
        UnitOfTime.HOURS,
        _SDC.DURATION,
        diagnostic=True,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    online_description(
        "power_reduction_ratio", 60, 10, PERCENTAGE, None, diagnostic=True
    ),
)

# Enumerated online registers shown with the labels of the device's own map.
STORAGE_1PLAY_STATES = (
    ("inverter_state", 12, False),
    ("battery_state", 21, False),
    ("power_reduction_reason", 59, True),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[IngeteamCoordinator],
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Preserve all old unique IDs; add only energy-related/diagnostic entities."""
    owner = entry.runtime_data
    storage_1play = owner.profile.key == MODEL_STORAGE_1PLAY
    descriptions = STORAGE_1PLAY_SENSORS if storage_1play else SENSORS
    async_add_entities(
        [
            *(
                IngeteamSensor(owner, desc)
                for desc in descriptions
                # The ISS entity set is unchanged; 1Play follows its own map.
                if not storage_1play
                or desc.sse
                or owner.api.supports("online", desc.register.address)
            ),
            *(
                IngeteamMapStateSensor(owner, key, address, diagnostic)
                for key, address, diagnostic in (
                    STORAGE_1PLAY_STATES if storage_1play else ()
                )
                if owner.api.supports("online", address)
            ),
            *(IngeteamEnergySensor(owner, key) for key in ENERGY_SOURCES),
            *(IngeteamCalendarSensor(owner, key) for key in ACCOUNTING_KEYS),
            IngeteamFlowSensor(owner, "grid_flow", ["importing", "exporting", "idle"]),
            IngeteamFlowSensor(
                owner,
                "battery_flow",
                ["charging", "discharging", "idle", "not_available"],
            ),
            IngeteamAlarmSensor(owner),
            IngeteamSSEDiagnostics(owner),
            IngeteamTimestampSensor(owner, "sse_last_event", "last_event"),
            IngeteamTimestampSensor(owner, "sse_last_disconnect", "last_disconnect"),
        ]
    )


class IngeteamSensor(IngeteamEntity, SensorEntity):
    """One existing or directional power sensor."""

    entity_description: IngeteamSensorDescription

    def __init__(
        self, owner: IngeteamCoordinator, description: IngeteamSensorDescription
    ) -> None:
        super().__init__(
            owner.telemetry if description.sse else owner, description.register
        )
        self.owner = owner
        self.entity_description = description
        self._attr_unique_id = f"{self._serial}_{description.key}"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self.entity_description.needs_battery:
            self.async_on_remove(
                self.owner.telemetry.async_add_listener(self._handle_coordinator_update)
            )

    @property
    def available(self) -> bool:
        return self.native_value is not None

    @property
    def native_value(self) -> int | float | None:
        if self.entity_description.sse:
            if not self.owner.telemetry.connected:
                return None
            value = self.coordinator.data.get(self.entity_description.key)
            return (
                int(value) if isinstance(value, float) and value.is_integer() else value
            )
        if not self.owner.last_update_success:
            return None
        if self.entity_description.needs_battery and (
            not self.owner.telemetry.connected
            or self.owner.telemetry.data.get("battery_status") in (None, 7)
        ):
            return None
        return scaled_sum(
            (self.coordinator.data or {}).get("online", {}),
            ((self.register.address, self.register.startbit),),
            self.entity_description.divisor,
        )


class IngeteamEnergySensor(IngeteamEntity, SensorEntity):
    """Lifetime calculated kWh, retained while its source is unavailable."""

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_suggested_display_precision = 3

    def __init__(self, owner: IngeteamCoordinator, key: str) -> None:
        super().__init__(owner.telemetry, Register(0), GROUP_ENERGY)
        self._key = key
        self._last_publish = 0.0
        self._attr_unique_id = f"{self._serial}_{key}"
        self._attr_translation_key = key

    @callback
    def _handle_coordinator_update(self) -> None:
        """Accumulate every event, but limit energy Recorder traffic."""
        now = self.coordinator.hass.loop.time()
        if (
            not self.coordinator.connected
            or now - self._last_publish >= ENERGY_PUBLISH_INTERVAL
        ):
            self._last_publish = now
            self.async_write_ha_state()

    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self) -> float:
        # Do not round individual increments. Rounded output is only for state
        # publishing; persistence retains full internal precision.
        return round(self.coordinator.energy.totals[self._key], 6)


class IngeteamTimestampSensor(IngeteamEntity, SensorEntity):
    """Optional timestamps; disabled by default to limit Recorder traffic."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(self, owner: IngeteamCoordinator, key: str, field: str) -> None:
        super().__init__(owner.telemetry, Register(0))
        self._field = field
        self._attr_unique_id = f"{self._serial}_{key}"
        self._attr_translation_key = key

    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self) -> datetime | None:
        return getattr(self.coordinator, self._field)


class IngeteamCalendarSensor(IngeteamEnergySensor):
    """Calendar meters reset; settled net meters are persistent lifetime totals."""

    def __init__(self, owner, key):
        super().__init__(owner, key)
        self._period_value: float | None = None
        self._attr_state_class = (
            SensorStateClass.MEASUREMENT
            if key == "hourly_net_balance"
            else SensorStateClass.TOTAL_INCREASING
        )
        if key == "hourly_net_balance":
            # Signed hourly balance is not a cumulative Energy dashboard input.
            self._attr_device_class = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            self.coordinator.async_add_calendar_listener(
                self._key, self._handle_period_update
            )
        )

    @callback
    def _handle_period_update(self, value: float) -> None:
        """Publish final/reset values even inside the inherited 30-second gate."""
        self._period_value = value
        self._last_publish = self.coordinator.hass.loop.time()
        try:
            self.async_write_ha_state()
        finally:
            self._period_value = None

    @property
    def native_value(self):
        if self._period_value is not None:
            return round(self._period_value, 6)
        return round(self.coordinator.accounting.values[self._key], 6)


class IngeteamFlowSensor(IngeteamEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.ENUM

    def __init__(self, owner, key, options):
        super().__init__(owner.telemetry, Register(0))
        self._key = key
        self._attr_options = options
        self._attr_unique_id = f"{self._serial}_{key}"
        self._attr_translation_key = key

    @property
    def available(self):
        return self.coordinator.connected and self.native_value is not None

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        if self._key == "grid_flow":
            return flow_state(data.get("external_grid_power"), "importing", "exporting")
        if data.get("battery_status") == 7:
            return "not_available"
        return flow_state(data.get("battery_power"), "discharging", "charging")


class IngeteamAlarmSensor(IngeteamEntity, SensorEntity):
    _attr_translation_key = "active_alarms"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:alert-circle-outline"

    def __init__(self, owner):
        super().__init__(owner, Register(0))
        self._attr_unique_id = f"{self._serial}_active_alarms"

    @property
    def available(self):
        return self.coordinator.last_update_success and (
            bool(self.coordinator.alarms) or self.coordinator.alarm_coverage_complete
        )

    @property
    def native_value(self):
        return len(self.coordinator.alarms)

    @property
    def extra_state_attributes(self):
        return {
            "alarms": self.coordinator.alarms,
            "raw_codes": self.coordinator.raw_alarms,
            "coverage": "device_map",
            "coverage_complete": self.coordinator.alarm_coverage_complete,
            "missing_categories": self.coordinator.missing_alarm_categories,
            "stale_categories": self.coordinator.stale_alarm_categories,
        }


class IngeteamSSEDiagnostics(IngeteamEntity, SensorEntity):
    _attr_translation_key = "sse_diagnostics"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False
    _attr_icon = "mdi:connection"

    def __init__(self, owner):
        super().__init__(owner.telemetry, Register(0))
        self._attr_unique_id = f"{self._serial}_sse_diagnostics"

    @property
    def available(self):
        return True

    @property
    def native_value(self):
        return "connected" if self.coordinator.connected else "disconnected"

    @property
    def extra_state_attributes(self):
        return telemetry_diagnostics(self.coordinator)


class IngeteamMapStateSensor(IngeteamEntity, SensorEntity):
    """Enumerated register shown with the label declared by the device map."""

    _attr_icon = "mdi:information-outline"

    def __init__(self, owner, key, address, diagnostic):
        super().__init__(owner, Register(address))
        self._attr_unique_id = f"{self._serial}_{key}"
        self._attr_translation_key = key
        if diagnostic:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def available(self):
        return self.coordinator.last_update_success and self._code() is not None

    def _code(self):
        return raw_integer(self._register_value("online"))

    @property
    def native_value(self):
        code = self._code()
        if code is None:
            return None
        label = label_for(
            self.coordinator.api.capabilities,
            self.register.address,
            code,
            self.coordinator.hass.config.language,
        )
        return label or str(code)

    @property
    def extra_state_attributes(self):
        return {"code": self._code()}
