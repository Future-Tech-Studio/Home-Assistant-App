"""Voice commands: speech to text and Assist through Home Assistant.

The page records 16 kHz mono 16-bit PCM and posts it here. This module asks
Home Assistant for the preferred Assist pipeline, sends the audio to that
pipeline's speech-to-text engine, and hands the text to the pipeline's
conversation agent, so the App follows whatever voice setup the home uses
(Speech-to-Phrase, Whisper or Home Assistant Cloud).
"""

from __future__ import annotations

import json
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

DEFAULT_CORE_API_URL = "http://supervisor/core/api"
SAMPLE_RATE = 16000
# Twenty seconds of 16 kHz 16-bit mono audio.
MAX_AUDIO_BYTES = SAMPLE_RATE * 2 * 20
MAX_TEXT_LENGTH = 500


class VoiceCommandError(Exception):
    """A voice command could not be understood or run; the text is for people."""


class VoiceAssistant:
    """Turn recorded speech or typed text into an Assist command."""

    def __init__(
        self,
        token: str,
        run_commands: Callable[[list[dict[str, Any]]], list[Any]],
        core_api_url: str = DEFAULT_CORE_API_URL,
        opener: Callable[..., Any] = urlopen,
    ) -> None:
        self._token = token
        self._run_commands = run_commands
        self._core_api_url = core_api_url.rstrip("/")
        self._opener = opener

    def pipeline(self) -> dict[str, Any]:
        """Return Home Assistant's preferred Assist pipeline."""
        try:
            result = self._run_commands([{"type": "assist_pipeline/pipeline/get"}])[0]
        except Exception as err:
            raise VoiceCommandError(
                "Home Assistant's voice assistant is unavailable."
            ) from err
        if not isinstance(result, dict):
            raise VoiceCommandError("Home Assistant has no voice assistant set up.")
        return result

    @staticmethod
    def _language(pipeline: dict[str, Any], key: str) -> str:
        return str(pipeline.get(key) or pipeline.get("language") or "en")

    def transcribe(self, audio: bytes, pipeline: dict[str, Any]) -> str:
        """Return the text Home Assistant heard in raw 16 kHz PCM audio."""
        engine = str(pipeline.get("stt_engine") or "")
        if not engine:
            raise VoiceCommandError(
                "Your Assist voice setup has no speech-to-text. "
                "Type the command, or add Speech-to-Phrase in Home Assistant."
            )
        if not audio:
            raise VoiceCommandError("No sound was recorded.")
        if len(audio) > MAX_AUDIO_BYTES:
            raise VoiceCommandError("That recording was too long.")
        language = self._language(pipeline, "stt_language")
        request = Request(
            f"{self._core_api_url}/stt/{quote(engine, safe='._')}",
            data=audio,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/octet-stream",
                "Accept": "application/json",
                # Home Assistant's own pipeline labels raw PCM this way.
                "X-Speech-Content": (
                    f"format=wav; codec=pcm; sample_rate={SAMPLE_RATE}; "
                    f"bit_rate=16; channel=1; language={language}"
                ),
            },
            method="POST",
        )
        try:
            with self._opener(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8") or "{}")
        except (HTTPError, URLError, OSError, ValueError) as err:
            raise VoiceCommandError(
                "Home Assistant couldn't turn that into text."
            ) from err
        text = str((payload or {}).get("text") or "").strip()
        if (payload or {}).get("result") != "success" or not text:
            raise VoiceCommandError("Sorry, I didn't catch that.")
        return text

    def converse(self, text: str, pipeline: dict[str, Any]) -> dict[str, Any]:
        """Run text through the pipeline's conversation agent."""
        command: dict[str, Any] = {
            "type": "conversation/process",
            "text": text,
            "language": self._language(pipeline, "conversation_language"),
        }
        if pipeline.get("conversation_engine"):
            command["agent_id"] = str(pipeline["conversation_engine"])
        try:
            result = self._run_commands([command])[0]
        except Exception as err:
            raise VoiceCommandError(
                "Home Assistant's voice assistant is unavailable."
            ) from err
        response = (result or {}).get("response") or {}
        speech = str(
            ((response.get("speech") or {}).get("plain") or {}).get("speech") or ""
        ).strip()
        response_type = str(response.get("response_type") or "")
        return {
            "reply": speech or ("Done." if response_type == "action_done" else ""),
            "success": response_type in {"action_done", "query_answer"},
        }

    def command(self, audio: bytes | None = None, text: str | None = None) -> dict[str, Any]:
        """Run one voice or typed command and return what was heard and done."""
        pipeline = self.pipeline()
        if audio is not None:
            text = self.transcribe(audio, pipeline)
        text = " ".join(str(text or "").split())
        if not text:
            raise VoiceCommandError("Say or type a command.")
        if len(text) > MAX_TEXT_LENGTH:
            raise VoiceCommandError("That command is too long.")
        return {"transcript": text, **self.converse(text, pipeline)}
