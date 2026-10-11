"""Voice commands: speech to text and Assist through Home Assistant.

The page records 16 kHz mono 16-bit PCM and posts it here. This module asks
Home Assistant for the preferred Assist pipeline, sends the audio to that
pipeline's speech-to-text engine, and hands the text to the pipeline's
conversation agent, so the App follows whatever voice setup the home uses
(Speech-to-Phrase, Whisper or Home Assistant Cloud).
"""

from __future__ import annotations

import json
import threading
import time
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
    """A voice command could not be understood or run; the text is for people.

    ``setup`` marks errors the Set up voice button can fix.
    """

    def __init__(self, message: str, setup: bool = False) -> None:
        super().__init__(message)
        self.setup = setup


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
                "Voice isn't set up yet. Tap Set up voice, or type the command.",
                setup=True,
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


SPEECH_TO_PHRASE_SLUG = "core_speech-to-phrase"
DEFAULT_SUPERVISOR_URL = "http://supervisor"


class VoiceSetup:
    """Install Speech-to-Phrase and make it Assist's speech-to-text.

    Runs in the background because Supervisor takes a minute or two to
    install an add-on. Each step checks first, so pressing the button again
    picks up wherever the last try stopped. Installing needs the App's
    ``hassio_role: manager``; without it Supervisor answers 403.
    """

    DISCOVERY_WAIT_SECONDS = 180

    def __init__(
        self,
        token: str,
        run_commands: Callable[[list[dict[str, Any]]], list[Any]],
        supervisor_url: str = DEFAULT_SUPERVISOR_URL,
        core_api_url: str = DEFAULT_CORE_API_URL,
        opener: Callable[..., Any] = urlopen,
        sleep: Callable[[float], None] | None = None,
        start_thread: Callable[[Callable[[], None]], None] | None = None,
    ) -> None:
        self._token = token
        self._run_commands = run_commands
        self._supervisor_url = supervisor_url.rstrip("/")
        self._core_api_url = core_api_url.rstrip("/")
        self._opener = opener
        self._sleep = sleep or time.sleep
        self._start_thread = start_thread or (
            lambda target: threading.Thread(target=target, name="fht-voice-setup", daemon=True).start()
        )
        self._lock = threading.Lock()
        self._state: dict[str, Any] = {"state": "idle", "message": ""}

    def _request(self, url: str, payload: dict[str, Any] | None = None, timeout: float = 30) -> Any:
        request = Request(
            url,
            data=None if payload is None else json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="GET" if payload is None else "POST",
        )
        with self._opener(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8") or "null")

    def _set(self, state: str, message: str) -> None:
        with self._lock:
            self._state = {"state": state, "message": message}

    def status(self) -> dict[str, Any]:
        """Return the background setup's progress, or whether voice is ready."""
        with self._lock:
            if self._state["state"] in {"working", "failed", "needs_update", "ready"}:
                return dict(self._state)
        try:
            pipeline = self._run_commands([{"type": "assist_pipeline/pipeline/get"}])[0] or {}
        except Exception:
            return {"state": "unknown", "message": "Home Assistant's voice assistant is unavailable."}
        if pipeline.get("stt_engine"):
            return {"state": "ready", "message": "Voice is set up."}
        return {"state": "idle", "message": "Voice needs speech-to-text."}

    def start(self) -> dict[str, Any]:
        """Start setting up voice in the background, unless it already runs."""
        with self._lock:
            if self._state["state"] == "working":
                return dict(self._state)
            self._state = {"state": "working", "message": "Getting voice ready…"}
        self._start_thread(self._run)
        return self.status()

    def _run(self) -> None:
        try:
            self._install_and_start()
            entity_id = self._stt_entity() or self._confirm_discovery()
            self._use_in_pipeline(entity_id)
        except _NeedsUpdate:
            self._set(
                "needs_update",
                "The App needs its next Stable update before it can set up voice. "
                "Until then, install Speech-to-Phrase from Home Assistant's add-on store.",
            )
            return
        except VoiceCommandError as err:
            self._set("failed", str(err))
            return
        except Exception as err:  # noqa: BLE001 - shown to people, not raised
            print(f"[Voice] WARNING setup failed: {err}", flush=True)
            self._set("failed", "Voice setup didn't finish. Try again.")
            return
        self._set("ready", "Voice is set up. Tap the shield and say a command.")

    def _install_and_start(self) -> None:
        base = f"{self._supervisor_url}/addons/{SPEECH_TO_PHRASE_SLUG}"
        try:
            info = (self._request(f"{base}/info") or {}).get("data") or {}
        except HTTPError as err:
            if err.code == 403:
                raise _NeedsUpdate() from err
            if err.code not in {400, 404}:
                raise
            info = {}
        if not info.get("version"):
            self._set("working", "Installing Speech-to-Phrase… this takes a minute or two.")
            try:
                self._request(f"{self._supervisor_url}/store/addons/{SPEECH_TO_PHRASE_SLUG}/install", {}, timeout=900)
            except HTTPError as err:
                if err.code == 403:
                    raise _NeedsUpdate() from err
                raise VoiceCommandError("Home Assistant couldn't install Speech-to-Phrase.") from err
            info = {}
        if info.get("state") != "started":
            self._set("working", "Starting Speech-to-Phrase…")
            self._request(f"{base}/start", {}, timeout=120)

    def _stt_entity(self) -> str:
        states = self._request(f"{self._core_api_url}/states") or []
        candidates = sorted(
            str(state.get("entity_id") or "")
            for state in states
            if str(state.get("entity_id") or "").startswith("stt.")
        )
        return next((entity_id for entity_id in candidates if "phrase" in entity_id), "")

    def _confirm_discovery(self) -> str:
        """Accept Home Assistant's 'Speech-to-Phrase was found' prompt for the user."""
        self._set("working", "Connecting Speech-to-Phrase to Home Assistant…")
        for _attempt in range(int(self.DISCOVERY_WAIT_SECONDS / 5)):
            flows = self._run_commands([{"type": "config_entries/flow/progress"}])[0] or []
            for flow in flows:
                if flow.get("handler") == "wyoming" and (flow.get("context") or {}).get("source") == "hassio":
                    self._request(f"{self._core_api_url}/config/config_entries/flow/{flow['flow_id']}", {})
            self._sleep(5)
            entity_id = self._stt_entity()
            if entity_id:
                return entity_id
        raise VoiceCommandError("Speech-to-Phrase started, but Home Assistant hasn't connected to it yet. Try again in a minute.")

    def _use_in_pipeline(self, entity_id: str) -> None:
        pipeline = self._run_commands([{"type": "assist_pipeline/pipeline/get"}])[0] or {}
        if pipeline.get("stt_engine"):
            return
        language = str(pipeline.get("language") or "en")
        fields = (
            "conversation_engine", "conversation_language", "language", "name",
            "tts_engine", "tts_language", "tts_voice", "wake_word_entity", "wake_word_id",
            "prefer_local_intents",
        )
        update = {key: pipeline[key] for key in fields if key in pipeline}
        self._set("working", "Turning on speech-to-text in Assist…")
        self._run_commands([{
            "type": "assist_pipeline/pipeline/update",
            "pipeline_id": pipeline["id"],
            **update,
            "stt_engine": entity_id,
            "stt_language": language.split("-")[0],
        }])


class _NeedsUpdate(Exception):
    """Supervisor refused: the installed App lacks the manager role."""
