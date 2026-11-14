"""Selected writable switches for Ingeteam ISS."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import IngeteamCoordinator
from .entity import IngeteamEntity
from .profiles.descriptions import IngeteamSwitchDescription
from .values import register_integer


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[IngeteamCoordinator],
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up writable switches."""
    async_add_entities(
        IngeteamSwitch(entry.runtime_data, desc)
        for desc in entry.runtime_data.profile.switches
        if entry.runtime_data.api.supports(
            "holding", desc.register.address, desc.register.startbit
        )
    )


class IngeteamSwitch(IngeteamEntity, SwitchEntity):
    """One writable boolean setting."""

    entity_description: IngeteamSwitchDescription

    def __init__(
        self, coordinator: IngeteamCoordinator, description: IngeteamSwitchDescription
    ) -> None:
        super().__init__(coordinator, description.register, description.group)
        self.entity_description = description
        self._attr_unique_id = f"{self._serial}_{description.key}"

    @property
    def available(self) -> bool:
        return super().available and self.is_on is not None

    @property
    def is_on(self) -> bool | None:
        """Return the confirmed bit value."""
        value = register_integer(self._register_value(), 0, 1)
        return bool(value) if value is not None else None

    async def async_turn_on(self, **kwargs) -> None:
        """Enable the function."""
        await self.coordinator.async_write(
            self.register.address, self.register.startbit, 1
        )

    async def async_turn_off(self, **kwargs) -> None:
        """Disable the function."""
        await self.coordinator.async_write(
            self.register.address, self.register.startbit, 0
        )
