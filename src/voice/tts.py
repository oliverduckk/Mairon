import re
import urllib.request
from pathlib import Path

import numpy as np
import sounddevice as sd
from kokoro_onnx import Kokoro


PROJECT_ROOT = Path(__file__).resolve().parents[2]

MODEL_DIR = PROJECT_ROOT / "data" / "models" / "kokoro"
MODEL_PATH = MODEL_DIR / "kokoro-v1.0.onnx"
VOICES_PATH = MODEL_DIR / "voices-v1.0.bin"

MODEL_URL = (
    "https://github.com/thewh1teagle/"
    "kokoro-onnx/releases/download/"
    "model-files-v1.0/kokoro-v1.0.onnx"
)

VOICES_URL = (
    "https://github.com/thewh1teagle/"
    "kokoro-onnx/releases/download/"
    "model-files-v1.0/voices-v1.0.bin"
)


# Provisional Mairon voice:
# Eric supplies most of the natural delivery.
# Onyx adds a little lower/drier character.
PRIMARY_VOICE = "am_onyx"
SECONDARY_VOICE = "am_eric"
PRIMARY_WEIGHT = 0.75
SECONDARY_WEIGHT = 0.25

VOICE_LANGUAGE = "en-us"
VOICE_SPEED = 0.90


def download_file(url, destination, label):
    if destination.exists():
        return

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    partial_path = destination.with_suffix(
        destination.suffix + ".part"
    )

    print(f"[TTS] Downloading {label}...")

    try:
        urllib.request.urlretrieve(
            url,
            partial_path,
        )

        partial_path.replace(
            destination
        )

    except Exception:
        if partial_path.exists():
            try:
                partial_path.unlink()
            except OSError:
                pass

        raise


def ensure_model_files():
    MODEL_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    download_file(
        MODEL_URL,
        MODEL_PATH,
        "Kokoro model",
    )

    download_file(
        VOICES_URL,
        VOICES_PATH,
        "Kokoro voice pack",
    )


def load_tts():
    """
    Load Kokoro locally and prepare Mairon's blended voice.
    """

    ensure_model_files()

    print("[TTS] Loading Mairon's local voice...")

    engine = Kokoro(
        str(MODEL_PATH),
        str(VOICES_PATH),
    )

    primary_style = engine.get_voice_style(
        PRIMARY_VOICE
    )

    secondary_style = engine.get_voice_style(
        SECONDARY_VOICE
    )

    voice_style = (
        primary_style * PRIMARY_WEIGHT
        + secondary_style * SECONDARY_WEIGHT
    )

    print("[TTS] Mairon's voice ready.")

    return {
        "engine": engine,
        "voice_style": voice_style,
    }


def apply_pronunciation_rules(text):
    """
    Speech-only pronunciation hints.

    No custom pronunciation overrides are currently active.
    Kokoro uses its normal pronunciation so prosody stays natural.
    """

    return text


def normalise_temperature_for_speech(match):
    """
    Turn compact temperature notation into natural spoken text.

    Example:
        11.8°C -> 11 point 8 degrees Celsius

    This prevents Kokoro from treating the decimal point as sentence
    punctuation and pausing between the whole and fractional parts.
    """

    number = match.group(
        "number"
    )

    unit = match.group(
        "unit"
    ).upper()

    spoken_number = number.replace(
        ".",
        " point ",
    )

    if unit == "C":
        unit_text = "degrees Celsius"
    else:
        unit_text = "degrees Fahrenheit"

    return (
        f"{spoken_number} "
        f"{unit_text}"
    )


def clean_text_for_speech(text):
    """
    Convert Mairon's display text into speech-friendly text.

    This is an output-only transformation. Mairon's actual response,
    conversation history, memories, and displayed text are untouched.
    """

    value = str(text or "").strip()

    if not value:
        return ""

    # Remove fenced-code markers.
    value = re.sub(
        r"```[a-zA-Z0-9_+-]*",
        "",
        value,
    )

    value = value.replace(
        "```",
        "",
    )

    # Strip Markdown formatting tokens. Kokoro otherwise sometimes
    # literally says words such as "asterisk".
    value = value.replace(
        "**",
        "",
    )

    value = value.replace(
        "__",
        "",
    )

    value = value.replace(
        "`",
        "",
    )

    value = value.replace(
        "*",
        "",
    )

    value = value.replace(
        "~~",
        "",
    )

    # Headings and list markers are visual formatting, not speech.
    value = re.sub(
        r"(?m)^\s*#{1,6}\s*",
        "",
        value,
    )

    value = re.sub(
        r"(?m)^\s*[-+]\s+",
        "",
        value,
    )

    # Make temperatures explicit before generic decimal handling.
    value = re.sub(
        r"(?P<number>-?\d+(?:\.\d+)?)\s*°?\s*(?P<unit>[CF])\b",
        normalise_temperature_for_speech,
        value,
        flags=re.IGNORECASE,
    )

    # Other decimal numbers should say "point" instead of letting
    # Kokoro treat the period like sentence punctuation.
    value = re.sub(
        r"(?<=\d)\.(?=\d)",
        " point ",
        value,
    )

    # Common symbols read more naturally expanded.
    value = re.sub(
        r"(?<=\d)\s*%",
        " percent",
        value,
    )

    # Collapse formatting whitespace after all replacements.
    value = re.sub(
        r"\s+",
        " ",
        value,
    ).strip()

    return apply_pronunciation_rules(
        value
    )


def generate_speech(tts_state, text):
    speech_text = clean_text_for_speech(
        text
    )

    if not speech_text:
        return None, None

    engine = tts_state["engine"]
    voice_style = tts_state["voice_style"]

    samples, sample_rate = engine.create(
        speech_text,
        voice=voice_style,
        speed=VOICE_SPEED,
        lang=VOICE_LANGUAGE,
    )

    samples = np.asarray(
        samples,
        dtype=np.float32,
    )

    return samples, sample_rate


def speak(tts_state, text):
    """
    Generate and play speech locally.

    Audio stays in memory and is not written to disk.
    """

    samples, sample_rate = generate_speech(
        tts_state,
        text,
    )

    if samples is None:
        return

    sd.play(
        samples,
        samplerate=sample_rate,
    )

    sd.wait()
