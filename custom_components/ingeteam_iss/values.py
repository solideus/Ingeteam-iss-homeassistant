"""Value handling independent of Home Assistant and network access."""

from collections.abc import Mapping
from math import isfinite
from typing import Any


def bounded_integer(value: Any, minimum: float, maximum: float) -> int:
    """Validate integral register values without silently truncating them."""
    if isinstance(value, bool):
        raise ValueError("Expected an integer")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as err:
        raise ValueError("Expected an integer") from err
    if (
        not isfinite(number)
        or not number.is_integer()
        or not minimum <= number <= maximum
    ):
        raise ValueError(f"Expected an integer between {minimum:g} and {maximum:g}")
    return int(number)


def register_integer(value: Any, minimum: int, maximum: int) -> int | None:
    """Read an integral register without converting invalid values to settings."""
    if not isinstance(value, (int, float)):
        return None
    try:
        return bounded_integer(value, minimum, maximum)
    except ValueError:
        return None


def scaled_sum(
    values: Mapping[tuple[int, int], Any],
    keys: tuple[tuple[int, int], ...],
    divisor: float = 1,
) -> int | float | None:
    """Sum complete finite readings; a missing string is not zero watts."""
    total = 0.0
    for key in keys:
        value = values.get(key)
        if value is None or isinstance(value, bool):
            return None
        try:
            number = float(value)
        except TypeError, ValueError, OverflowError:
            return None
        if not isfinite(number):
            return None
        total += number / divisor
        if not isfinite(total):
            return None
    return int(total) if total.is_integer() else total
