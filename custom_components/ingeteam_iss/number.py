"""Selected writable numeric settings for Ingeteam ISS."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    GROUP_BATTERY,
    GROUP_GRID_CHARGE,
    GROUP_GRID_EXPORT,
    GROUP_SCHEDULED_DISCHARGE,
    Register,
)
from .coordinator import IngeteamCoordinator
from .entity import IngeteamEntity
from .values import bounded_integer


@dataclass(frozen=True, kw_only=True)
class IngeteamNumberDescription(NumberEntityDescription):
    """Writable numeric register description."""

    register: Register
    group: str


NUMBERS: tuple[IngeteamNumberDescription, ...] = (
    IngeteamNumberDescription(
        key="bms_max_charge_current",
        translation_key="bms_max_charge_current",
        register=Register(86),
        group=GROUP_BATTERY,
        native_min_value=0,
        native_max_value=66,
        native_step=1,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=NumberDeviceClass.CURRENT,
        mode=NumberMode.SLIDER,
        entity_category=EntityCategory.CONFIG,
    ),
    IngeteamNumberDescription(
        key="bms_max_on_grid_discharge_current",
        translation_key="bms_max_on_grid_discharge_current",
        register=Register(142),
        group=GROUP_BATTERY,
        native_min_value=0,
        native_max_value=66,
        native_step=1,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=NumberDeviceClass.CURRENT,
        mode=NumberMode.SLIDER,
        entity_category=EntityCategory.CONFIG,
    ),
    IngeteamNumberDescription(
        key="max_grid_charge_power",
        translation_key="max_grid_charge_power",
        register=Register(128),
        group=GROUP_GRID_CHARGE,
        native_min_value=0,
        native_max_value=18000,
        native_step=100,
        native_unit_of_measurement=UnitOfPower.WATT,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
    ),
    IngeteamNumberDescription(
        key="max_surplus_grid_power",
        translation_key="max_surplus_grid_power",
        register=Register(129),
        group=GROUP_GRID_EXPORT,
        native_min_value=0,
        native_max_value=32000,
        native_step=100,
        native_unit_of_measurement=UnitOfPower.WATT,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
    ),
    IngeteamNumberDescription(
        key="max_battery_grid_injection_power",
        translation_key="max_battery_grid_injection_power",
        register=Register(58),
        group=GROUP_SCHEDULED_DISCHARGE,
        native_min_value=0,
        native_max_value=18000,
        native_step=100,
        native_unit_of_measurement=UnitOfPower.WATT,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
    ),
    IngeteamNumberDescription(
        key="soc_max",
        translation_key="soc_max",
        register=Register(123),
        group=GROUP_BATTERY,
        native_min_value=0,
        native_max_value=100,
        native_step=1,
        native_unit_of_measurement=PERCENTAGE,
        mode=NumberMode.SLIDER,
        entity_category=EntityCategory.CONFIG,
    ),
    IngeteamNumberDescription(
        key="soc_recovery",
        translation_key="soc_recovery",
        register=Register(130),
        group=GROUP_BATTERY,
        native_min_value=0,
        native_max_value=100,
        native_step=1,
        native_unit_of_measurement=PERCENTAGE,
        mode=NumberMode.SLIDER,
        entity_category=EntityCategory.CONFIG,
    ),
    IngeteamNumberDescription(
        key="soc_min",
        translation_key="soc_min",
        register=Register(125),
        group=GROUP_BATTERY,
        native_min_value=0,
        native_max_value=100,
        native_step=1,
        native_unit_of_measurement=PERCENTAGE,
        mode=NumberMode.SLIDER,
        entity_category=EntityCategory.CONFIG,
    ),
    IngeteamNumberDescription(
        key="soc_descx",
        translation_key="soc_descx",
        register=Register(126),
        group=GROUP_BATTERY,
        native_min_value=0,
        native_max_value=100,
        native_step=1,
        native_unit_of_measurement=PERCENTAGE,
        mode=NumberMode.SLIDER,
        entity_category=EntityCategory.CONFIG,
    ),
    IngeteamNumberDescription(
        key="soc_recx",
        translation_key="soc_recx",
        register=Register(127),
        group=GROUP_BATTERY,
        native_min_value=0,
        native_max_value=100,
        native_step=1,
        native_unit_of_measurement=PERCENTAGE,
        mode=NumberMode.SLIDER,
        entity_category=EntityCategory.CONFIG,
    ),
    IngeteamNumberDescription(
        key="soc_grid_1",
        translation_key="soc_grid_1",
        register=Register(119),
        group=GROUP_GRID_CHARGE,
        native_min_value=0,
        native_max_value=100,
        native_step=1,
        native_unit_of_measurement=PERCENTAGE,
        mode=NumberMode.SLIDER,
        entity_category=EntityCategory.CONFIG,
    ),
    IngeteamNumberDescription(
        key="soc_grid_2",
        translation_key="soc_grid_2",
        register=Register(63),
        group=GROUP_GRID_CHARGE,
        native_min_value=0,
        native_max_value=100,
        native_step=1,
        native_unit_of_measurement=PERCENTAGE,
        mode=NumberMode.SLIDER,
        entity_category=EntityCategory.CONFIG,
    ),
    IngeteamNumberDescription(
        key="soc_discharge_1",
        translation_key="soc_discharge_1",
        register=Register(59),
        group=GROUP_SCHEDULED_DISCHARGE,
        native_min_value=0,
        native_max_value=100,
        native_step=1,
        native_unit_of_measurement=PERCENTAGE,
        mode=NumberMode.SLIDER,
        entity_category=EntityCategory.CONFIG,
    ),
    IngeteamNumberDescription(
        key="soc_discharge_2",
        translation_key="soc_discharge_2",
        register=Register(60),
        group=GROUP_SCHEDULED_DISCHARGE,
        native_min_value=0,
        native_max_value=100,
        native_step=1,
        native_unit_of_measurement=PERCENTAGE,
        mode=NumberMode.SLIDER,
        entity_category=EntityCategory.CONFIG,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[IngeteamCoordinator],
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up writable number entities."""
    async_add_entities(
        IngeteamNumber(entry.runtime_data, desc)
        for desc in NUMBERS
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
    def native_value(self) -> float | None:
        """Return the confirmed register value."""
        value = self._register_value()
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
