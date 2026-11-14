"""Curated SSE/HTTP telemetry and persistent integrated energy sensors."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    EntityCategory,
    UnitOfEnergy,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .accounting import ACCOUNTING_KEYS
from .const import ENERGY_PUBLISH_INTERVAL, GROUP_ENERGY, Register
from .coordinator import IngeteamCoordinator
from .diagnostics import telemetry_diagnostics
from .energy import ENERGY_SOURCES
from .entity import IngeteamEntity
from .profiles.descriptions import FlowStateDescription, IngeteamSensorDescription
from .values import scaled_sum


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[IngeteamCoordinator],
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Preserve all old unique IDs; add only energy-related/diagnostic entities."""
    owner = entry.runtime_data
    async_add_entities(
        [
            *(IngeteamSensor(owner, desc) for desc in owner.profile.sensors),
            *(IngeteamEnergySensor(owner, key) for key in ENERGY_SOURCES),
            *(IngeteamCalendarSensor(owner, key) for key in ACCOUNTING_KEYS),
            *(
                IngeteamFlowSensor(owner, description)
                for description in owner.profile.flow_states
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
            or not self.owner.profile.battery_available(self.owner.telemetry.data)
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

    def __init__(self, owner, description: FlowStateDescription):
        super().__init__(owner.telemetry, Register(0))
        self._description = description
        self._attr_options = list(description.options)
        self._attr_unique_id = f"{self._serial}_{description.key}"
        self._attr_translation_key = description.key

    @property
    def available(self):
        return self.coordinator.connected and self.native_value is not None

    @property
    def native_value(self):
        return self._description.evaluator(self.coordinator.data or {})


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
