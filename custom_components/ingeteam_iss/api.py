"""Local HTTP client for the private Ingeteam inverter API."""

from __future__ import annotations

import json
from base64 import b64encode
from collections.abc import AsyncIterator, Iterable
from typing import Any

from aiohttp import (
    ClientError,
    ClientResponseError,
    ClientSession,
    ClientTimeout,
)

from .const import (
    DEFAULT_DEVICE_ID,
    DEFAULT_PORT,
    HOLDING_RANGES,
    ONLINE_RANGES,
    SSE_PATH,
)
from .sse import SSEEvent, iter_sse
from .values import bounded_integer


class IngeteamApiError(Exception):
    """Base API error."""


class IngeteamAuthError(IngeteamApiError):
    """Authentication failed."""


class IngeteamConnectionError(IngeteamApiError):
    """Connection to the inverter failed."""


class IngeteamApi:
    """Access the local API used by the inverter web portal."""

    def __init__(
        self,
        session: ClientSession,
        host: str,
        username: str,
        password: str,
        *,
        port: int = DEFAULT_PORT,
        device_id: int = DEFAULT_DEVICE_ID,
    ) -> None:
        self._session = session
        self.host = host.strip().rstrip("/")
        self.username = username
        if ":" in username:
            raise ValueError("A Basic Authentication username cannot contain ':'")
        # Preserve the portal's existing Latin-1 Basic encoding without the
        # deprecated aiohttp BasicAuth/auth= API (removed in aiohttp 4).
        credentials = f"{username}:{password}".encode("latin-1")
        self._authorization = "Basic " + b64encode(credentials).decode("ascii")
        self.port = bounded_integer(port, 1, 65535)
        self.device_id = bounded_integer(device_id, 1, 247)
        self._timeout = ClientTimeout(total=10)
        self.capabilities: dict[str, Any] = {}

    async def async_load_capabilities(self) -> None:
        """Use the device's own map; a missing optional map is not a lockout."""
        try:
            self.capabilities = await self._request_json(
                "GET", f"/inverter/map/{self.device_id}"
            )
        except IngeteamAuthError:
            raise
        except IngeteamApiError:
            self.capabilities = {}

    def supports(self, section: str, address: int, bit: int = 0) -> bool:
        fields = self.capabilities.get(section)
        if not isinstance(fields, list):
            return True
        return any(
            isinstance(f, dict) and f.get("add") == address and f.get("start", 0) == bit
            for f in fields
        )

    def ranges(self, section: str, requested) -> list[dict]:
        if not isinstance(self.capabilities.get(section), list):
            return list(requested)
        allowed = {
            f["add"]
            for f in self.capabilities[section]
            if isinstance(f, dict) and type(f.get("add")) is int
        }
        return [
            {"address": a, "length": 1}
            for r in requested
            for a in range(r["address"], r["address"] + r["length"])
            if a in allowed
        ]

    @property
    def base_url(self) -> str:
        """Return the local base URL."""
        return f"http://{self.host}:{self.port}"

    async def _request_json(
        self, method: str, path: str, payload: Any | None = None
    ) -> dict[str, Any]:
        """Perform an authenticated request and decode JSON."""
        headers: dict[str, str] = {
            "Accept": "application/json, text/plain, */*",
            "Authorization": self._authorization,
        }
        data: str | None = None
        if payload is not None:
            # The web portal sends a JSON string with this content type.
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            data = json.dumps(payload, separators=(",", ":"))

        try:
            async with self._session.request(
                method,
                f"{self.base_url}{path}",
                headers=headers,
                data=data,
                timeout=self._timeout,
            ) as response:
                if response.status in (401, 403):
                    raise IngeteamAuthError("Credenciales rechazadas por el inversor")
                response.raise_for_status()
                decoded = await response.json(content_type=None)
        except IngeteamAuthError:
            raise
        except (ClientResponseError, ClientError, TimeoutError) as err:
            raise IngeteamConnectionError(str(err)) from err
        except (ValueError, json.JSONDecodeError) as err:
            raise IngeteamApiError("Respuesta JSON no válida") from err

        if not isinstance(decoded, dict):
            raise IngeteamApiError("Formato de respuesta inesperado")
        return decoded

    async def async_device_info(self) -> dict[str, Any]:
        """Read communication-board identity and capabilities."""
        return await self._request_json("GET", "/system/info/device")

    async def async_events(self) -> AsyncIterator[SSEEvent]:
        """One authenticated SSE connection; owner handles watchdog/retries."""
        try:
            async with self._session.get(
                f"{self.base_url}{SSE_PATH}",
                headers={
                    "Accept": "text/event-stream",
                    "Cache-Control": "no-cache",
                    "Authorization": self._authorization,
                },
                timeout=ClientTimeout(total=None, sock_connect=10, sock_read=None),
            ) as response:
                if response.status in (401, 403):
                    raise IngeteamAuthError("SSE authentication rejected")
                response.raise_for_status()
                if response.content_type != "text/event-stream":
                    raise IngeteamApiError("Unexpected SSE content type")
                async for event in iter_sse(response.content.iter_any()):
                    yield event
        except IngeteamApiError:
            raise
        except (ClientError, TimeoutError) as err:
            raise IngeteamConnectionError("SSE connection failed") from err
        except (ValueError, UnicodeError) as err:
            raise IngeteamApiError("Invalid SSE framing") from err

    async def async_read_holding(self) -> dict[tuple[int, int], Any]:
        """Read the selected EMS holding registers."""
        response = await self._request_json(
            "POST",
            f"/inverter/holding/read/{self.device_id}",
            self.ranges("holding", HOLDING_RANGES),
        )
        return self._flatten_register_response(response)

    async def async_read_online(self) -> dict[tuple[int, int], Any]:
        """Read selected live inverter values."""
        response = await self._request_json(
            "POST",
            f"/inverter/online/read/{self.device_id}",
            self.ranges("online", ONLINE_RANGES),
        )
        return self._flatten_register_response(response)

    async def async_write_holding(
        self, address: int, startbit: int, value: int
    ) -> None:
        """Write one decoded holding value through the portal API.

        This endpoint applies EMS-related values immediately, unlike some raw
        Modbus writes observed on the tested ISS firmware.
        """
        await self.async_write_holding_values([(address, startbit, value)])

    async def async_write_holding_values(
        self, values: list[tuple[int, int, int]]
    ) -> None:
        """Write one or more decoded values in one HTTP transaction."""
        payload = {
            "Values": [
                {"address": address, "startbit": startbit, "value": value}
                for address, startbit, value in values
            ],
            "metadata": {"user": self.username, "host": "home-assistant"},
        }
        if any(not self.supports("holding", a, b) for a, b, _ in values):
            raise IngeteamApiError("Unsupported holding register on this device")
        response = await self._request_json(
            "POST", f"/inverter/holding/write/{self.device_id}", payload
        )
        result = response.get("result")
        if not isinstance(result, list) or not result:
            raise IngeteamApiError("El inversor no confirmó la escritura")
        if any(
            not isinstance(item, dict) or item.get("success") is not True
            for item in result
        ):
            raise IngeteamApiError(
                "The inverter rejected the write or returned an invalid confirmation"
            )

    @staticmethod
    def _flatten_register_response(
        response: dict[str, Any],
    ) -> dict[tuple[int, int], Any]:
        """Flatten the Data/range structure returned by the inverter."""
        values: dict[tuple[int, int], Any] = {}
        blocks: Iterable[Any] = response.get("Data", [])
        for block in blocks:
            if not isinstance(block, dict):
                continue
            for item in block.get("data", []):
                if not isinstance(item, dict) or "address" not in item:
                    continue
                if (
                    item.get("inconsistency") is True
                    or item.get("success") is False
                    or "value" not in item
                ):
                    continue
                key = (int(item["address"]), int(item.get("startbit", 0)))
                values[key] = item["value"]
        return values
