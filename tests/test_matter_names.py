"""Tests for writing Home Assistant names onto Matter nodes (fht_matter.py)."""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import struct
import tempfile
import threading
import unittest
from unittest.mock import patch

MODULE_PATH = Path(__file__).parents[1] / "future_homes_tech_app" / "fht_matter.py"
SPEC = importlib.util.spec_from_file_location("fht_matter", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MATTER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MATTER)

FABRIC = 0x1A2B3C4D5E6F7081
FABRIC_HEX = f"{FABRIC:016X}"


def matter_device(node_id: int, postfix: str = "MatterNodeDevice", name: str = "Light", **extra):
    return {
        "identifiers": [["matter", f"deviceid_{FABRIC_HEX}-{node_id:016X}-{postfix}"], ["matter", f"serial_{node_id}"]],
        "name": name,
        "name_by_user": None,
        **extra,
    }


def registry(*devices):
    return {"data": {"devices": list(devices)}}


class LabelTests(unittest.TestCase):
    def test_label_uses_the_rename_and_fits_32_bytes(self) -> None:
        self.assertEqual(MATTER.node_label("  Kitchen   Pendant "), "Kitchen Pendant")
        self.assertEqual(MATTER.node_label("x" * 40), "x" * 32)
        # Never cut a multi-byte character in half.
        trimmed = MATTER.node_label("é" * 20)
        self.assertLessEqual(len(trimmed.encode("utf-8")), 32)
        self.assertEqual(trimmed, "é" * 16)

    def test_wanted_labels_read_matter_devices_only(self) -> None:
        wanted = MATTER.wanted_labels(registry(
            matter_device(5, name="Eve Energy", name_by_user="Coffee Maker"),
            matter_device(6, name="Nanoleaf A19"),
            matter_device(7, postfix="3", name="Hue go", name_by_user="Desk Lamp"),
            matter_device(8, name="Off", disabled_by="user"),
            {"identifiers": [["zha", "00:11"]], "name": "Zigbee", "name_by_user": "Zigbee"},
        ))
        self.assertEqual(wanted, {
            (FABRIC_HEX, 5, "node"): "Coffee Maker",
            (FABRIC_HEX, 6, "node"): "Nanoleaf A19",
            (FABRIC_HEX, 7, "3"): "Desk Lamp",
        })

    def test_only_differing_labels_on_online_nodes_are_written(self) -> None:
        wanted = {
            (FABRIC_HEX, 5, "node"): "Coffee Maker",
            (FABRIC_HEX, 6, "node"): "Same",
            (FABRIC_HEX, 7, "3"): "Desk Lamp",
            (FABRIC_HEX, 7, "4"): "Composed part",
            (FABRIC_HEX, 9, "node"): "Offline",
            ("0000000000000001", 10, "node"): "Other fabric",
        }
        nodes = [
            {"node_id": 5, "available": True, "attributes": {"0/40/5": "Eve Energy"}},
            {"node_id": 6, "available": True, "attributes": {"0/40/5": "Same"}},
            {"node_id": 7, "available": True, "attributes": {"3/57/5": "Hue go", "3/57/65531": [], "4/6/0": True}},
            {"node_id": 9, "available": False, "attributes": {"0/40/5": "Old"}},
            {"node_id": 10, "available": True, "attributes": {"0/40/5": "Old"}},
        ]
        self.assertEqual(MATTER.label_writes(wanted, FABRIC, nodes), [
            (5, "0/40/5", "Eve Energy", "Coffee Maker"),
            (7, "3/57/5", "Hue go", "Desk Lamp"),
        ])

    def test_server_url_comes_from_the_matter_entry(self) -> None:
        def entries(url):
            return {"data": {"entries": [{"domain": "matter", "data": {"url": url}}]}}

        with patch.dict(os.environ, {"FHT_MATTER_SERVER_URL": ""}):
            self.assertEqual(MATTER.matter_server_url(entries("ws://localhost:5580/ws")), "ws://core-matter-server:5580/ws")
            self.assertEqual(MATTER.matter_server_url(entries("ws://192.168.1.20:5580/ws")), "ws://192.168.1.20:5580/ws")
            self.assertEqual(MATTER.matter_server_url({}), MATTER.DEFAULT_MATTER_SERVER_URL)
        with patch.dict(os.environ, {"FHT_MATTER_SERVER_URL": "ws://elsewhere:1/ws"}):
            self.assertEqual(MATTER.matter_server_url(entries("ws://localhost:5580/ws")), "ws://elsewhere:1/ws")

    def test_write_results_with_a_bad_status_count_as_failed(self) -> None:
        self.assertFalse(MATTER.write_failed([{"Path": {}, "Status": 0}]))
        self.assertTrue(MATTER.write_failed([{"Path": {}, "Status": 136}]))
        self.assertFalse(MATTER.write_failed(None))


