"""Battery-use selectors for the two discharge schedules."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import IngeteamCoordinator
from .entity import IngeteamEntity
from .profiles.descriptions import IngeteamSelectDescription
from .values import register_integer


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[IngeteamCoordinator],
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up battery-use selectors."""
    async_add_entities(
        IngeteamSelect(entry.runtime_data, desc)
        for desc in entry.runtime_data.profile.selects
        if entry.runtime_data.api.supports(
            "holding", desc.register.address, desc.register.startbit
        )
    )


class IngeteamSelect(IngeteamEntity, SelectEntity):
    """One writable battery-use mode."""

    entity_description: IngeteamSelectDescription

    def __init__(
        self, coordinator: IngeteamCoordinator, description: IngeteamSelectDescription
    ) -> None:
        super().__init__(coordinator, description.register, description.group)
        self.entity_description = description
        self._attr_unique_id = f"{self._serial}_{description.key}"

    @property
    def available(self) -> bool:
        return super().available and self.current_option is not None

    @property
    def current_option(self) -> str | None:
        """Return the confirmed selection."""
        value = register_integer(
            self._register_value(), 0, len(self.entity_description.options) - 1
        )
        if value is None:
            return None
        return self.entity_description.options[value]

    async def async_select_option(self, option: str) -> None:
        """Write the selected battery-use mode."""
        if option not in self.entity_description.options:
            raise ValueError(f"Unsupported option: {option}")
        await self.coordinator.async_write(
            self.register.address,
            self.register.startbit,
            self.entity_description.options.index(option),
        )
