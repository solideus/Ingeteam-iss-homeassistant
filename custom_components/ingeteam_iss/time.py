"""Writable schedule times for Ingeteam ISS."""

from __future__ import annotations

from datetime import time

from homeassistant.components.time import TimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import IngeteamCoordinator
from .entity import IngeteamEntity
from .profiles.descriptions import IngeteamTimeDescription
from .values import register_integer


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[IngeteamCoordinator],
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up writable schedule times."""
    async_add_entities(
        IngeteamTime(entry.runtime_data, desc)
        for desc in entry.runtime_data.profile.times
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
        minute = register_integer(self._register_value(), 0, 59)
        hour = register_integer(
            (self.coordinator.data or {})
            .get("holding", {})
            .get((self.register.address, 8)),
            0,
            23,
        )
        if minute is None or hour is None:
            return None
        return time(hour=hour, minute=minute)

    async def async_set_value(self, value: time) -> None:
        """Write minute and hour together, then read the confirmed value."""
        await self.coordinator.async_write_many(
            [
                (self.register.address, 0, value.minute),
                (self.register.address, 8, value.hour),
            ]
        )
