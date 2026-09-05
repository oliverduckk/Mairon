import ast
import sys
from pathlib import Path


PROJECT_ROOT = Path(
    __file__
).resolve().parents[1]

SRC_DIR = PROJECT_ROOT / "src"

if str(
    SRC_DIR
) not in sys.path:
    sys.path.insert(
        0,
        str(
            SRC_DIR
        ),
    )


def _source(
    path: Path,
) -> str:
    assert path.is_file(), path

    return path.read_text(
        encoding="utf-8",
    )


def run():
    app_path = (
        SRC_DIR
        / "desktop_app.py"
    )

    voice_path = (
        SRC_DIR
        / "voice"
        / "gui_voice.py"
    )

    app_source = _source(
        app_path
    )

    voice_source = _source(
        voice_path
    )

    app_tree = ast.parse(
        app_source,
        filename=str(
            app_path
        ),
    )

    voice_tree = ast.parse(
        voice_source,
        filename=str(
            voice_path
        ),
    )

    # --------------------------------------------------
    # 1. GUI voice recording is button-controlled, never console-controlled.
    # --------------------------------------------------

    assert (
        "class PushToTalkRecorder:"
        in voice_source
    )

    assert (
        "sd.InputStream("
        in voice_source
    )

    assert (
        "def start("
        in voice_source
    )

    assert (
        "def stop("
        in voice_source
    )

    assert (
        "record_until_enter"
        not in voice_source
    )

    assert (
        "record_until_enter"
        not in app_source
    )

    # --------------------------------------------------
    # 2. Existing STT/TTS engines remain the implementation authority.
    # --------------------------------------------------

    imported_voice_modules = set()

    for node in ast.walk(
        voice_tree
    ):
        if isinstance(
            node,
            ast.ImportFrom,
        ):
            imported_voice_modules.add(
                str(
                    node.module
                    or ""
                )
            )

    assert (
        "voice.stt"
        in imported_voice_modules
    )

    assert (
        "voice.tts"
        in imported_voice_modules
    )

    assert (
        "transcribe_audio("
        in voice_source
    )

    assert (
        "speak("
        in voice_source
    )

    # --------------------------------------------------
    # 3. Composer microphone is now an actual control.
    # --------------------------------------------------

    assert (
        "command=self._toggle_voice"
        in app_source
    )

    assert (
        "def _toggle_voice("
        in app_source
    )

    assert (
        "def _stop_voice_recording("
        in app_source
    )

    assert (
        "def _voice_transcribe_worker("
        in app_source
    )

    # --------------------------------------------------
    # 4. Voice transcript goes through the same application-service boundary.
    # --------------------------------------------------

    assert (
        'channel="voice"'
        in app_source
        or '"voice",' in app_source
    )

    assert (
        "self.application.submit_text("
        in app_source
    )

    imported_app_modules = set()

    for node in ast.walk(
        app_tree
    ):
        if isinstance(
            node,
            ast.ImportFrom,
        ):
            imported_app_modules.add(
                str(
                    node.module
                    or ""
                )
            )

    assert (
        "application_service"
        in imported_app_modules
    )

    assert (
        "core.orchestrator"
        not in imported_app_modules
    )

    assert (
        "core.router"
        not in imported_app_modules
    )

    # --------------------------------------------------
    # 5. Voice-originated final answers are spoken locally.
    # --------------------------------------------------

    assert (
        "def _start_speaking("
        in app_source
    )

    assert (
        "def _speech_worker("
        in app_source
    )

    assert (
        ".speak_response("
        in app_source
    )

    assert (
        'result.channel == "voice"'
        in app_source
    )

    # --------------------------------------------------
    # 6. UI exposes useful activity states.
    # --------------------------------------------------

    for state in (
        "Listening",
        "Transcribing",
        "Thinking",
        "Speaking",
    ):
        assert state in app_source

    print(
        "Mairon Phase 10.3 native GUI voice/TTS tests: PASS"
    )


if __name__ == "__main__":
    run()
