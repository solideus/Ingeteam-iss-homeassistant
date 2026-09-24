"""Writable schedule times for Ingeteam ISS."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time

from homeassistant.components.time import TimeEntity, TimeEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import GROUP_GRID_CHARGE, GROUP_SCHEDULED_DISCHARGE, Register
from .coordinator import IngeteamCoordinator
from .entity import IngeteamEntity


@dataclass(frozen=True, kw_only=True)
class IngeteamTimeDescription(TimeEntityDescription):
    """Writable hour/minute register description."""

    register: Register
    group: str


TIMES: tuple[IngeteamTimeDescription, ...] = (
    IngeteamTimeDescription(
        key="grid_charge_schedule_1_start",
        translation_key="grid_charge_schedule_1_start",
        register=Register(117),
        group=GROUP_GRID_CHARGE,
        icon="mdi:clock-start",
        entity_category=EntityCategory.CONFIG,
    ),
    IngeteamTimeDescription(
        key="grid_charge_schedule_1_end",
        translation_key="grid_charge_schedule_1_end",
        register=Register(118),
        group=GROUP_GRID_CHARGE,
        icon="mdi:clock-end",
        entity_category=EntityCategory.CONFIG,
    ),
    IngeteamTimeDescription(
        key="grid_charge_schedule_2_start",
        translation_key="grid_charge_schedule_2_start",
        register=Register(61),
        group=GROUP_GRID_CHARGE,
        icon="mdi:clock-start",
        entity_category=EntityCategory.CONFIG,
    ),
    IngeteamTimeDescription(
        key="grid_charge_schedule_2_end",
        translation_key="grid_charge_schedule_2_end",
        register=Register(62),
        group=GROUP_GRID_CHARGE,
        icon="mdi:clock-end",
        entity_category=EntityCategory.CONFIG,
    ),
    IngeteamTimeDescription(
        key="battery_discharge_schedule_1_start",
        translation_key="battery_discharge_schedule_1_start",
        register=Register(120),
        group=GROUP_SCHEDULED_DISCHARGE,
        icon="mdi:clock-start",
        entity_category=EntityCategory.CONFIG,
    ),
    IngeteamTimeDescription(
        key="battery_discharge_schedule_1_end",
        translation_key="battery_discharge_schedule_1_end",
        register=Register(121),
        group=GROUP_SCHEDULED_DISCHARGE,
        icon="mdi:clock-end",
        entity_category=EntityCategory.CONFIG,
    ),
    IngeteamTimeDescription(
        key="battery_discharge_schedule_2_start",
        translation_key="battery_discharge_schedule_2_start",
        register=Register(64),
        group=GROUP_SCHEDULED_DISCHARGE,
        icon="mdi:clock-start",
        entity_category=EntityCategory.CONFIG,
    ),
    IngeteamTimeDescription(
        key="battery_discharge_schedule_2_end",
        translation_key="battery_discharge_schedule_2_end",
        register=Register(65),
        group=GROUP_SCHEDULED_DISCHARGE,
        icon="mdi:clock-end",
        entity_category=EntityCategory.CONFIG,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[IngeteamCoordinator],
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up writable schedule times."""
    async_add_entities(
        IngeteamTime(entry.runtime_data, desc)
        for desc in TIMES
        if all(
            entry.runtime_data.api.supports("holding", desc.register.address, bit)
            for bit in (0, 8)
        )
    )


class IngeteamTime(IngeteamEntity, TimeEntity):
    """One schedule start or end time."""

    entity_description: IngeteamTimeDescription

    def __init__(
        self, coordinator: IngeteamCoordinator, description: IngeteamTimeDescription
    ) -> None:
        super().__init__(coordinator, description.register, description.group)
        self.entity_description = description
        self._attr_unique_id = f"{self._serial}_{description.key}"

    @property
    def available(self) -> bool:
        """A valid time needs both its hour and minute fields."""
        return super().available and self.native_value is not None

    @property
    def native_value(self) -> time | None:
        """Return the confirmed hour and minute."""
        minute = self._register_value()
        hour = (
            (self.coordinator.data or {})
            .get("holding", {})
            .get((self.register.address, 8))
        )
        if minute is None or hour is None:
            return None
        try:
            return time(hour=int(hour), minute=int(minute))
        except TypeError, ValueError:
            return None

    async def async_set_value(self, value: time) -> None:
        """Write minute and hour together, then read the confirmed value."""
        await self.coordinator.async_write_many(
            [
                (self.register.address, 0, value.minute),
                (self.register.address, 8, value.hour),
            ]
        )
