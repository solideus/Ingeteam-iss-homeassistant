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
    UnitOfPower,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import ENERGY_PUBLISH_INTERVAL, GROUP_ENERGY, Register
from .coordinator import IngeteamCoordinator
from .energy import ENERGY_SOURCES
from .entity import IngeteamEntity
from .values import scaled_sum


@dataclass(frozen=True, kw_only=True)
class IngeteamSensorDescription(SensorEntityDescription):
    """SSE readings are decoded; remaining online registers require scaling."""

    register: Register = Register(0)
    divisor: float = 1.0
    sse: bool = True


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


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[IngeteamCoordinator],
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Preserve all old unique IDs; add only energy-related/diagnostic entities."""
    owner = entry.runtime_data
    async_add_entities(
        [
            *(IngeteamSensor(owner, desc) for desc in SENSORS),
            *(IngeteamEnergySensor(owner, key) for key in ENERGY_SOURCES),
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
        if self.entity_description.key == "battery_current":
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
        if self.entity_description.key == "battery_current" and (
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
