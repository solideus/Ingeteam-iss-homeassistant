"""Original netting implementation: hourly boundaries, DST, persistence and gaps."""

from datetime import datetime, timezone

import pytest

from custom_components.ingeteam_iss.accounting import CalendarEnergy
from custom_components.ingeteam_iss.alarms import decode_alarms, flow_state


def timestamp(text):
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc).timestamp()


def sample(imp=0, exp=0, load=3600):
    return {
        "grid_import_power": imp,
        "grid_export_power": exp,
        "total_load_power": load,
    }


def test_netting_closes_hour_once_and_never_resets_lifetime():
    acc = CalendarEnergy("Europe/Madrid")
    start = timestamp("2026-09-24T10:00:00")
    for second in range(3601):
        acc.update(
            sample(3600 if second < 1800 else 0, 0 if second < 1800 else 1800),
            second,
            start + second,
        )
    assert acc.values["net_import_energy"] == pytest.approx(0.9)
    assert acc.values["net_export_energy"] == 0
    assert acc.values["load_energy_daily"] == pytest.approx(3.6)
    assert acc.values["hourly_net_balance"] == 0
    acc.tick(start + 3610)
    assert acc.values["net_import_energy"] == pytest.approx(0.9)
    acc.tick(start + 86400)
    assert acc.values["load_energy_daily"] == 0
    assert acc.values["load_energy_monthly"] == pytest.approx(3.6)
    assert acc.values["net_import_energy"] == pytest.approx(0.9)


def test_midnight_month_split_and_restart():
    start = timestamp("2026-09-30T21:59:58")  # 23:59:58 Europe/Madrid
    acc = CalendarEnergy("Europe/Madrid")
    acc.update(sample(3600), 0, start)
    acc.update(sample(3600), 4, start + 4)
    assert acc.values["load_energy_daily"] == pytest.approx(0.002)
    assert acc.values["load_energy_monthly"] == pytest.approx(0.002)
    assert acc.values["net_import_energy"] == pytest.approx(0.002)
    restored = CalendarEnergy("Europe/Madrid")
    restored.restore(acc.dump())
    restored.update(sample(3600), 0, start + 100)
    assert restored.imported == pytest.approx(0.002)
    restored.update(sample(3600), 1, start + 101)
    assert restored.imported == pytest.approx(0.003)
    restored.tick(start + 3610)
    assert restored.values["net_import_energy"] == pytest.approx(0.005)
    again = CalendarEnergy("Europe/Madrid")
    again.restore(restored.dump())
    again.tick(start + 3620)
    assert again.values["net_import_energy"] == pytest.approx(0.005)


@pytest.mark.parametrize("start", ["2026-03-29T00:59:58", "2026-10-25T00:59:58"])
def test_dst_hour_identifiers_are_unambiguous(start):
    acc = CalendarEnergy("Europe/Madrid")
    stamp = timestamp(start)
    acc.update(sample(0, 3600), 0, stamp)
    acc.update(sample(0, 3600), 4, stamp + 4)
    assert acc.values["net_export_energy"] == pytest.approx(0.002)
    assert acc.exported == pytest.approx(0.002)
    assert acc.values["load_energy_daily"] == pytest.approx(0.004)


def test_no_energy_across_gap_invalid_data_or_clock_jump():
    acc = CalendarEnergy("UTC")
    for mono, wall in [(0, 10000), (1, 10001), (30, 10030), (31, 12000), (32, 11900)]:
        acc.update(sample(3600), mono, wall)
    assert acc.values["load_energy_daily"] == pytest.approx(0.001)
    acc.break_interval()
    acc.update(sample(3600), 100, 13000)
    acc.update(sample(None), 101, 13001)
    assert acc.imported == 0


def test_idle_settlement_safety_margin_and_unknown_alarms():
    acc = CalendarEnergy("UTC")
    acc.update(sample(3600), 0, 3597)
    acc.update(sample(3600), 1, 3598)
    acc.tick(3604)
    assert acc.values["net_import_energy"] == 0
    acc.tick(3605)
    assert acc.values["net_import_energy"] == pytest.approx(0.001)
    alarms, raw = decode_alarms({(73, 0): 5, (10, 0): 0}, {}, "es")
    assert len(alarms) == 2
    assert all(not a["documented"] for a in alarms)
    assert raw["bms_warning"] == "0x0005"
    assert flow_state(5, "importing", "exporting") == "idle"
    assert flow_state(None, "importing", "exporting") is None


def test_documented_alarms_follow_connected_map_not_assumed_firmware():
    mapping = {
        "online": [{"add": 10, "ty": "alarm"}],
        "customtypes": {"alarm": {"values": {"00": "a", "01": "b"}}},
        "langs": {"SPANISH": {"a": "Fallo de prueba", "b": "Bit 1"}},
    }
    alarms, _ = decode_alarms({(10, 0): 7}, mapping, "es")
    assert [a["documented"] for a in alarms] == [True, False, False]
    assert alarms[0]["description"] == "Fallo de prueba"
