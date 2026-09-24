"""Selected writable switches for Ingeteam ISS."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import GROUP_BATTERY, GROUP_GRID_EXPORT, Register
from .coordinator import IngeteamCoordinator
from .entity import IngeteamEntity


@dataclass(frozen=True, kw_only=True)
class IngeteamSwitchDescription(SwitchEntityDescription):
    """Writable bit-register description."""

    register: Register
    group: str


SWITCHES: tuple[IngeteamSwitchDescription, ...] = (
    IngeteamSwitchDescription(
        key="bms_soc_calibration",
        translation_key="bms_soc_calibration",
        register=Register(132, 0),
        group=GROUP_BATTERY,
        icon="mdi:battery-sync",
        entity_category=EntityCategory.CONFIG,
    ),
    IngeteamSwitchDescription(
        key="prioritize_grid_export",
        translation_key="prioritize_grid_export",
        register=Register(132, 12),
        group=GROUP_GRID_EXPORT,
        entity_category=EntityCategory.CONFIG,
    ),
    IngeteamSwitchDescription(
        key="peak_shaving",
        translation_key="peak_shaving",
        register=Register(132, 14),
        group=GROUP_GRID_EXPORT,
        entity_category=EntityCategory.CONFIG,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[IngeteamCoordinator],
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up writable switches."""
    async_add_entities(
        IngeteamSwitch(entry.runtime_data, desc)
        for desc in SWITCHES
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
    def is_on(self) -> bool | None:
        """Return the confirmed bit value."""
        value = self._register_value()
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
