"""Bounded SSE framing and curated telemetry, independent of Home Assistant."""

from __future__ import annotations

import codecs
from collections.abc import AsyncIterator
from dataclasses import dataclass
from math import isfinite
from typing import Any

MAX_EVENT_SIZE = 262_144


@dataclass(frozen=True)
class SSEEvent:
    """One complete SSE event, never a network chunk."""

    event: str
    data: str


async def iter_sse(chunks: AsyncIterator[bytes]) -> AsyncIterator[SSEEvent]:
    """Handle split UTF-8, LF/CR/CRLF, comments and multiline data.

    Incomplete events at EOF are discarded. A malformed/oversized stream raises
    ValueError and is reconnected by the caller. No payload is logged.
    """
    decoder = codecs.getincrementaldecoder("utf-8-sig")()
    line = ""
    skip_lf = False
    event_type = "message"
    data: list[str] = []
    size = 0
    async for chunk in chunks:
        for char in decoder.decode(chunk):
            if skip_lf:
                skip_lf = False
                if char == "\n":
                    continue
            if char not in "\r\n":
                line += char
                if len(line) + size > MAX_EVENT_SIZE:
                    raise ValueError("SSE event too large")
                continue
            skip_lf = char == "\r"
            if not line:
                if data:
                    yield SSEEvent(event_type, "\n".join(data))
                event_type, data, size = "message", [], 0
            elif not line.startswith(":"):
                field, _, value = line.partition(":")
                if value.startswith(" "):
                    value = value[1:]
                if field == "event":
                    event_type = value
                elif field == "data":
                    data.append(value)
                    size += len(value) + 1
                    if size > MAX_EVENT_SIZE:
                        raise ValueError("SSE event too large")
            line = ""
    decoder.decode(b"", final=True)


def finite_number(value: Any, *, minimum: float | None = None) -> float | None:
    """Reject absent, boolean, non-numeric, non-finite and invalid-sign values."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except ValueError, OverflowError:
        return None
    if not isfinite(number) or (minimum is not None and number < minimum):
        return None
    return number


def decode_telemetry(event: SSEEvent) -> dict[str, float | None] | None:
    """Compatibility helper; runtime decoding comes from the selected profile."""
    from .profiles.tl_m.telemetry import decode_telemetry as decode

    return decode(event)
