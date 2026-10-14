from __future__ import annotations

import asyncio
import json
import threading
from contextlib import suppress
from urllib.parse import urlencode

from PySide6.QtCore import QThread, Signal
from websockets.asyncio.client import ClientConnection, connect

from live_captions.audio import STEREO_SOURCES, AudioMode, create_audio_capture, single_source
from live_captions.config import Settings


class DeepgramTranscriptionThread(QThread):
    transcript_received = Signal(str, bool, str)  # text, is_final, source
    status_changed = Signal(str)
    issue_detected = Signal(str)

    def __init__(self, settings: Settings, language: str, audio_mode: AudioMode = AudioMode.COMPUTER) -> None:
        super().__init__()
        self._settings = settings
        self._language = language
        self._audio_mode = audio_mode
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        self._stop_event.clear()
        try:
            asyncio.run(self._run_with_reconnect())
        except Exception as exc:  # Safety boundary for the Qt thread.
            self.issue_detected.emit(self._friendly_error(exc))
        finally:
            self.status_changed.emit("Paused")

    async def _run_with_reconnect(self) -> None:
        attempt = 0
        while not self._stop_event.is_set():
            try:
                await self._stream_once()
                if not self._stop_event.is_set():
                    raise ConnectionError("The Deepgram connection was closed.")
            except Exception as exc:
                if self._stop_event.is_set():
                    break
                attempt += 1
                delay = min(2 ** min(attempt - 1, 3), 8)
                self.issue_detected.emit(self._friendly_error(exc))
                self.status_changed.emit(f"Reconnecting in {delay}s…")
                await self._wait_or_stop(delay)
            else:
                attempt = 0

    async def _wait_or_stop(self, seconds: float) -> None:
        elapsed = 0.0
        while elapsed < seconds and not self._stop_event.is_set():
            await asyncio.sleep(0.1)
            elapsed += 0.1

    def _websocket_url(self) -> str:
        both = self._audio_mode is AudioMode.BOTH
        params = {
            "model": "nova-3",
            "language": self._language,
            "encoding": "linear16",
            "sample_rate": str(self._settings.sample_rate),
            "channels": "2" if both else "1",
            "interim_results": "true",
            "punctuate": "true",
            "smart_format": "true",
            "endpointing": "300",
            "utterance_end_ms": "1000",
            "vad_events": "true",
        }
        if both:
            # One channel per source: 0 = computer, 1 = microphone.
            params["multichannel"] = "true"
        return f"wss://api.deepgram.com/v1/listen?{urlencode(params)}"

    _AUDIO_MODE_LABELS = {
        AudioMode.COMPUTER: "Capturing computer audio",
        AudioMode.MICROPHONE: "Capturing microphone audio",
        AudioMode.BOTH: "Capturing computer + microphone audio",
    }

    async def _stream_once(self) -> None:
        self.status_changed.emit("Connecting to Deepgram…")
        if not self._settings.api_key:
            raise RuntimeError("DEEPGRAM_API_KEY is not configured in .env.")
        headers = {"Authorization": f"Token {self._settings.api_key}"}
        audio = create_audio_capture(
            mode=self._audio_mode,
            sample_rate=self._settings.sample_rate,
            frames_per_chunk=self._settings.frames_per_chunk,
        )

        async with connect(
            self._websocket_url(),
            additional_headers=headers,
            max_size=None,
            ping_interval=20,
            ping_timeout=20,
            open_timeout=15,
        ) as websocket:
            audio.start()
            self.status_changed.emit(self._AUDIO_MODE_LABELS.get(self._audio_mode, "Capturing audio"))
            receiver = asyncio.create_task(self._receive_results(websocket))
            try:
                while not self._stop_event.is_set():
                    if receiver.done():
                        await receiver
                        return
                    chunk = await asyncio.to_thread(audio.read, 0.25)
                    if chunk:
                        await websocket.send(chunk)

                with suppress(Exception):
                    await websocket.send(json.dumps({"type": "Finalize"}))
                    await asyncio.sleep(0.25)
                    await websocket.send(json.dumps({"type": "CloseStream"}))
                with suppress(Exception, asyncio.TimeoutError):
                    await asyncio.wait_for(receiver, timeout=1.5)
            finally:
                audio.stop()
                if not receiver.done():
                    receiver.cancel()
                    with suppress(asyncio.CancelledError):
                        await receiver

    async def _receive_results(self, websocket: ClientConnection) -> None:
        async for raw_message in websocket:
            if isinstance(raw_message, bytes):
                continue
            try:
                message = json.loads(raw_message)
            except json.JSONDecodeError:
                continue

            if message.get("type") != "Results":
                continue
            alternatives = message.get("channel", {}).get("alternatives", [])
            if not alternatives:
                continue
            text = alternatives[0].get("transcript", "").strip()
            is_final = bool(message.get("is_final"))
            if self._audio_mode is AudioMode.BOTH:
                channel = (message.get("channel_index") or [0])[0]
                source = STEREO_SOURCES[1 if channel == 1 else 0]
            else:
                source = single_source(self._audio_mode)
            # An empty final still matters: it clears that source's interim text.
            if text or is_final:
                self.transcript_received.emit(text, is_final, source.value)

    @staticmethod
    def _friendly_error(exc: Exception) -> str:
        message = str(exc).strip()
        lowered = message.casefold()
        if "401" in lowered or "unauthorized" in lowered:
            return "Deepgram rejected the API key. Check the .env file."
        if "403" in lowered or "forbidden" in lowered:
            return "The API key cannot access real-time transcription."
        if "loopback" in lowered or "device" in lowered:
            return message
        if "getaddrinfo" in lowered or "name resolution" in lowered:
            return "No internet access, or Deepgram could not be reached."
        return message or exc.__class__.__name__
