from __future__ import annotations

import importlib
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from PySide6.QtCore import QThread, Signal

from live_captions.audio import (
    STEREO_SOURCES,
    AudioMode,
    AudioSource,
    LoopbackAudioCapture,
    MicrophoneCapture,
    MixedAudioCapture,
    create_audio_capture,
    single_source,
    split_stereo_pcm,
)
from live_captions.config import Settings

WHISPER_SAMPLE_RATE = 16_000
WINDOW_SECONDS = 5.0
STEP_SECONDS = 3.0
MIN_AUDIO_SECONDS = 1.0
SILENCE_RMS = 0.004
MAX_PROMPT_CHARS = 400


def pcm48k_to_float16k(pcm: bytes) -> np.ndarray:
    """Convert mono linear16 PCM from 48 kHz to float32 at 16 kHz."""
    source = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
    if source.size == 0:
        return source
    if source.size % 3:
        source = source[: source.size - (source.size % 3)]
    if source.size == 0:
        return source
    return source.reshape(-1, 3).mean(axis=1).astype(np.float32, copy=False)


def trim_overlap(previous: str, current: str, max_words: int = 24) -> str:
    """Remove the longest confirmed prefix between overlapping windows."""
    previous_words = previous.split()
    current_words = current.split()
    max_overlap = min(len(previous_words), len(current_words), max_words)
    for size in range(max_overlap, 0, -1):
        left = [word.casefold().strip(".,!?;:") for word in previous_words[-size:]]
        right = [word.casefold().strip(".,!?;:") for word in current_words[:size]]
        if left == right:
            return " ".join(current_words[size:])
    return current.strip()


@dataclass(slots=True)
class _SourceState:
    """Sliding-window state kept independently for each audio source."""

    chunks: list[np.ndarray] = field(default_factory=list)
    buffered: int = 0
    since_run: int = 0
    last_text: str = ""


class WhisperTranscriptionThread(QThread):
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

    _AUDIO_MODE_LABELS = {
        AudioMode.COMPUTER: "Local Whisper • audio stays on this computer",
        AudioMode.MICROPHONE: "Local Whisper • capturing microphone",
        AudioMode.BOTH: "Local Whisper • computer + microphone",
    }

    def run(self) -> None:
        self._stop_event.clear()
        audio: LoopbackAudioCapture | MicrophoneCapture | MixedAudioCapture | None = None
        try:
            model = self._load_model(self._settings.whisper_model_path)
            if self._stop_event.is_set():
                return
            audio = create_audio_capture(
                mode=self._audio_mode,
                sample_rate=self._settings.sample_rate,
                frames_per_chunk=self._settings.frames_per_chunk,
            )
            audio.start()
            self.status_changed.emit(self._AUDIO_MODE_LABELS.get(self._audio_mode, "Local Whisper"))
            self._transcribe_stream(model, audio)
        except Exception as exc:
            self.issue_detected.emit(self._friendly_error(exc))
        finally:
            if audio is not None:
                audio.stop()
            self.status_changed.emit("Paused")

    def _load_model(self, model_path: Path) -> Any:
        if not model_path.is_file():
            raise FileNotFoundError(str(model_path))
        self.status_changed.emit("Loading the local Whisper model…")
        whisper = importlib.import_module("whisper")
        return whisper.load_model(str(model_path), device="cpu")

    def _transcribe_stream(
        self,
        model: Any,
        audio: LoopbackAudioCapture | MicrophoneCapture | MixedAudioCapture,
    ) -> None:
        stereo = self._audio_mode is AudioMode.BOTH
        sources = STEREO_SOURCES if stereo else (single_source(self._audio_mode),)
        states = {source: _SourceState() for source in sources}

        while not self._stop_event.is_set():
            chunk = audio.read(timeout=0.25)
            if not chunk:
                continue
            if stereo:
                # Interleaved stereo: left = computer, right = microphone.
                pcm_by_source = dict(zip(STEREO_SOURCES, split_stereo_pcm(chunk)))
            else:
                pcm_by_source = {sources[0]: chunk}
            for source, pcm in pcm_by_source.items():
                self._feed(model, source, states[source], pcm)

    def _feed(self, model: Any, source: AudioSource, state: _SourceState, pcm: bytes) -> None:
        window_samples = int(WINDOW_SECONDS * WHISPER_SAMPLE_RATE)
        step_samples = int(STEP_SECONDS * WHISPER_SAMPLE_RATE)
        minimum_samples = int(MIN_AUDIO_SECONDS * WHISPER_SAMPLE_RATE)

        samples = pcm48k_to_float16k(pcm)
        if samples.size == 0:
            return
        state.chunks.append(samples)
        state.buffered += samples.size
        state.since_run += samples.size

        if state.buffered < minimum_samples or state.since_run < step_samples:
            return

        window = np.concatenate(state.chunks)
        if window.size > window_samples:
            window = window[-window_samples:]
        self._transcribe_window(model, source, state, window)
        state.since_run = 0

        retained = window[-window_samples:]
        state.chunks = [retained]
        state.buffered = retained.size

    def _transcribe_window(self, model: Any, source: AudioSource, state: _SourceState, audio: np.ndarray) -> None:
        if float(np.sqrt(np.mean(np.square(audio)))) < SILENCE_RMS:
            return
        started = time.monotonic()
        result = model.transcribe(
            audio,
            language=self._language,
            task="transcribe",
            fp16=False,
            temperature=0,
            condition_on_previous_text=False,
            initial_prompt=state.last_text[-MAX_PROMPT_CHARS:] or None,
            verbose=False,
        )
        text = " ".join(str(result.get("text", "")).split())
        if not text:
            return
        new_text = trim_overlap(state.last_text, text)
        state.last_text = text
        if new_text:
            self.transcript_received.emit(new_text, True, source.value)
        elapsed = time.monotonic() - started
        self.status_changed.emit(f"Local Whisper • processed in {elapsed:.1f}s")

    @staticmethod
    def _friendly_error(exc: Exception) -> str:
        if isinstance(exc, FileNotFoundError):
            return "Whisper model not found. Check models/small.pt."
        if isinstance(exc, ModuleNotFoundError):
            return "OpenAI Whisper is not installed. Reinstall the dependencies."
        message = str(exc).strip()
        lowered = message.casefold()
        if "loopback" in lowered or "device" in lowered:
            return message
        return message or exc.__class__.__name__
