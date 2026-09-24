"""SSE connectivity reflects valid telemetry, not just a connected socket."""

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .alarms import raw_integer
from .const import Register
from .coordinator import IngeteamCoordinator
from .entity import IngeteamEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[IngeteamCoordinator],
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(
        [
            IngeteamSSEConnectivity(entry.runtime_data),
            *(
                IngeteamOperatingState(entry.runtime_data, key)
                for key in (
                    "pv_active",
                    "grid_connected",
                    "alarm_active",
                    "power_reduction",
                )
            ),
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
    def __init__(self, owner, key):
        super().__init__(
            owner.telemetry if key in ("pv_active", "grid_connected") else owner,
            Register(0),
        )
        self._key = key
        self._attr_unique_id = f"{self._serial}_{key}"
        self._attr_translation_key = key
        if key == "alarm_active":
            self._attr_device_class = BinarySensorDeviceClass.PROBLEM
        if key == "power_reduction":
            self._attr_entity_registry_enabled_default = False

    @property
    def available(self):
        fresh = getattr(
            self.coordinator, "connected", self.coordinator.last_update_success
        )
        return fresh and self.is_on is not None

    @property
    def is_on(self):
        data = self.coordinator.data or {}
        if self._key == "pv_active":
            power = data.get("pv_total_power")
            return power > 10 if power is not None else None
        if self._key == "grid_connected":
            status = data.get("inverter_status")
            return True if status in (3, 4, 8) else False if status in (2, 11) else None
        if self._key == "alarm_active":
            if not self.coordinator.raw_alarms:
                return None
            return bool(self.coordinator.alarms)
        reason = raw_integer(data.get("online", {}).get((41, 0)))
        return reason != 0 if reason is not None else None
