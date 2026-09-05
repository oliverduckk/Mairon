from __future__ import annotations

import re
import threading
from typing import Callable, Optional

import numpy as np
import sounddevice as sd

from voice.stt import (
    CHANNELS,
    SAMPLE_RATE,
    load_model,
    transcribe_audio,
)
from voice.tts import (
    load_tts,
    speak,
)


def normalise_voice_input(
    text: str,
) -> str:
    """
    Apply only the established conservative Mairon-name correction.
    """

    value = str(
        text
        or ""
    ).strip()

    if not value:
        return ""

    return re.sub(
        r"\b(myron|miron|mayron|mairon)\b",
        "Mairon",
        value,
        flags=re.IGNORECASE,
    )


class PushToTalkRecorder:
    """
    GUI-safe push-to-talk recorder.

    Recording starts/stops from button events rather than console input.
    Audio remains in memory and is returned as float32 mono samples.
    """

    def __init__(
        self,
    ):
        self._lock = (
            threading.Lock()
        )

        self._stream = None
        self._chunks = []
        self._recording = False

    @property
    def recording(
        self,
    ) -> bool:
        return bool(
            self._recording
        )

    def _callback(
        self,
        indata,
        frames,
        time_info,
        status,
    ) -> None:
        if not self._recording:
            return

        with self._lock:
            self._chunks.append(
                indata.copy()
            )

    def start(
        self,
    ) -> None:
        if self._recording:
            raise RuntimeError(
                "Voice recording is already active."
            )

        with self._lock:
            self._chunks = []

        stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="float32",
            callback=self._callback,
        )

        try:
            self._recording = True
            stream.start()

        except Exception as exc:
            self._recording = False

            try:
                stream.close()

            except Exception:
                pass

            raise RuntimeError(
                "Microphone recording failed: "
                + str(
                    exc
                )
            ) from exc

        self._stream = stream

    def stop(
        self,
    ) -> np.ndarray:
        if not self._recording:
            raise RuntimeError(
                "Voice recording is not active."
            )

        self._recording = False

        stream = self._stream
        self._stream = None

        if stream is not None:
            try:
                stream.stop()

            finally:
                stream.close()

        with self._lock:
            chunks = list(
                self._chunks
            )

            self._chunks = []

        if not chunks:
            raise RuntimeError(
                "No microphone audio was captured."
            )

        audio = np.concatenate(
            chunks,
            axis=0,
        )

        return (
            audio.reshape(
                -1
            )
            .astype(
                np.float32
            )
        )

    def cancel(
        self,
    ) -> None:
        self._recording = False

        stream = self._stream
        self._stream = None

        if stream is not None:
            try:
                stream.stop()

            except Exception:
                pass

            try:
                stream.close()

            except Exception:
                pass

        with self._lock:
            self._chunks = []


class VoiceRuntime:
    """
    Lazy GUI voice runtime.

    STT and TTS keep their existing implementations and model configuration.
    This class only owns lazy loading, push-to-talk recording, and UI-neutral
    status notifications.
    """

    def __init__(
        self,
        event_sink: Optional[
            Callable[
                [
                    str,
                ],
                None,
            ]
        ] = None,
    ):
        self.recorder = (
            PushToTalkRecorder()
        )

        self._event_sink = (
            event_sink
            or (
                lambda message: None
            )
        )

        self._stt_model = None
        self._tts_state = None

        self._stt_lock = (
            threading.Lock()
        )

        self._tts_lock = (
            threading.Lock()
        )

    def _emit(
        self,
        message: str,
    ) -> None:
        try:
            self._event_sink(
                str(
                    message
                    or ""
                )
            )

        except Exception:
            pass

    def start_recording(
        self,
    ) -> None:
        self.recorder.start()

    def stop_recording(
        self,
    ) -> np.ndarray:
        return self.recorder.stop()

    def cancel_recording(
        self,
    ) -> None:
        self.recorder.cancel()

    def _ensure_stt(
        self,
    ):
        with self._stt_lock:
            if self._stt_model is None:
                self._emit(
                    "Loading speech recognition"
                )

                self._stt_model = (
                    load_model()
                )

        return self._stt_model

    def _ensure_tts(
        self,
    ):
        with self._tts_lock:
            if self._tts_state is None:
                self._emit(
                    "Loading Mairon's voice"
                )

                self._tts_state = (
                    load_tts()
                )

        return self._tts_state

    def transcribe(
        self,
        audio: np.ndarray,
    ) -> str:
        model = (
            self._ensure_stt()
        )

        self._emit(
            "Transcribing"
        )

        result = transcribe_audio(
            model,
            audio,
        )

        if not isinstance(
            result,
            dict,
        ):
            raise RuntimeError(
                "Speech recognition returned an invalid result."
            )

        return normalise_voice_input(
            result.get(
                "text",
                "",
            )
        )

    def speak_response(
        self,
        text: str,
    ) -> None:
        value = str(
            text
            or ""
        ).strip()

        if not value:
            return

        state = (
            self._ensure_tts()
        )

        self._emit(
            "Speaking"
        )

        speak(
            state,
            value,
        )
