"""Battery-use selectors for the two discharge schedules."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    GROUP_BATTERY,
    GROUP_GRID_CHARGE,
    GROUP_SCHEDULED_DISCHARGE,
    Register,
)
from .coordinator import IngeteamCoordinator
from .entity import IngeteamEntity
from .models import MODEL_STORAGE_1PLAY
from .values import register_integer

BATTERY_USE_OPTIONS = ("self_consumption", "grid_injection")
SCHEDULE_MODE_OPTIONS = ("off", "whole_week", "weekdays", "weekend")


@dataclass(frozen=True, kw_only=True)
class IngeteamSelectDescription(SelectEntityDescription):
    """Writable enum register description."""

    register: Register
    group: str


SELECTS: tuple[IngeteamSelectDescription, ...] = (
    IngeteamSelectDescription(
        key="schedule_1_battery_use",
        translation_key="schedule_1_battery_use",
        register=Register(133, 11),
        group=GROUP_SCHEDULED_DISCHARGE,
        options=BATTERY_USE_OPTIONS,
        entity_category=EntityCategory.CONFIG,
    ),
    IngeteamSelectDescription(
        key="schedule_2_battery_use",
        translation_key="schedule_2_battery_use",
        register=Register(133, 12),
        group=GROUP_SCHEDULED_DISCHARGE,
        options=BATTERY_USE_OPTIONS,
        entity_category=EntityCategory.CONFIG,
    ),
    IngeteamSelectDescription(
        key="grid_charge_schedule_1_mode",
        translation_key="grid_charge_schedule_1_mode",
        register=Register(100, 5),
        group=GROUP_GRID_CHARGE,
        options=SCHEDULE_MODE_OPTIONS,
        entity_category=EntityCategory.CONFIG,
    ),
    IngeteamSelectDescription(
        key="grid_charge_schedule_2_mode",
        translation_key="grid_charge_schedule_2_mode",
        register=Register(133, 1),
        group=GROUP_GRID_CHARGE,
        options=SCHEDULE_MODE_OPTIONS,
        entity_category=EntityCategory.CONFIG,
    ),
    IngeteamSelectDescription(
        key="battery_discharge_schedule_1_mode",
        translation_key="battery_discharge_schedule_1_mode",
        register=Register(100, 10),
        group=GROUP_SCHEDULED_DISCHARGE,
        options=SCHEDULE_MODE_OPTIONS,
        entity_category=EntityCategory.CONFIG,
    ),
    IngeteamSelectDescription(
        key="battery_discharge_schedule_2_mode",
        translation_key="battery_discharge_schedule_2_mode",
        register=Register(100, 12),
        group=GROUP_SCHEDULED_DISCHARGE,
        options=SCHEDULE_MODE_OPTIONS,
        entity_category=EntityCategory.CONFIG,
    ),
)

# STORAGE 1Play holding 132 bit 4: "Battery Charging Priority".
STORAGE_1PLAY_SELECTS: tuple[IngeteamSelectDescription, ...] = (
    IngeteamSelectDescription(
        key="battery_charge_priority",
        translation_key="battery_charge_priority",
        register=Register(132, 4),
        group=GROUP_BATTERY,
        options=("pv_then_grid", "grid_only"),
        entity_category=EntityCategory.CONFIG,
        # Experimental: disabled by default until the review checks are done.
        entity_registry_enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[IngeteamCoordinator],
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up battery-use selectors."""
    profile = entry.runtime_data.profile
    if entry.runtime_data.profile_conflict is not None:
        return
    descriptions = (
        STORAGE_1PLAY_SELECTS if profile.key == MODEL_STORAGE_1PLAY else SELECTS
    )
    async_add_entities(
        IngeteamSelect(entry.runtime_data, desc)
        for desc in descriptions
        if (profile.control_keys is None or desc.key in profile.control_keys)
        and entry.runtime_data.api.supports(
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

    def _write_fields(self):
        last = len(self.entity_description.options) - 1
        return ((self.register.address, self.register.startbit, 0, last),)

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
