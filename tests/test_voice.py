"""Tests for voice commands through Home Assistant Assist (fht_voice.py)."""

from __future__ import annotations

import io
import json
import unittest
from pathlib import Path
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
            ({"pipeline": {**PIPELINE, "stt_engine": None}}, {"audio": b"\x00\x00"}, "isn.t set up yet"),
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
        self.assertEqual(handler._send_json.call_args.args, (200, {"ok": False, "error": "Say or type a command.", "setup": False}))

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


class FakeSupervisor:
    """Supervisor and Home Assistant as Voice setup sees them."""

    def __init__(self, installed=False, started=False, role=True, entity_after_flow=True):
        self.installed = installed
        self.started = started
        self.role = role
        self.entity_after_flow = entity_after_flow
        self.flow_confirmed = False
        self.calls = []
        self.pipeline = {
            "id": "01pipeline", "name": "Home Assistant", "language": "en",
            "conversation_engine": "conversation.home_assistant", "conversation_language": "en",
            "stt_engine": None, "stt_language": None, "tts_engine": "tts.piper", "tts_language": "en_US",
            "tts_voice": None, "wake_word_entity": None, "wake_word_id": None, "prefer_local_intents": True,
        }

    def opener(self, request, timeout):
        url = request.full_url
        self.calls.append((request.get_method(), url))
        if url.startswith("http://supervisor/addons/") or url.startswith("http://supervisor/store/"):
            if not self.role:
                raise VOICE.HTTPError(url, 403, "Forbidden", {}, None)
        if url == "http://supervisor/addons/core_speech-to-phrase/info":
            if not self.installed:
                raise VOICE.HTTPError(url, 400, "Bad Request", {}, None)
            return FakeResponse(json.dumps({"data": {"version": "1.4.1", "state": "started" if self.started else "stopped"}}).encode())
        if url == "http://supervisor/store/addons/core_speech-to-phrase/install":
            self.installed = True
            return FakeResponse(b'{"result": "ok"}')
        if url == "http://supervisor/addons/core_speech-to-phrase/start":
            self.started = True
            return FakeResponse(b'{"result": "ok"}')
        if url == "http://supervisor/core/api/states":
            states = [{"entity_id": "stt.home_assistant_cloud"}]
            if self.flow_confirmed and self.entity_after_flow:
                states.append({"entity_id": "stt.speech_to_phrase"})
            return FakeResponse(json.dumps(states).encode())
        if url == "http://supervisor/core/api/config/config_entries/flow/flow1":
            self.flow_confirmed = True
            return FakeResponse(b'{"type": "create_entry"}')
        raise AssertionError(url)

    def run_commands(self, commands):
        command = commands[0]
        if command["type"] == "assist_pipeline/pipeline/get":
            return [dict(self.pipeline)]
        if command["type"] == "config_entries/flow/progress":
            return [[
                {"flow_id": "other", "handler": "hue", "context": {"source": "zeroconf"}},
                *([] if self.flow_confirmed else [{"flow_id": "flow1", "handler": "wyoming", "context": {"source": "hassio"}}]),
            ]]
        if command["type"] == "assist_pipeline/pipeline/update":
            self.update = command
            self.pipeline.update(stt_engine=command["stt_engine"], stt_language=command["stt_language"])
            return [{}]
        raise AssertionError(command)

    def setup(self):
        return VOICE.VoiceSetup("token", self.run_commands, opener=self.opener, sleep=lambda _s: None, start_thread=lambda target: target())


class VoiceSetupTests(unittest.TestCase):
    def test_installs_starts_connects_and_turns_on_speech_to_text(self):
        home = FakeSupervisor()
        setup = home.setup()
        self.assertEqual(setup.status()["state"], "idle")
        self.assertEqual(setup.start(), {"state": "ready", "message": "Voice is set up. Tap the shield and say a command."})
        self.assertIn(("POST", "http://supervisor/store/addons/core_speech-to-phrase/install"), home.calls)
        self.assertIn(("POST", "http://supervisor/addons/core_speech-to-phrase/start"), home.calls)
        self.assertTrue(home.flow_confirmed)
        self.assertEqual(home.update["pipeline_id"], "01pipeline")
        self.assertEqual(home.update["stt_engine"], "stt.speech_to_phrase")
        self.assertEqual(home.update["stt_language"], "en")
        # Everything else in the pipeline is sent back unchanged.
        self.assertEqual(home.update["tts_engine"], "tts.piper")
        self.assertEqual(home.update["prefer_local_intents"], True)
        self.assertNotIn("id", home.update)
        self.assertEqual(setup.status()["state"], "ready")

    def test_already_installed_and_connected_only_changes_the_pipeline(self):
        home = FakeSupervisor(installed=True, started=True)
        home.flow_confirmed = True
        home.setup().start()
        self.assertEqual([call for call in home.calls if call[0] == "POST"], [])
        self.assertEqual(home.pipeline["stt_engine"], "stt.speech_to_phrase")

    def test_without_the_manager_role_it_asks_for_the_stable_update(self):
        home = FakeSupervisor(role=False)
        result = home.setup().start()
        self.assertEqual(result["state"], "needs_update")
        self.assertIn("next Stable update", result["message"])
        self.assertIsNone(home.pipeline["stt_engine"])

    def test_connection_that_never_appears_fails_with_a_retry_message(self):
        home = FakeSupervisor(entity_after_flow=False)
        result = home.setup().start()
        self.assertEqual(result["state"], "failed")
        self.assertIn("Try again", result["message"])
        self.assertIsNone(home.pipeline["stt_engine"])

    def test_missing_speech_to_text_is_marked_for_setup(self):
        assistant = VOICE.VoiceAssistant("token", lambda commands: [{**PIPELINE, "stt_engine": None}])
        with self.assertRaises(VOICE.VoiceCommandError) as caught:
            assistant.command(audio=b"\x00\x00")
        self.assertTrue(caught.exception.setup)


class VoiceSetupRouteTests(unittest.TestCase):
    def test_get_reports_and_post_starts(self):
        handler = SERVER.FutureHomesTechRequestHandler.__new__(SERVER.FutureHomesTechRequestHandler)
        handler.path = "/api/voice/setup"
        handler.voice_setup = Mock()
        handler.voice_setup.status.return_value = {"state": "idle", "message": "Voice needs speech-to-text."}
        handler.voice_setup.start.return_value = {"state": "working", "message": "Installing Speech-to-Phrase…"}
        handler._send_json = Mock()
        handler._dispatch_POST()
        self.assertEqual(handler._send_json.call_args.args, (200, {"ok": True, "state": "working", "message": "Installing Speech-to-Phrase…"}))
        handler._voice_setup(start=False)
        self.assertEqual(handler._send_json.call_args.args, (200, {"ok": True, "state": "idle", "message": "Voice needs speech-to-text."}))

    def test_voice_errors_say_when_setup_can_fix_them(self):
        handler = VoiceRouteTests.handler(None, "application/octet-stream", b"\x01\x02")
        handler.voice_assistant.command.side_effect = VOICE.VoiceCommandError("Voice isn't set up yet.", setup=True)
        handler._dispatch_POST()
        self.assertEqual(handler._send_json.call_args.args, (200, {"ok": False, "error": "Voice isn't set up yet.", "setup": True}))

    def test_app_has_the_manager_role(self):
        config = (Path(SERVER.__file__).with_name("config.yaml")).read_text(encoding="utf-8")
        self.assertIn("\nhassio_role: manager\n", config)


if __name__ == "__main__":
    unittest.main()