class FakeMatterServer:
    """A Matter Server WebSocket on localhost that answers get_nodes and write_attribute."""

    def __init__(self, nodes, refuse_paths=()):
        self.nodes = nodes
        self.refuse_paths = set(refuse_paths)
        self.writes = []
        self.listener = socket.socket()
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen()
        self.url = f"ws://127.0.0.1:{self.listener.getsockname()[1]}/ws"
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def close(self):
        self.listener.close()

    def _serve(self):
        while True:
            try:
                connection, _ = self.listener.accept()
            except OSError:
                return
            with connection:
                self._handle(connection)

    @staticmethod
    def _send(connection, message):
        payload = json.dumps(message).encode()
        if len(payload) < 126:
            header = bytes((0x81, len(payload)))
        else:
            header = bytes((0x81, 126)) + struct.pack("!H", len(payload))
        connection.sendall(header + payload)

    @staticmethod
    def _receive(connection):
        def exact(size):
            data = b""
            while len(data) < size:
                chunk = connection.recv(size - len(data))
                if not chunk:
                    raise EOFError
                data += chunk
            return data

        first, second = exact(2)
        size = second & 0x7F
        if size == 126:
            size = struct.unpack("!H", exact(2))[0]
        elif size == 127:
            size = struct.unpack("!Q", exact(8))[0]
        mask = exact(4)
        payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(exact(size)))
        if first & 0x0F == 0x8:
            raise EOFError
        return json.loads(payload)

    def _handle(self, connection):
        request = b""
        while b"\r\n\r\n" not in request:
            request += connection.recv(4096)
        key = next(
            line.split(":", 1)[1].strip()
            for line in request.decode().split("\r\n")
            if line.lower().startswith("sec-websocket-key")
        )
        accept = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode()
        connection.sendall(
            "HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Accept: {accept}\r\n\r\n".encode()
        )
        self._send(connection, {"fabric_id": 1, "compressed_fabric_id": FABRIC, "schema_version": 11})
        while True:
            try:
                message = self._receive(connection)
            except (EOFError, OSError):
                return
            args = message.get("args") or {}
            if message["command"] == "get_nodes":
                self._send(connection, {"message_id": message["message_id"], "result": self.nodes})
            elif message["command"] == "write_attribute":
                path = args["attribute_path"]
                if path in self.refuse_paths:
                    self._send(connection, {"message_id": message["message_id"], "result": [{"Path": {}, "Status": 136}]})
                    continue
                self.writes.append((args["node_id"], path, args["value"]))
                for node in self.nodes:
                    if node["node_id"] == args["node_id"]:
                        node["attributes"][path] = args["value"]
                self._send(connection, {"message_id": message["message_id"], "result": [{"Path": {}, "Status": 0}]})
            else:
                self._send(connection, {"message_id": message["message_id"], "error_code": 1, "details": "unknown"})


class SyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.storage = Path(self.directory.name) / ".storage"
        self.storage.mkdir()
        self.logs = []

    def write_storage(self, url, devices):
        (self.storage / "core.config_entries").write_text(json.dumps(
            {"data": {"entries": [{"domain": "matter", "data": {"url": url}}]}}
        ))
        (self.storage / "core.device_registry").write_text(json.dumps(registry(*devices)))

    def test_sync_renames_nodes_and_then_leaves_them_alone(self) -> None:
        server = FakeMatterServer([
            {"node_id": 5, "available": True, "attributes": {"0/40/5": "Eve Energy"}},
            {"node_id": 7, "available": True, "attributes": {"3/57/5": "Hue go", "4/57/5": "Hue bulb"}},
        ], refuse_paths={"4/57/5"})
        self.addCleanup(server.close)
        self.write_storage(server.url, [
            matter_device(5, name="Eve Energy", name_by_user="Coffee Maker"),
            matter_device(7, postfix="3", name="Hue go", name_by_user="Desk Lamp"),
            matter_device(7, postfix="4", name="Hue bulb", name_by_user="Porch"),
        ])
        sync = MATTER.MatterNameSync(Path(self.directory.name), log=self.logs.append)
        # The Matter entry's localhost URL would point at core-matter-server.
        environment = patch.dict(os.environ, {"FHT_MATTER_SERVER_URL": server.url})
        environment.start()
        self.addCleanup(environment.stop)

        self.assertEqual(sync.sync(), [(5, "0/40/5", "Coffee Maker"), (7, "3/57/5", "Desk Lamp")])
        self.assertEqual(server.writes, [(5, "0/40/5", "Coffee Maker"), (7, "3/57/5", "Desk Lamp")])
        self.assertTrue(any("doesn't allow renaming" in line for line in self.logs))

        # Already in step, and the refused label isn't retried.
        self.assertEqual(sync.sync(), [])
        self.assertEqual(len(server.writes), 2)

        # A rename in Home Assistant reaches the node on the next pass.
        self.write_storage(server.url, [matter_device(5, name="Eve Energy", name_by_user="Espresso")])
        self.assertEqual(sync.sync(), [(5, "0/40/5", "Espresso")])

    def test_run_once_waits_for_a_registry_change(self) -> None:
        self.write_storage("ws://127.0.0.1:9/ws", [matter_device(5, name="A")])
        sync = MATTER.MatterNameSync(Path(self.directory.name), log=self.logs.append)
        calls = []
        with patch.object(sync, "sync", side_effect=lambda: calls.append(1) or []):
            sync.run_once(now=1000.0)
            sync.run_once(now=1060.0)
            self.assertEqual(len(calls), 1)
            sync.run_once(now=1000.0 + MATTER.FULL_SYNC_SECONDS + 1)
            self.assertEqual(len(calls), 2)

    def test_unreachable_server_is_logged_once_and_retried(self) -> None:
        self.write_storage("ws://127.0.0.1:9/ws", [matter_device(5, name="A")])
        sync = MATTER.MatterNameSync(Path(self.directory.name), log=self.logs.append)
        with patch.dict(os.environ, {"FHT_MATTER_SERVER_URL": ""}):
            sync.run_once(now=1000.0)
            sync.run_once(now=1060.0)
        self.assertEqual(len(self.logs), 1)
        self.assertIn("not synced", self.logs[0])

    def test_no_matter_integration_means_no_connection(self) -> None:
        (self.storage / "core.config_entries").write_text(json.dumps({"data": {"entries": []}}))
        factory_calls = []
        sync = MATTER.MatterNameSync(Path(self.directory.name), client_factory=factory_calls.append)
        self.assertEqual(sync.sync(), [])
        self.assertEqual(factory_calls, [])


if __name__ == "__main__":
    unittest.main()
