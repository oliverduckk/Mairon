import sys
from pathlib import Path


PROJECT_ROOT = Path(
    __file__
).resolve().parents[1]

SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(
        0,
        str(SRC_DIR),
    )


from personality.spoiler_guard import (
    resolve_media_title,
    should_activate_media_domain,
)
from research.media_research import (
    should_research_media_turn,
)


def _research_required(
    user_text: str,
    title: str,
) -> bool:
    return should_research_media_turn(
        user_input=user_text,
        conversation_policy={},
        spoiler_context={
            "title": title,
            "profile": None,
            "must_ask_progress": False,
            "must_complete_progress": False,
            "must_confirm_latest": False,
            "progress_updated": False,
            "pending_question": None,
            "release_sensitive": False,
        },
    )


def run():
    # --------------------------------------------------
    # 1. Exact Shadow Slave live failure enters media authority.
    # --------------------------------------------------

    shadow_prompt = (
        "can you provide me with a synopsis on Shadow Slave. "
        "Im thinking about reading it"
    )

    assert should_activate_media_domain(
        shadow_prompt
    ) is True

    shadow_title = resolve_media_title(
        shadow_prompt
    )

    assert (
        str(
            shadow_title
            or ""
        ).lower()
        == "shadow slave"
    )

    assert _research_required(
        shadow_prompt,
        shadow_title,
    ) is True

    # --------------------------------------------------
    # 2. Medium-identification questions resolve their actual title.
    # --------------------------------------------------

    bleach_prompt = (
        "is bleach an anime or manga?"
    )

    assert should_activate_media_domain(
        bleach_prompt
    ) is True

    bleach_title = resolve_media_title(
        bleach_prompt
    )

    assert (
        str(
            bleach_title
            or ""
        ).lower()
        == "bleach"
    )

    assert _research_required(
        bleach_prompt,
        bleach_title,
    ) is True

    one_piece_prompt = (
        "is one piece a manga or anime?"
    )

    one_piece_title = resolve_media_title(
        one_piece_prompt
    )

    assert (
        str(
            one_piece_title
            or ""
        ).lower()
        == "one piece"
    )

    assert _research_required(
        one_piece_prompt,
        one_piece_title,
    ) is True

    # --------------------------------------------------
    # 3. Broad factual media overview language is grounded.
    # --------------------------------------------------

    for prompt in (
        "give me a summary of Bleach",
        "can you give me an overview of One Piece",
        "what is the Bleach manga about",
    ):
        assert _research_required(
            prompt,
            "Bleach",
        ) is True

    print(
        "Mairon Phase 10.7 grounded-media-overview routing tests: PASS"
    )


if __name__ == "__main__":
    run()
