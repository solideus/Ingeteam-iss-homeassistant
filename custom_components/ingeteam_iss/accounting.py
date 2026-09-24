"""Calendar energy and hourly netting; independent of entity publication cadence.

Original implementation from the documented behaviour, not reference code.
Only observed, valid intervals are integrated. Restart restores buckets, never
power/time anchors. Hour identifiers are UTC timestamps (DST-safe).
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .const import ENERGY_MAX_GAP
from .sse import finite_number

ACCOUNTING_KEYS = (
    "load_energy_daily",
    "load_energy_monthly",
    "net_import_energy",
    "net_export_energy",
    "hourly_net_balance",
    "net_import_energy_daily",
    "net_export_energy_daily",
    "net_import_energy_monthly",
    "net_export_energy_monthly",
)


class CalendarEnergy:
    """Persistent calendar buckets with a five-second settlement safety margin."""

    def __init__(self, time_zone: str) -> None:
        self.zone = ZoneInfo(time_zone)
        self.values = dict.fromkeys(ACCOUNTING_KEYS, 0.0)
        self.day = ""
        self.month = ""
        self.hour: int | None = None
        self.imported = 0.0
        self.exported = 0.0
        self._previous = None

    def dump(self) -> dict:
        return {
            "values": dict(self.values),
            "day": self.day,
            "month": self.month,
            "hour": self.hour,
            "imported": self.imported,
            "exported": self.exported,
        }

    def restore(self, saved: dict) -> None:
        for key in self.values:
            if key != "hourly_net_balance":
                value = finite_number(saved.get("values", {}).get(key), minimum=0)
                if value is not None:
                    self.values[key] = value
        self.day = str(saved.get("day", ""))
        self.month = str(saved.get("month", ""))
        hour = saved.get("hour")
        self.hour = hour if type(hour) is int and hour >= 0 else None
        self.imported = finite_number(saved.get("imported"), minimum=0) or 0.0
        self.exported = finite_number(saved.get("exported"), minimum=0) or 0.0
        self.values["hourly_net_balance"] = self.exported - self.imported
        self.break_interval()

    def break_interval(self) -> None:
        self._previous = None

    def _period(self, timestamp: float) -> None:
        local = datetime.fromtimestamp(timestamp, timezone.utc).astimezone(self.zone)
        day, month = local.date().isoformat(), local.strftime("%Y-%m")
        if day != self.day:
            for key in self.values:
                if key.endswith("_daily"):
                    self.values[key] = 0.0
            self.day = day
        if month != self.month:
            for key in self.values:
                if key.endswith("_monthly"):
                    self.values[key] = 0.0
            self.month = month

    def _settle(self) -> None:
        if self.hour is None:
            return
        # Attribute the closed hour to its own local day/month, not the next.
        self._period(self.hour + 3599)
        balance = self.imported - self.exported
        for direction, amount in (
            ("import", max(balance, 0)),
            ("export", max(-balance, 0)),
        ):
            for suffix in ("", "_daily", "_monthly"):
                self.values[f"net_{direction}_energy{suffix}"] += amount
        self.imported = self.exported = 0.0
        self.values["hourly_net_balance"] = 0.0

    def _hour(self, timestamp: float) -> bool:
        hour = int(timestamp // 3600) * 3600
        if self.hour is not None and hour < self.hour:
            return False  # Never reopen an already accounted hour after clock rollback.
        if self.hour != hour:
            self._settle()
            self.hour = hour
        self._period(timestamp)
        return True

    def tick(self, timestamp: float) -> None:
        """Close idle hours once safely past the boundary; never invent energy."""
        if self.hour is not None and timestamp >= self.hour + 3605:
            self._hour(timestamp)
        self._period(timestamp)

    def update(self, sample: dict, monotonic: float, timestamp: float) -> None:
        previous, self._previous = self._previous, (sample.copy(), monotonic, timestamp)
        if previous is not None:
            old, then, wall = previous
            elapsed = monotonic - then
            if (
                0 < elapsed <= ENERGY_MAX_GAP
                and timestamp > wall
                and abs(timestamp - wall - elapsed) < 1
            ):
                cursor = wall
                while cursor < timestamp:
                    end = min(timestamp, (int(cursor // 3600) + 1) * 3600)
                    if self._hour(cursor):
                        seconds = (end - cursor) * elapsed / (timestamp - wall)
                        for source, target in (
                            ("total_load_power", "load"),
                            ("grid_import_power", "import"),
                            ("grid_export_power", "export"),
                        ):
                            power = finite_number(old.get(source), minimum=0)
                            current = finite_number(sample.get(source), minimum=0)
                            if power is None or current is None:
                                continue
                            increment = power * seconds / 3_600_000
                            if target == "load":
                                self.values["load_energy_daily"] += increment
                                self.values["load_energy_monthly"] += increment
                            elif target == "import":
                                self.imported += increment
                            else:
                                self.exported += increment
                    cursor = end
        self._hour(timestamp)
        self.values["hourly_net_balance"] = self.exported - self.imported
