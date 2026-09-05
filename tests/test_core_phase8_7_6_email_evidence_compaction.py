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


from core.workflows.email_read import (
    _compact_verified_body_for_generation,
)


def run():
    raw = (
        "These employers are hiring now!\n"
        "\n"
        "( https://example.com/tracking?utm_source=email )\n"
        "***************************************\n"
        "New Graduate Jobs that may interest you\n"
        "***************************************\n"
        "Mainfreight Australia ( https://example.com/job )\n"
        "Graduate Program - Supply Chain & Logistics\n"
        "AUD 67,400 - AUD 77,700 / Year\n"
        "Applications close 31 December 2026\n"
    )

    compact = _compact_verified_body_for_generation(
        raw,
        char_budget=1000,
    )

    assert (
        "These employers are hiring now!"
        in compact
    )

    assert (
        "New Graduate Jobs that may interest you"
        in compact
    )

    assert (
        "Mainfreight Australia"
        in compact
    )

    assert (
        "Applications close 31 December 2026"
        in compact
    )

    assert (
        "https://"
        not in compact
    )

    assert (
        "utm_source"
        not in compact
    )

    assert (
        "***************************************"
        not in compact
    )

    # Long source bodies are bounded for model generation.
    long_raw = "\n".join(
        f"Verified line {index}: " + ("x" * 90)
        for index in range(100)
    )

    long_compact = _compact_verified_body_for_generation(
        long_raw,
        char_budget=1000,
    )

    assert len(
        long_compact
    ) < 1200

    assert (
        "[Verified email body compacted for generation.]"
        in long_compact
    )

    print(
        "Mairon Phase 8.7.6 email evidence compaction tests: PASS"
    )


if __name__ == "__main__":
    run()
