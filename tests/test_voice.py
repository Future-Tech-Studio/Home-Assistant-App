"""Tests for voice commands through Home Assistant Assist (fht_voice.py)."""

from __future__ import annotations

import io
import json
import unittest
from unittest.mock import Mock
from urllib.error import URLError

from test_server import SERVER

VOICE = SERVER.VOICE

PIPELINE = {
    "language": "en",
    "stt_engine": "stt.speech_to_phrase",
    "stt_language": "en",
    "conversation_engine": "conversation.home_assistant",
    "conversation_language": "en",
}


def assist_reply(speech="Turned off the light", response_type="action_done"):
    return {"response": {"response_type": response_type, "speech": {"plain": {"speech": speech}}}}


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


class VoiceAssistantTests(unittest.TestCase):
    def assistant(self, reply=None, stt=None, pipeline=PIPELINE):
        self.requests = []
        self.commands = []

        def run_commands(commands):
            self.commands.extend(commands)
            if commands[0]["type"] == "assist_pipeline/pipeline/get":
                return [pipeline]
            return [reply or assist_reply()]

        def opener(request, timeout):
            self.requests.append(request)
            if isinstance(stt, Exception):
                raise stt
            return FakeResponse(json.dumps(stt or {"result": "success", "text": "Turn off Chloe's light"}).encode())

        return VOICE.VoiceAssistant("token", run_commands, "http://supervisor/core/api/", opener)

    def test_audio_goes_to_the_pipeline_speech_engine_then_its_agent(self):
        result = self.assistant().command(audio=b"\x00\x01" * 800)
        self.assertEqual(result, {"transcript": "Turn off Chloe's light", "reply": "Turned off the light", "success": True})
        request = self.requests[0]
        self.assertEqual(request.full_url, "http://supervisor/core/api/stt/stt.speech_to_phrase")
        self.assertEqual(request.data, b"\x00\x01" * 800)
        self.assertEqual(request.get_header("Authorization"), "Bearer token")
        self.assertEqual(
            request.get_header("X-speech-content"),
            "format=wav; codec=pcm; sample_rate=16000; bit_rate=16; channel=1; language=en",
        )
        self.assertEqual(self.commands[-1], {
            "type": "conversation/process",
            "text": "Turn off Chloe's light",
            "language": "en",
            "agent_id": "conversation.home_assistant",
        })

    def test_typed_text_skips_speech_to_text(self):
        result = self.assistant().command(text="  turn   on the porch light ")
        self.assertEqual(result["transcript"], "turn on the porch light")
        self.assertEqual(self.requests, [])

    def test_failed_commands_explain_themselves(self):
        cases = [
            ({"pipeline": {**PIPELINE, "stt_engine": None}}, {"audio": b"\x00\x00"}, "no speech-to-text"),
            ({"stt": {"result": "error", "text": ""}}, {"audio": b"\x00\x00"}, "didn't catch that"),
            ({"stt": URLError("down")}, {"audio": b"\x00\x00"}, "couldn't turn that into text"),
            ({}, {"audio": b""}, "No sound"),
            ({}, {"audio": b"\x00" * (VOICE.MAX_AUDIO_BYTES + 2)}, "too long"),
            ({}, {"text": "   "}, "Say or type"),
            ({}, {"text": "x" * 501}, "too long"),
        ]
        for options, command, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(VOICE.VoiceCommandError, message):
                self.assistant(**options).command(**command)

    def test_assist_answers_that_did_nothing_are_not_success(self):
        result = self.assistant(reply=assist_reply("Sorry, I couldn't understand that", "error")).command(text="sing")
        self.assertEqual(result["reply"], "Sorry, I couldn't understand that")
        self.assertFalse(result["success"])
        quiet = self.assistant(reply=assist_reply("", "action_done")).command(text="lights off")
        self.assertEqual(quiet["reply"], "Done.")

    def test_unavailable_assist_is_a_voice_error(self):
        assistant = VOICE.VoiceAssistant("token", Mock(side_effect=SERVER.HomeAssistantAPIError("socket closed")))
        with self.assertRaisesRegex(VOICE.VoiceCommandError, "unavailable"):
            assistant.command(text="lights off")


class VoiceRouteTests(unittest.TestCase):
    def handler(self, content_type, body):
        handler = SERVER.FutureHomesTechRequestHandler.__new__(SERVER.FutureHomesTechRequestHandler)
        handler.path = "/api/voice/command"
        handler.headers = {"Content-Type": content_type, "Content-Length": str(len(body))}
        handler.rfile = io.BytesIO(body)
        handler.voice_assistant = Mock()
        handler.voice_assistant.command.return_value = {"transcript": "lights off", "reply": "Done.", "success": True}
        handler._send_json = Mock()
        return handler

    def test_route_passes_audio_or_text(self):
        handler = self.handler("application/octet-stream", b"\x01\x02")
        handler._dispatch_POST()
        handler.voice_assistant.command.assert_called_once_with(audio=b"\x01\x02")
        self.assertEqual(handler._send_json.call_args.args, (200, {"ok": True, "transcript": "lights off", "reply": "Done.", "success": True}))

        handler = self.handler("application/json", b'{"text": "lights off"}')
        handler._dispatch_POST()
        handler.voice_assistant.command.assert_called_once_with(text="lights off")

    def test_route_reports_voice_errors_and_oversized_audio(self):
        handler = self.handler("application/json", b'{"text": ""}')
        handler.voice_assistant.command.side_effect = VOICE.VoiceCommandError("Say or type a command.")
        handler._dispatch_POST()
        self.assertEqual(handler._send_json.call_args.args, (200, {"ok": False, "error": "Say or type a command."}))

        handler = self.handler("application/octet-stream", b"")
        handler.headers["Content-Length"] = str(VOICE.MAX_AUDIO_BYTES + 1)
        with self.assertRaises(SERVER.RequestBodyTooLarge):
            handler._dispatch_POST()
        handler.voice_assistant.command.assert_not_called()

    def test_page_may_use_its_own_microphone(self):
        handler = SERVER.FutureHomesTechRequestHandler.__new__(SERVER.FutureHomesTechRequestHandler)
        handler.send_header = Mock()
        handler._send_security_headers()
        self.assertIn(("Permissions-Policy", "camera=(), microphone=(self), geolocation=(), payment=()"), [call.args for call in handler.send_header.call_args_list])


if __name__ == "__main__":
    unittest.main()
