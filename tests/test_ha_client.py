"""Tests for the Home Assistant WebSocket client (fht_ha_client.py)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import socket
import unittest
from unittest.mock import Mock, patch

MODULE_PATH = (
    Path(__file__).parents[1]
    / "future_homes_tech_app"
    / "fht_ha_client.py"
)
SPEC = importlib.util.spec_from_file_location("fht_ha_client", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
HA_CLIENT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HA_CLIENT)


class WebSocketClientTests(unittest.TestCase):
    """Check the frames and the shared connection."""

    def test_websocket_commands_share_one_connection(self) -> None:
        """Reuse one authenticated connection; reopen once if it went stale."""
        opened = []
        replies = {}

        def open_socket(url):
            connection = Mock(name=f"socket{len(opened)}")
            connection.stale = False
            opened.append(connection)
            replies[connection] = [{"type": "auth_required"}, {"type": "auth_ok"}]
            return connection, bytearray()

        def send(connection, message):
            if "id" in message:
                if connection.stale:
                    raise BrokenPipeError("closed")
                replies[connection].append({"id": message["id"], "type": "result", "success": True, "result": message["type"]})

        def receive(connection, buffered):
            return replies[connection].pop(0)

        HA_CLIENT._WEBSOCKET_POOL.close()
        with patch.object(HA_CLIENT, "_open_websocket", side_effect=open_socket), \
                patch.object(HA_CLIENT, "_send_websocket_json", side_effect=send), \
                patch.object(HA_CLIENT, "_receive_websocket_json", side_effect=receive), \
                patch.object(HA_CLIENT, "_send_websocket_frame"):
            self.assertEqual(HA_CLIENT.execute_websocket_commands("t", "ws://ha", [{"type": "a"}]), ["a"])
            self.assertEqual(HA_CLIENT.execute_websocket_commands("t", "ws://ha", [{"type": "b"}, {"type": "c"}]), ["b", "c"])
            self.assertEqual(len(opened), 1)
            opened[0].stale = True
            self.assertEqual(HA_CLIENT.execute_websocket_commands("t", "ws://ha", [{"type": "d"}]), ["d"])
            self.assertEqual(len(opened), 2)
        HA_CLIENT._WEBSOCKET_POOL.close()

    def test_websocket_json_frame_round_trip(self) -> None:
        """Encode and decode masked WebSocket JSON frames."""
        sending_socket, receiving_socket = socket.socketpair()
        self.addCleanup(sending_socket.close)
        self.addCleanup(receiving_socket.close)

        payload = {
            "id": 1,
            "type": "config/entity_registry/list_for_display",
        }
        HA_CLIENT._send_websocket_json(sending_socket, payload)
        received = HA_CLIENT._receive_websocket_json(
            receiving_socket,
            bytearray(),
        )

        self.assertEqual(received, payload)


if __name__ == "__main__":
    unittest.main()
