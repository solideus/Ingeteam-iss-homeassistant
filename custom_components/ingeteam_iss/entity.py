"""Shared entity base for Ingeteam ISS."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, GROUP_NAMES, Register
from .coordinator import IngeteamCoordinator
from .telemetry import IngeteamTelemetryCoordinator

type EntityCoordinator = IngeteamCoordinator | IngeteamTelemetryCoordinator


def inverter_device_info(coordinator: EntityCoordinator) -> DeviceInfo:
    """Stable parent identity, registered before platform setup starts."""
    info = coordinator.device_info
    serial = str(info.get("SerialNumber") or coordinator.api.host)
    return DeviceInfo(
        identifiers={(DOMAIN, serial)},
        manufacturer="Ingeteam",
        model=str(
            info.get("ProductName") or info.get("Model") or info.get("HwType") or "ISS"
        ),
        name=f"Ingeteam ISS {serial}",
        serial_number=str(info.get("SerialNumber") or "") or None,
        sw_version=str(info.get("Version") or "") or None,
        hw_version=str(info.get("HwType") or "") or None,
        configuration_url=coordinator.api.base_url,
    )


class IngeteamEntity(CoordinatorEntity[EntityCoordinator]):
    """Base entity tied to one inverter and one decoded register."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: EntityCoordinator,
        register: Register,
        group: str | None = None,
    ) -> None:
        super().__init__(coordinator)
        self.register = register
        info = coordinator.device_info
        self._serial = str(info.get("SerialNumber") or coordinator.api.host)
        parent_identifier = (DOMAIN, self._serial)
        if group is None:
            self._attr_device_info = inverter_device_info(coordinator)
        else:
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, f"{self._serial}_{group}")},
                manufacturer="Ingeteam",
                model="Grupo funcional ISS",
                name=f"Ingeteam ISS · {GROUP_NAMES[group]}",
                translation_key=group,
                configuration_url=coordinator.api.base_url,
                via_device=parent_identifier,
            )

    @property
    def available(self) -> bool:
        """Do not offer controls for missing or inconsistent holding fields."""
        return super().available and self._register_value() is not None

    def _register_value(self, source: str = "holding"):
        """Return one decoded value from coordinator data."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get(source, {}).get(
            (self.register.address, self.register.startbit)
        )
