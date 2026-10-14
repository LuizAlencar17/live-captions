from __future__ import annotations

import enum
import queue
import threading
from collections.abc import Sequence

import numpy as np
import soundcard as sc

AudioItem = bytes | Exception


class AudioMode(enum.Enum):
    """Which audio sources to capture."""

    COMPUTER = "computer"
    MICROPHONE = "microphone"
    BOTH = "both"


class AudioSource(enum.Enum):
    """Where a piece of audio (and its transcript) came from."""

    COMPUTER = "computer"
    MICROPHONE = "microphone"


# Channel order of the stereo stream produced by MixedAudioCapture:
# left = computer output, right = microphone.
STEREO_SOURCES = (AudioSource.COMPUTER, AudioSource.MICROPHONE)


def single_source(mode: AudioMode) -> AudioSource:
    """Source label for the single-source modes (COMPUTER / MICROPHONE)."""
    return AudioSource.MICROPHONE if mode is AudioMode.MICROPHONE else AudioSource.COMPUTER


def split_stereo_pcm(pcm: bytes) -> tuple[bytes, bytes]:
    """Split interleaved stereo linear16 PCM into (left, right) mono PCM."""
    data = np.frombuffer(pcm, dtype="<i2")
    if data.size % 2:
        data = data[:-1]
    frames = data.reshape(-1, 2)
    return frames[:, 0].tobytes(), frames[:, 1].tobytes()


# ---------------------------------------------------------------------------
# Helper: push an item to a bounded queue, dropping the oldest if full
# ---------------------------------------------------------------------------

def _safe_put(q: queue.Queue[AudioItem], item: AudioItem) -> None:
    try:
        q.put_nowait(item)
    except queue.Full:
        try:
            q.get_nowait()
        except queue.Empty:
            pass
        q.put_nowait(item)


def _normalized(value: object) -> str:
    return " ".join(str(value).casefold().split())


def _find_loopback(sample_rate: int | None = None) -> sc.Microphone:
    speaker = sc.default_speaker()
    if speaker is None:
        raise RuntimeError("No default audio output device was found.")

    speaker_name = _normalized(speaker.name)
    microphones: Sequence[sc.Microphone] = sc.all_microphones(include_loopback=True)
    candidates = [m for m in microphones if getattr(m, "isloopback", False)]

    for microphone in candidates:
        microphone_name = _normalized(microphone.name)
        if speaker_name == microphone_name or speaker_name in microphone_name:
            return microphone

    for identifier in (getattr(speaker, "id", None), speaker.name):
        if identifier is None:
            continue
        try:
            return sc.get_microphone(id=str(identifier), include_loopback=True)
        except (RuntimeError, IndexError):
            continue

    if candidates:
        return candidates[0]
    raise RuntimeError("The WASAPI loopback device was not found.")


def _samples_to_mono_pcm(samples: np.ndarray) -> tuple[np.ndarray, bytes]:
    """Convert raw recorder output to (mono float32, linear16 PCM bytes)."""
    audio = np.asarray(samples, dtype=np.float32)
    if audio.ndim == 2:
        audio = audio.mean(axis=1)
    audio = np.clip(audio, -1.0, 1.0)
    pcm = (audio * 32767.0).astype("<i2", copy=False).tobytes()
    return audio, pcm


# ---------------------------------------------------------------------------
# LoopbackAudioCapture — captures computer output (unchanged interface)
# ---------------------------------------------------------------------------

class LoopbackAudioCapture:
    """Capture the default output device through WASAPI loopback."""

    def __init__(self, sample_rate: int, frames_per_chunk: int) -> None:
        self.sample_rate = sample_rate
        self.frames_per_chunk = frames_per_chunk
        self._queue: queue.Queue[AudioItem] = queue.Queue(maxsize=32)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._capture_loop,
            name="wasapi-loopback",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def read(self, timeout: float = 0.25) -> bytes | None:
        try:
            item = self._queue.get(timeout=timeout)
        except queue.Empty:
            return None
        if isinstance(item, Exception):
            raise item
        return item

    def _capture_loop(self) -> None:
        try:
            loopback = _find_loopback()
            with loopback.recorder(samplerate=self.sample_rate) as recorder:
                while not self._stop_event.is_set():
                    samples = recorder.record(numframes=self.frames_per_chunk)
                    _, pcm = _samples_to_mono_pcm(samples)
                    _safe_put(self._queue, pcm)
        except Exception as exc:  # Propagate to the transcription thread.
            _safe_put(self._queue, exc)


# ---------------------------------------------------------------------------
# MicrophoneCapture — captures from the default microphone
# ---------------------------------------------------------------------------

