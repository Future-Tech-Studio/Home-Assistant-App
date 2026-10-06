"""Keep each Matter node's own name (its node label) in step with Home Assistant.

Home Assistant shows a Matter device under the name you give it, but the
device itself keeps the label it was commissioned with, so other Matter
controllers (Apple Home, Google Home, the device's own app) and a fresh
re-interview still see the old name. This module writes the current Home
Assistant name onto each node through the Matter Server, and again whenever
the name changes in Home Assistant.

Only the Basic Information cluster's NodeLabel (endpoint 0) is written for a
whole node; a device behind a Matter bridge gets its Bridged Device Basic
Information NodeLabel on its own endpoint. Nothing else on a device changes.
"""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import re
import socket
import threading
import time
from typing import Any, Callable
from urllib.parse import urlsplit, urlunsplit

_ha_client_spec = importlib.util.spec_from_file_location("fht_ha_client", Path(__file__).with_name("fht_ha_client.py"))
HA_CLIENT = importlib.util.module_from_spec(_ha_client_spec)
_ha_client_spec.loader.exec_module(HA_CLIENT)

# The Matter Server App's address from other Apps; Home Assistant's own Matter
# entry may say localhost, which only works from Home Assistant itself.
DEFAULT_MATTER_SERVER_URL = "ws://core-matter-server:5580/ws"
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}

# Matter caps NodeLabel at 32 bytes.
NODE_LABEL_MAX_BYTES = 32
NODE_LABEL_PATH = "0/40/5"
BRIDGED_CLUSTER = 57

# Home Assistant's Matter device identifier:
# deviceid_<compressed fabric id>-<node id>-<MatterNodeDevice or endpoint>
_DEVICE_IDENTIFIER = re.compile(
    r"^deviceid_([0-9A-Fa-f]{16})-([0-9A-Fa-f]{16})-(MatterNodeDevice|\d+)$"
)

CHECK_SECONDS = 60
FULL_SYNC_SECONDS = 15 * 60
START_DELAY_SECONDS = 90


class MatterServerError(Exception):
    """The Matter Server could not be reached or refused a command."""


class MatterCommandRefused(MatterServerError):
    """The Matter Server answered a command with an error; the connection is fine."""


def node_label(name: str) -> str:
    """Return ``name`` trimmed to what a Matter NodeLabel can hold."""
    label = " ".join(str(name or "").split())
    encoded = label.encode("utf-8")
    if len(encoded) <= NODE_LABEL_MAX_BYTES:
        return label
    return encoded[:NODE_LABEL_MAX_BYTES].decode("utf-8", errors="ignore").rstrip()


def wanted_labels(device_registry: dict[str, Any]) -> dict[tuple[str, int, str], str]:
    """Map (fabric, node, "node" or endpoint) to the label Home Assistant names it.

    The name is the one Home Assistant shows: your rename if there is one,
    otherwise the device's own name. Disabled devices are left alone.
    """
    wanted: dict[tuple[str, int, str], str] = {}
    devices = (device_registry.get("data") or {}).get("devices") or []
    for device in devices:
        if not isinstance(device, dict) or device.get("disabled_by"):
            continue
        label = node_label(device.get("name_by_user") or device.get("name") or "")
        if not label:
            continue
        for identifier in device.get("identifiers") or []:
            if not (isinstance(identifier, list) and len(identifier) == 2 and identifier[0] == "matter"):
                continue
            match = _DEVICE_IDENTIFIER.match(str(identifier[1]))
            if not match:
                continue
            fabric, node_id, postfix = match.groups()
            where = "node" if postfix == "MatterNodeDevice" else postfix
            wanted[(fabric.upper(), int(node_id, 16), where)] = label
    return wanted


