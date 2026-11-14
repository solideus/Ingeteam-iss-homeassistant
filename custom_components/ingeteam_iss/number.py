"""Selected writable numeric settings for Ingeteam ISS."""

from __future__ import annotations

from homeassistant.components.number import (
    NumberEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import IngeteamCoordinator
from .entity import IngeteamEntity
from .profiles.descriptions import IngeteamNumberDescription
from .values import bounded_integer, register_integer


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[IngeteamCoordinator],
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up writable number entities."""
    async_add_entities(
        IngeteamNumber(entry.runtime_data, desc)
        for desc in entry.runtime_data.profile.numbers
        if entry.runtime_data.api.supports(
            "holding", desc.register.address, desc.register.startbit
        )
    )


class IngeteamNumber(IngeteamEntity, NumberEntity):
    """One writable numeric setting."""

    entity_description: IngeteamNumberDescription

    def __init__(
        self, coordinator: IngeteamCoordinator, description: IngeteamNumberDescription
    ) -> None:
        super().__init__(coordinator, description.register, description.group)
        self.entity_description = description
        self._attr_unique_id = f"{self._serial}_{description.key}"

    @property
    def available(self) -> bool:
        return super().available and self.native_value is not None

    @property
    def native_value(self) -> float | None:
        """Return the confirmed register value."""
        value = register_integer(
            self._register_value(),
            self.entity_description.native_min_value,
            self.entity_description.native_max_value,
        )
        return float(value) if value is not None else None

    async def async_set_native_value(self, value: float) -> None:
        """Write and immediately read back the setting."""
        try:
            value = bounded_integer(
                value,
                self.entity_description.native_min_value,
                self.entity_description.native_max_value,
            )
        except ValueError as err:
            raise ServiceValidationError(str(err)) from err
        await self.coordinator.async_write(
            self.register.address, self.register.startbit, value
        )
