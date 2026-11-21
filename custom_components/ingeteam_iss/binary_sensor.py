"""SSE connectivity reflects valid telemetry, not just a connected socket."""

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import Register
from .coordinator import IngeteamCoordinator
from .entity import IngeteamEntity
from .profiles.descriptions import OperatingStateDescription


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[IngeteamCoordinator],
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(
        [
            IngeteamSSEConnectivity(entry.runtime_data),
            *(
                IngeteamOperatingState(entry.runtime_data, description)
                for description in entry.runtime_data.profile.operating_states
            ),
            IngeteamAlarmState(entry.runtime_data),
        ]
    )


class IngeteamSSEConnectivity(IngeteamEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "sse_connected"

    def __init__(self, owner: IngeteamCoordinator) -> None:
        super().__init__(owner.telemetry, Register(0))
        self._attr_unique_id = f"{self._serial}_sse_connected"

    @property
    def available(self) -> bool:
        return True

    @property
    def is_on(self) -> bool:
        return self.coordinator.connected


class IngeteamOperatingState(IngeteamEntity, BinarySensorEntity):
    """Publish a binary state declared and interpreted by the active profile."""

    def __init__(self, owner, description: OperatingStateDescription):
        super().__init__(
            owner.telemetry if description.source == "telemetry" else owner,
            Register(0),
        )
        self._description = description
        self._attr_unique_id = f"{self._serial}_{description.key}"
        self._attr_translation_key = description.key
        self._attr_device_class = description.device_class
        self._attr_entity_registry_enabled_default = description.enabled_default

    @property
    def available(self):
        fresh = getattr(
            self.coordinator, "connected", self.coordinator.last_update_success
        )
        return fresh and self.is_on is not None

    @property
    def is_on(self):
        return self._description.evaluator(self.coordinator.data or {})


class IngeteamAlarmState(IngeteamEntity, BinarySensorEntity):
    """Alarm coverage is shared infrastructure, independent of register layout."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_translation_key = "alarm_active"

    def __init__(self, owner):
        super().__init__(owner, Register(0))
        self._attr_unique_id = f"{self._serial}_alarm_active"

    @property
    def available(self):
        return self.coordinator.last_update_success and self.is_on is not None

    @property
    def is_on(self):
        if self.coordinator.alarms:
            return True
        return False if self.coordinator.alarm_coverage_complete else None

    @property
    def extra_state_attributes(self):
        return {
            "coverage_complete": self.coordinator.alarm_coverage_complete,
            "missing_categories": self.coordinator.missing_alarm_categories,
            "stale_categories": self.coordinator.stale_alarm_categories,
        }