def label_writes(
    wanted: dict[tuple[str, int, str], str],
    compressed_fabric_id: int,
    nodes: list[dict[str, Any]],
) -> list[tuple[int, str, str, str]]:
    """Return (node id, attribute path, current label, new label) still to write.

    Nodes that are offline, endpoints that aren't bridged devices (a composed
    device shares its node's label) and labels that already match are skipped.
    """
    fabric = f"{int(compressed_fabric_id):016X}"
    by_node = {
        int(node["node_id"]): node
        for node in nodes
        if isinstance(node, dict) and isinstance(node.get("node_id"), int)
    }
    writes = []
    for (wanted_fabric, node_id, where), label in sorted(wanted.items(), key=lambda item: (item[0][1], item[0][2])):
        node = by_node.get(node_id)
        if wanted_fabric != fabric or not node or node.get("available") is False:
            continue
        attributes = node.get("attributes") or {}
        if where == "node":
            path = NODE_LABEL_PATH
        else:
            prefix = f"{where}/{BRIDGED_CLUSTER}/"
            if not any(str(key).startswith(prefix) for key in attributes):
                continue
            path = f"{prefix}5"
        current = str(attributes.get(path) or "")
        if current != label:
            writes.append((node_id, path, current, label))
    return writes


def matter_server_url(config_entries: dict[str, Any]) -> str:
    """Return the Matter Server WebSocket URL to use from this App."""
    configured = os.environ.get("FHT_MATTER_SERVER_URL", "").strip()
    if configured:
        return configured
    for entry in (config_entries.get("data") or {}).get("entries") or []:
        if not isinstance(entry, dict) or entry.get("domain") != "matter" or entry.get("disabled_by"):
            continue
        url = str((entry.get("data") or {}).get("url") or "").strip()
        parts = urlsplit(url)
        if parts.scheme not in {"ws", "wss"} or not parts.hostname:
            continue
        if parts.hostname in LOOPBACK_HOSTS:
            netloc = f"core-matter-server:{parts.port or 5580}"
            return urlunsplit((parts.scheme, netloc, parts.path or "/ws", parts.query, ""))
        return url
    return DEFAULT_MATTER_SERVER_URL


def has_matter_entry(config_entries: dict[str, Any]) -> bool:
    return any(
        isinstance(entry, dict) and entry.get("domain") == "matter" and not entry.get("disabled_by")
        for entry in (config_entries.get("data") or {}).get("entries") or []
    )


class MatterServerClient:
    """One short-lived connection to the Matter Server's WebSocket API."""

    def __init__(self, url: str, timeout: float = 60.0) -> None:
        self.url = url
        self.timeout = timeout
        self.connection: socket.socket | None = None
        self.buffered = bytearray()
        self.server_info: dict[str, Any] = {}
        self._next_id = 1

    def __enter__(self) -> "MatterServerClient":
        try:
            self.connection, self.buffered = HA_CLIENT._open_websocket(self.url)
            self.connection.settimeout(self.timeout)
            # The server says who it is (fabric, schema) before any command.
            self.server_info = HA_CLIENT._receive_websocket_json(self.connection, self.buffered)
        except (OSError, ValueError, HA_CLIENT.WebSocketProtocolError) as err:
            self.close()
            raise MatterServerError(f"Unable to reach the Matter Server at {self.url}: {err}") from err
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def close(self) -> None:
        if self.connection is not None:
            try:
                self.connection.close()
            except OSError:
                pass
        self.connection = None

    def command(self, command: str, **args: Any) -> Any:
        assert self.connection is not None
        message_id = str(self._next_id)
        self._next_id += 1
        try:
            HA_CLIENT._send_websocket_json(
                self.connection, {"message_id": message_id, "command": command, "args": args}
            )
            while True:
                response = HA_CLIENT._receive_websocket_json(self.connection, self.buffered)
                if response.get("message_id") != message_id:
                    continue
                if "error_code" in response:
                    raise MatterCommandRefused(
                        f"Matter Server refused {command}: {response.get('details') or response.get('error_code')}"
                    )
                return response.get("result")
        except (OSError, ValueError, HA_CLIENT.WebSocketProtocolError) as err:
            raise MatterServerError(f"Matter Server connection failed during {command}: {err}") from err


