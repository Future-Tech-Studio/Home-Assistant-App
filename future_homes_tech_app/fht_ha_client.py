"""Talk to Home Assistant over its WebSocket API.

Split out of server.py: the frame encoding, the handshake, and the one shared
authenticated connection that execute_websocket_commands reuses. server.py
keeps the old names as aliases.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import socket
import ssl
import struct
import threading
import time
from typing import Any
from urllib.parse import urlsplit

MAX_WEBSOCKET_MESSAGE_SIZE = 64 * 1024 * 1024


class HomeAssistantAPIError(Exception):
    """Indicate a failure while reading Home Assistant entities."""


class WebSocketProtocolError(Exception):
    """Indicate an invalid Home Assistant WebSocket response."""


def _read_exact(
    connection: socket.socket,
    buffered: bytearray,
    size: int,
) -> bytes:
    """Read an exact number of bytes while preserving buffered data."""
    while len(buffered) < size:
        chunk = connection.recv(max(4096, size - len(buffered)))
        if not chunk:
            raise WebSocketProtocolError(
                "Home Assistant closed the WebSocket connection."
            )
        buffered.extend(chunk)

    result = bytes(buffered[:size])
    del buffered[:size]
    return result


def _send_websocket_frame(
    connection: socket.socket,
    opcode: int,
    payload: bytes,
) -> None:
    """Send one masked client WebSocket frame."""
    first_byte = 0x80 | opcode
    payload_size = len(payload)
    if payload_size < 126:
        header = bytes((first_byte, 0x80 | payload_size))
    elif payload_size <= 0xFFFF:
        header = bytes((first_byte, 0x80 | 126))
        header += struct.pack("!H", payload_size)
    else:
        header = bytes((first_byte, 0x80 | 127))
        header += struct.pack("!Q", payload_size)

    mask = os.urandom(4)
    masked_payload = bytes(
        byte ^ mask[index % 4]
        for index, byte in enumerate(payload)
    )
    connection.sendall(header + mask + masked_payload)


def _receive_websocket_frame(
    connection: socket.socket,
    buffered: bytearray,
) -> tuple[bool, int, bytes]:
    """Receive one WebSocket frame."""
    first_byte, second_byte = _read_exact(
        connection,
        buffered,
        2,
    )
    final = bool(first_byte & 0x80)
    opcode = first_byte & 0x0F
    masked = bool(second_byte & 0x80)
    payload_size = second_byte & 0x7F

    if first_byte & 0x70:
        raise WebSocketProtocolError(
            "Home Assistant returned unsupported WebSocket flags."
        )
    if payload_size == 126:
        payload_size = struct.unpack(
            "!H",
            _read_exact(connection, buffered, 2),
        )[0]
    elif payload_size == 127:
        payload_size = struct.unpack(
            "!Q",
            _read_exact(connection, buffered, 8),
        )[0]
    if payload_size > MAX_WEBSOCKET_MESSAGE_SIZE:
        raise WebSocketProtocolError(
            "Home Assistant returned an oversized registry response."
        )

    mask = (
        _read_exact(connection, buffered, 4)
        if masked
        else b""
    )
    payload = _read_exact(connection, buffered, payload_size)
    if masked:
        payload = bytes(
            byte ^ mask[index % 4]
            for index, byte in enumerate(payload)
        )
    return final, opcode, payload


def _receive_websocket_json(
    connection: socket.socket,
    buffered: bytearray,
) -> dict[str, Any]:
    """Receive one complete JSON text message."""
    payload = bytearray()
    receiving_text = False

    while True:
        final, opcode, frame_payload = _receive_websocket_frame(
            connection,
            buffered,
        )
        if opcode == 0x8:
            raise WebSocketProtocolError(
                "Home Assistant closed the WebSocket connection."
            )
        if opcode == 0x9:
            _send_websocket_frame(connection, 0xA, frame_payload)
            continue
        if opcode == 0xA:
            continue
        if opcode == 0x1:
            if receiving_text:
                raise WebSocketProtocolError(
                    "Home Assistant returned overlapping text messages."
                )
            receiving_text = True
            payload.extend(frame_payload)
        elif opcode == 0x0 and receiving_text:
            payload.extend(frame_payload)
        else:
            raise WebSocketProtocolError(
                "Home Assistant returned an unsupported WebSocket frame."
            )

        if len(payload) > MAX_WEBSOCKET_MESSAGE_SIZE:
            raise WebSocketProtocolError(
                "Home Assistant returned an oversized registry response."
            )
        if final:
            response = json.loads(payload.decode("utf-8"))
            if not isinstance(response, dict):
                raise WebSocketProtocolError(
                    "Home Assistant returned invalid WebSocket JSON."
                )
            return response


def _send_websocket_json(
    connection: socket.socket,
    payload: dict[str, Any],
) -> None:
    """Send one JSON text message."""
    _send_websocket_frame(
        connection,
        0x1,
        json.dumps(
            payload,
            separators=(",", ":"),
        ).encode("utf-8"),
    )


def _open_websocket(
    websocket_url: str,
    extra_headers: dict[str, str] | None = None,
    verify_ssl: bool = True,
) -> tuple[socket.socket, bytearray]:
    """Open and validate a Home Assistant WebSocket connection."""
    parsed = urlsplit(websocket_url)
    if parsed.scheme not in {"ws", "wss"} or not parsed.hostname:
        raise WebSocketProtocolError(
            "The Home Assistant WebSocket URL is invalid."
        )

    secure = parsed.scheme == "wss"
    port = parsed.port or (443 if secure else 80)
    connection = socket.create_connection(
        (parsed.hostname, port),
        timeout=30,
    )
    if secure:
        context = ssl.create_default_context()
        if not verify_ssl:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        connection = context.wrap_socket(
            connection,
            server_hostname=parsed.hostname,
        )

    path = parsed.path or "/"
    if parsed.query:
        path += f"?{parsed.query}"
    host = parsed.hostname
    if port != (443 if secure else 80):
        host += f":{port}"

    websocket_key = base64.b64encode(os.urandom(16)).decode("ascii")
    custom_headers = "".join(
        f"{key}: {value}\r\n"
        for key, value in (extra_headers or {}).items()
    )
    request = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {websocket_key}\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        f"{custom_headers}"
        "\r\n"
    ).encode("ascii")
    connection.sendall(request)

    buffered = bytearray()
    while b"\r\n\r\n" not in buffered:
        chunk = connection.recv(4096)
        if not chunk:
            connection.close()
            raise WebSocketProtocolError(
                "Home Assistant closed the WebSocket handshake."
            )
        buffered.extend(chunk)
        if len(buffered) > 65536:
            connection.close()
            raise WebSocketProtocolError(
                "Home Assistant returned an oversized handshake."
            )

    header_bytes, remaining = bytes(buffered).split(
        b"\r\n\r\n",
        1,
    )
    buffered = bytearray(remaining)
    header_lines = header_bytes.decode("iso-8859-1").split("\r\n")
    if not header_lines[0].startswith("HTTP/1.1 101"):
        connection.close()
        raise WebSocketProtocolError(
            "Home Assistant rejected the WebSocket handshake."
        )

    headers = {
        key.strip().casefold(): value.strip()
        for line in header_lines[1:]
        if ":" in line
        for key, value in [line.split(":", 1)]
    }
    expected_accept = base64.b64encode(
        hashlib.sha1(
            (
                websocket_key
                + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
            ).encode("ascii")
        ).digest()
    ).decode("ascii")
    if headers.get("sec-websocket-accept") != expected_accept:
        connection.close()
        raise WebSocketProtocolError(
            "Home Assistant returned an invalid WebSocket handshake."
        )

    return connection, buffered


class _PooledWebSocket:
    """One authenticated Home Assistant WebSocket reused for commands."""

    IDLE_SECONDS = 300

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.connection: socket.socket | None = None
        self.buffered = bytearray()
        self.next_id = 1
        self.key: tuple[str, str] | None = None
        self.used_at = 0.0
        self.answered = 0

    def close(self) -> None:
        if self.connection is not None:
            try:
                _send_websocket_frame(self.connection, 0x8, b"")
            except OSError:
                pass
            try:
                self.connection.close()
            except OSError:
                pass
        self.connection = None
        self.buffered = bytearray()

    def open(self, token: str, websocket_url: str) -> None:
        self.close()
        connection, buffered = _open_websocket(websocket_url)
        self.connection, self.buffered = connection, buffered
        self.key = (token, websocket_url)
        self.next_id = 1
        if _receive_websocket_json(connection, buffered).get("type") != "auth_required":
            raise WebSocketProtocolError(
                "Home Assistant did not request WebSocket authentication."
            )
        _send_websocket_json(connection, {"type": "auth", "access_token": token})
        if _receive_websocket_json(connection, buffered).get("type") != "auth_ok":
            raise WebSocketProtocolError(
                "Home Assistant rejected WebSocket authentication."
            )

    def run(self, commands: list[dict[str, Any]]) -> list[Any]:
        assert self.connection is not None
        results = []
        self.answered = 0
        for command in commands:
            request_id = self.next_id
            self.next_id += 1
            _send_websocket_json(self.connection, {"id": request_id, **command})
            while True:
                response = _receive_websocket_json(self.connection, self.buffered)
                if response.get("id") != request_id:
                    continue
                if response.get("type") != "result" or response.get("success") is not True:
                    error = response.get("error")
                    message = error.get("message") if isinstance(error, dict) else None
                    raise _WebSocketCommandRejected(
                        message or "Home Assistant rejected a registry request."
                    )
                results.append(response.get("result"))
                self.answered += 1
                break
        return results


class _WebSocketCommandRejected(WebSocketProtocolError):
    """Home Assistant answered a command with an error; the socket is fine."""


_WEBSOCKET_POOL = _PooledWebSocket()


def execute_websocket_commands(
    token: str,
    websocket_url: str,
    commands: list[dict[str, Any]],
) -> list[Any]:
    """Execute authenticated Home Assistant WebSocket commands.

    Commands share one kept-open connection instead of opening a new one per
    batch. A reused connection that turns out to be closed is reopened once
    before any command in the batch has been answered.
    """
    if not token:
        raise HomeAssistantAPIError(
            "The Home Assistant API token is unavailable."
        )
    pool = _WEBSOCKET_POOL
    with pool.lock:
        for attempt in range(2):
            reused = False
            try:
                pool.answered = 0
                if (
                    pool.connection is None
                    or pool.key != (token, websocket_url)
                    or time.monotonic() - pool.used_at > pool.IDLE_SECONDS
                ):
                    pool.open(token, websocket_url)
                else:
                    reused = True
                results = pool.run(commands)
                pool.used_at = time.monotonic()
                return results
            except _WebSocketCommandRejected as err:
                pool.used_at = time.monotonic()
                raise HomeAssistantAPIError(
                    f"Unable to organize Home Assistant light groups: {err}"
                ) from err
            except (
                OSError,
                UnicodeDecodeError,
                ValueError,
                json.JSONDecodeError,
                WebSocketProtocolError,
            ) as err:
                answered = pool.answered
                pool.close()
                if reused and attempt == 0 and answered == 0:
                    continue
                raise HomeAssistantAPIError(
                    "Unable to organize Home Assistant light groups: "
                    f"{err}"
                ) from err
    raise HomeAssistantAPIError("Unable to reach Home Assistant.")
