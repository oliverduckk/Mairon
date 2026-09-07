import sys
import types
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


# Keep this regression independent from private Gmail/Calendar integrations.
fake_registry = types.ModuleType(
    "tools.tool_registry"
)


def _unpatched_execute_tool(*args, **kwargs):
    raise AssertionError(
        "spoiler-safe source-quality regression unexpectedly called a live tool"
    )


fake_registry.execute_tool = _unpatched_execute_tool
sys.modules.setdefault(
    "tools.tool_registry",
    fake_registry,
)

from research import media_research


def _context(title):
    return {
        "title": title,
        "profile": None,
        "must_ask_progress": False,
        "must_complete_progress": False,
        "must_confirm_latest": False,
        "progress_updated": False,
        "pending_question": None,
        "release_sensitive": False,
    }


def run():
    # --------------------------------------------------
    # 1. Prospective-reader requests are classified semantically.
    # --------------------------------------------------

    prompt = (
        "Can you give me a synopsis of Dune? "
        "I'm thinking about reading it."
    )

    assert media_research.classify_media_research_mode(
        prompt,
        _context("Dune"),
    ) == "spoiler_light_overview"

    query = media_research.build_media_search_query(
        prompt,
        _context("Dune"),
    ).lower()

    assert "dune" in query
    assert "synopsis" in query
    assert "premise" in query
    assert "overview" in query
    assert "thinking about reading" not in query

    # Explicit full-plot intent must not be silently rewritten to spoiler-light.
    assert media_research.classify_media_research_mode(
        "Give me the full story and ending of Dune",
        _context("Dune"),
    ) == "full_plot"

    # --------------------------------------------------
    # 2. A higher-ranked ending explainer loses to safer overview sources.
    # --------------------------------------------------

    raw_results = {
        "success": True,
        "results": [
            {
                "title": "Dune Full Story & Ending Explained",
                "url": "https://example.com/dune-ending-explained",
                "content": "Every major plot beat and the ending explained.",
                "score": 0.99,
            },
            {
                "title": "Dune - Wikipedia",
                "url": "https://en.wikipedia.org/wiki/Dune_(novel)",
                "content": "Dune is a science fiction novel.",
                "score": 0.95,
            },
            {
                "title": "Dune Book Overview",
                "url": "https://publisher.example/books/dune",
                "content": "An introductory description of the novel's premise.",
                "score": 0.85,
            },
        ],
    }

    cleaned = media_research._extract_search_results(
        raw_results
    )

    assert cleaned[0][
        "spoiler_risk"
    ] > 0

    selected = media_research._select_results_for_reading(
        cleaned,
        max_reads=2,
        research_mode="spoiler_light_overview",
    )

    selected_titles = [
        item.get("title")
        for item in selected
    ]

    assert "Dune Full Story & Ending Explained" not in selected_titles
    assert selected_titles[0] == "Dune - Wikipedia"
    assert len(selected_titles) == 2

    # --------------------------------------------------
    # 3. If every result advertises full-plot spoilers, Core fails closed.
    # --------------------------------------------------

    only_spoilers = media_research._extract_search_results({
        "success": True,
        "results": [
            {
                "title": "Movie Ending Explained",
                "url": "https://example.com/ending",
                "content": "Full story spoilers and ending explained.",
                "score": 0.99,
            },
            {
                "title": "Complete Story Recap",
                "url": "https://example.org/full-recap",
                "content": "Complete recap with spoilers.",
                "score": 0.90,
            },
        ],
    })

    assert media_research._select_results_for_reading(
        only_spoilers,
        max_reads=2,
        research_mode="spoiler_light_overview",
    ) == []

    # --------------------------------------------------
    # 4. Evidence packet carries answer-mode rules to generation/verifier.
    # --------------------------------------------------

    packet = media_research.build_internal_research_packet({
        "success": True,
        "query": "Dune synopsis premise overview official",
        "topic": "Dune",
        "research_mode": "spoiler_light_overview",
        "recommendation_requested": False,
        "spoiler_profile": "unknown",
        "sources": [
            {
                "title": "Introductory source",
                "url": "https://example.com/dune",
                "search_snippet": "An introductory premise.",
                "read_success": True,
                "read_result": {
                    "success": True,
                    "content": "The novel follows a young noble family in a distant future.",
                },
            },
        ],
    })

    assert '"answer_mode": "spoiler_light_overview"' in packet
    assert '"recommendation_requested": false' in packet
    assert "Use premise/setup material only" in packet
    assert "do not append a recommendation" in packet

    # Production logic remains title-agnostic: the test title should not be
    # hard-coded anywhere in the source module.
    production_source = (
        SRC_DIR
        / "research"
        / "media_research.py"
    ).read_text(
        encoding="utf-8"
    ).lower()

    assert '"dune"' not in production_source
    assert "shadow slave" not in production_source
    assert "beginning after the end" not in production_source

    print(
        "Mairon Phase 10.7.3 spoiler-safe source-quality tests: PASS"
    )


if __name__ == "__main__":
    run()
