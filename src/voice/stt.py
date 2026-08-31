import queue
import sys
import threading

import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel


SAMPLE_RATE = 16000
CHANNELS = 1
MODEL_NAME = "small.en"
DEVICE = "cpu"
COMPUTE_TYPE = "int8"


def list_microphones():
    devices = sd.query_devices()

    print("\nAvailable input devices:\n")

    found = False

    for index, device in enumerate(devices):
        if device.get("max_input_channels", 0) <= 0:
            continue

        found = True
        default_marker = ""

        try:
            default_input = sd.default.device[0]

            if index == default_input:
                default_marker = "  <-- DEFAULT"
        except Exception:
            pass

        print(f"[{index}] {device['name']}{default_marker}")

    if not found:
        print("No microphone/input devices were found.")

    print()


def record_until_enter():
    audio_queue = queue.Queue()
    chunks = []

    def callback(indata, frames, time_info, status):
        if status:
            print(f"\n[Audio] {status}", file=sys.stderr)

        audio_queue.put(indata.copy())

    stop_event = threading.Event()

    def collector():
        while not stop_event.is_set():
            try:
                chunk = audio_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            chunks.append(chunk)

        while True:
            try:
                chunk = audio_queue.get_nowait()
            except queue.Empty:
                break

            chunks.append(chunk)

    print("Press Enter to START recording.")
    input()

    print("Recording... speak normally.")
    print("Press Enter to STOP.")

    collector_thread = threading.Thread(
        target=collector,
        daemon=True
    )
    collector_thread.start()

    try:
        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="float32",
            callback=callback
        ):
            input()

    except Exception as error:
        stop_event.set()
        collector_thread.join(timeout=1)

        raise RuntimeError(
            f"Microphone recording failed: {error}"
        ) from error

    stop_event.set()
    collector_thread.join(timeout=2)

    if not chunks:
        raise RuntimeError("No microphone audio was captured.")

    audio = np.concatenate(chunks, axis=0)
    return audio.reshape(-1).astype(np.float32)


def load_model():
    print(
        f"[STT] Loading {MODEL_NAME} "
        f"on {DEVICE} ({COMPUTE_TYPE})..."
    )

    model = WhisperModel(
        MODEL_NAME,
        device=DEVICE,
        compute_type=COMPUTE_TYPE
    )

    print("[STT] Model ready.")
    return model


def transcribe_audio(model, audio):
    print("[STT] Transcribing...")

    segments, info = model.transcribe(
        audio,
        language="en",
        beam_size=5,
        vad_filter=True,
        condition_on_previous_text=False
    )

    transcript_parts = []

    for segment in segments:
        text = segment.text.strip()

        if text:
            transcript_parts.append(text)

    return {
        "text": " ".join(transcript_parts).strip(),
        "language": info.language,
        "language_probability": info.language_probability
    }


def main():
    print()
    print("Mairon Voice MVP — Local STT Test")
    print("---------------------------------")

    list_microphones()
    model = load_model()

    print()
    print("Local speech recognition is ready.")
    print("Type Q at the ready prompt to quit.")

    while True:
        print()

        command = input(
            "Press Enter for a recording, or Q to quit: "
        ).strip().lower()

        if command == "q":
            print("STT test stopped.")
            break

        try:
            audio = record_until_enter()
            duration_seconds = len(audio) / SAMPLE_RATE

            print(
                f"[Audio] Captured "
                f"{duration_seconds:.1f} seconds."
            )

            result = transcribe_audio(model, audio)

            print()
            print("Mairon heard:")
            print("-------------")

            if result["text"]:
                print(result["text"])
            else:
                print("[No speech recognised]")

            print()

        except KeyboardInterrupt:
            print("\nSTT test stopped.")
            break

        except Exception as error:
            print(f"\n[Error] {error}\n")


if __name__ == "__main__":
    main()