class MicrophoneCapture:
    """Capture audio from the default microphone input."""

    def __init__(self, sample_rate: int, frames_per_chunk: int) -> None:
        self.sample_rate = sample_rate
        self.frames_per_chunk = frames_per_chunk
        self._queue: queue.Queue[AudioItem] = queue.Queue(maxsize=32)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._capture_loop,
            name="microphone-capture",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def read(self, timeout: float = 0.25) -> bytes | None:
        try:
            item = self._queue.get(timeout=timeout)
        except queue.Empty:
            return None
        if isinstance(item, Exception):
            raise item
        return item

    def _capture_loop(self) -> None:
        try:
            mic = sc.default_microphone()
            if mic is None:
                raise RuntimeError("No default microphone was found.")
            with mic.recorder(samplerate=self.sample_rate) as recorder:
                while not self._stop_event.is_set():
                    samples = recorder.record(numframes=self.frames_per_chunk)
                    _, pcm = _samples_to_mono_pcm(samples)
                    _safe_put(self._queue, pcm)
        except Exception as exc:
            _safe_put(self._queue, exc)


# ---------------------------------------------------------------------------
# MixedAudioCapture — mixes loopback + microphone into a single stream
# ---------------------------------------------------------------------------

class MixedAudioCapture:
    """Capture computer output AND microphone input as ONE stereo PCM stream.

    Channels are kept separate (left = computer, right = microphone) so the
    transcription engines can tell which source each phrase came from.
    """

    def __init__(self, sample_rate: int, frames_per_chunk: int) -> None:
        self.sample_rate = sample_rate
        self.frames_per_chunk = frames_per_chunk
        self._out_queue: queue.Queue[AudioItem] = queue.Queue(maxsize=32)
        self._loop_queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=16)
        self._mic_queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=16)
        self._stop_event = threading.Event()
        self._threads: list[threading.Thread] = []

    def start(self) -> None:
        if any(t.is_alive() for t in self._threads):
            return
        self._stop_event.clear()
        self._threads = [
            threading.Thread(target=self._record_loopback, name="mixed-loopback", daemon=True),
            threading.Thread(target=self._record_mic, name="mixed-mic", daemon=True),
            threading.Thread(target=self._mixer, name="mixed-mixer", daemon=True),
        ]
        for t in self._threads:
            t.start()

    def stop(self) -> None:
        self._stop_event.set()
        for t in self._threads:
            if t.is_alive():
                t.join(timeout=2.0)

    def read(self, timeout: float = 0.25) -> bytes | None:
        try:
            item = self._out_queue.get(timeout=timeout)
        except queue.Empty:
            return None
        if isinstance(item, Exception):
            raise item
        return item

    # --- internal recording threads ---

    def _record_stream(self, device: sc.Microphone, target: queue.Queue[np.ndarray]) -> None:
        with device.recorder(samplerate=self.sample_rate) as recorder:
            while not self._stop_event.is_set():
                samples = recorder.record(numframes=self.frames_per_chunk)
                audio = np.asarray(samples, dtype=np.float32)
                if audio.ndim == 2:
                    audio = audio.mean(axis=1)
                try:
                    target.put_nowait(audio)
                except queue.Full:
                    try:
                        target.get_nowait()
                    except queue.Empty:
                        pass
                    target.put_nowait(audio)

    def _record_loopback(self) -> None:
        try:
            loopback = _find_loopback()
            self._record_stream(loopback, self._loop_queue)
        except Exception as exc:
            _safe_put(self._out_queue, exc)

    def _record_mic(self) -> None:
        try:
            mic = sc.default_microphone()
            if mic is None:
                raise RuntimeError("No default microphone was found.")
            self._record_stream(mic, self._mic_queue)
        except Exception as exc:
            _safe_put(self._out_queue, exc)

    def _mixer(self) -> None:
        """Read from both internal queues, mix, and produce PCM output."""
        try:
            while not self._stop_event.is_set():
                loop_data: np.ndarray | None = None
                mic_data: np.ndarray | None = None

                try:
                    loop_data = self._loop_queue.get(timeout=0.15)
                except queue.Empty:
                    pass

                try:
                    mic_data = self._mic_queue.get(timeout=0.15)
                except queue.Empty:
                    pass

                if loop_data is None and mic_data is None:
                    continue

                n = min(len(x) for x in (loop_data, mic_data) if x is not None)
                left = loop_data[:n] if loop_data is not None else np.zeros(n, dtype=np.float32)
                right = mic_data[:n] if mic_data is not None else np.zeros(n, dtype=np.float32)
                stereo = np.clip(np.stack((left, right), axis=1), -1.0, 1.0)
                pcm = (stereo * 32767.0).astype("<i2").tobytes()  # interleaved L,R
                _safe_put(self._out_queue, pcm)
        except Exception as exc:
            _safe_put(self._out_queue, exc)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_audio_capture(
    mode: AudioMode,
    sample_rate: int,
    frames_per_chunk: int,
) -> LoopbackAudioCapture | MicrophoneCapture | MixedAudioCapture:
    """Create the appropriate audio capture object for *mode*."""
    if mode is AudioMode.MICROPHONE:
        return MicrophoneCapture(sample_rate, frames_per_chunk)
    if mode is AudioMode.BOTH:
        return MixedAudioCapture(sample_rate, frames_per_chunk)
    return LoopbackAudioCapture(sample_rate, frames_per_chunk)
