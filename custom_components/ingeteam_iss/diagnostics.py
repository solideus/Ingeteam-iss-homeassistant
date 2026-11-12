"""Allow-listed diagnostics: never export credentials or raw device identity."""

from homeassistant.util import dt as dt_util

from .const import REFERENCE_FIRMWARE
from .models import detect_model, map_firmware


def telemetry_diagnostics(telemetry) -> dict:
    return {
        "connected": telemetry.connected,
        "last_received": telemetry.last_received.isoformat()
        if telemetry.last_received
        else None,
        "last_valid_event": telemetry.last_event.isoformat()
        if telemetry.last_event
        else None,
        "seconds_without_data": (
            dt_util.utcnow() - telemetry.last_event
        ).total_seconds()
        if telemetry.last_event
        else None,
        "mean_interval_seconds": telemetry.mean_interval,
        "reconnections": max(0, telemetry.connections - 1),
        "valid_frames": telemetry.valid_frames,
        "discarded_frames": telemetry.discarded_frames,
        "incomplete_frames": telemetry.incomplete_frames,
        "last_disconnect_reason": telemetry.disconnect_reason,
        "missing_fields": telemetry.missing_fields,
        "timeout_seconds": telemetry.timeout,
        "publication_interval_seconds": telemetry.publish_interval,
    }


async def async_get_config_entry_diagnostics(hass, entry) -> dict:
    owner = entry.runtime_data
    return {
        "reference_firmware": REFERENCE_FIRMWARE,
        "model": owner.profile.key,
        "map_firmware": map_firmware(owner.api.capabilities),
        "detected_model": detect_model(owner.api.capabilities),
        "reported_portal_version": owner.device_info.get("Version"),
        "reported_hardware": owner.device_info.get("HwType"),
        "capability_map_available": bool(owner.api.capabilities),
        "holding_fields_available": len((owner.data or {}).get("holding", {})),
        "telemetry": telemetry_diagnostics(owner.telemetry),
        "energy": owner.telemetry.energy.totals.copy(),
        "calendar_energy": owner.telemetry.accounting.dump(),
        "alarms": owner.alarms,
        "raw_alarms": owner.raw_alarms,
    }