def write_failed(result: Any) -> bool:
    """True when a write_attribute result reports a non-success status."""
    if not isinstance(result, list):
        return False
    for status in result:
        if isinstance(status, dict):
            code = status.get("Status", status.get("status", 0))
            if code not in (0, None):
                return True
    return False


class MatterNameSync:
    """Write Home Assistant's device names onto Matter nodes, and keep them there."""

    def __init__(
        self,
        config_directory: Path,
        client_factory: Callable[[str], MatterServerClient] = MatterServerClient,
        log: Callable[[str], None] | None = None,
    ) -> None:
        self._storage = Path(config_directory) / ".storage"
        self._client_factory = client_factory
        self._log = log or (lambda message: print(f"[Matter] {message}", flush=True))
        self._registry_stamp: float | None = None
        self._synced_at = 0.0
        # Labels a node refused, so a read-only label isn't retried every pass.
        self._refused: dict[tuple[int, str], str] = {}
        self._unreachable_logged = False
        self.stop_event = threading.Event()

    def _read(self, name: str) -> dict[str, Any]:
        try:
            data = json.loads((self._storage / name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def sync(self) -> list[tuple[int, str, str]]:
        """Write every label that differs from Home Assistant's name. Returns what was written."""
        entries = self._read("core.config_entries")
        if not has_matter_entry(entries):
            return []
        wanted = wanted_labels(self._read("core.device_registry"))
        if not wanted:
            return []
        url = matter_server_url(entries)
        written: list[tuple[int, str, str]] = []
        with self._client_factory(url) as client:
            fabric = client.server_info.get("compressed_fabric_id")
            if not isinstance(fabric, int):
                raise MatterServerError("The Matter Server did not say which fabric it runs.")
            nodes = client.command("get_nodes") or []
            for node_id, path, current, label in label_writes(wanted, fabric, nodes):
                if self._refused.get((node_id, path)) == label:
                    continue
                try:
                    result = client.command("write_attribute", node_id=node_id, attribute_path=path, value=label)
                except MatterCommandRefused as err:
                    self._refused[(node_id, path)] = label
                    self._log(f"Node {node_id} kept its name {current!r}; renaming it to {label!r} failed: {err}")
                    continue
                if write_failed(result):
                    self._refused[(node_id, path)] = label
                    self._log(f"Node {node_id} doesn't allow renaming {path} to {label!r}; it keeps {current!r}.")
                    continue
                self._refused.pop((node_id, path), None)
                written.append((node_id, path, label))
                self._log(f"Renamed node {node_id} ({path}) from {current!r} to {label!r}.")
        return written

    def _registry_changed(self) -> bool:
        try:
            stamp = (self._storage / "core.device_registry").stat().st_mtime
        except OSError:
            stamp = None
        changed = stamp != self._registry_stamp
        self._registry_stamp = stamp
        return changed

    def run_once(self, now: float | None = None) -> None:
        """One pass of the background loop: sync when names changed or it's been a while."""
        now = time.monotonic() if now is None else now
        changed = self._registry_changed()
        if not changed and now - self._synced_at < FULL_SYNC_SECONDS:
            return
        try:
            self.sync()
        except MatterServerError as err:
            if not self._unreachable_logged:
                self._log(f"Node names not synced: {err}")
                self._unreachable_logged = True
            # Try again on the next check rather than waiting for the next change.
            self._registry_stamp = None
            return
        self._unreachable_logged = False
        self._synced_at = now

    def run_forever(self, start_delay: float = START_DELAY_SECONDS) -> None:
        if self.stop_event.wait(start_delay):
            return
        while not self.stop_event.is_set():
            try:
                self.run_once()
            except Exception as err:  # noqa: BLE001 - keep the loop alive
                self._log(f"Node name sync stopped a pass: {err}")
            self.stop_event.wait(CHECK_SECONDS)
