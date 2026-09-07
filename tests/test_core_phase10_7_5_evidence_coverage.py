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


fake_registry = types.ModuleType(
    "tools.tool_registry"
)


def _unpatched_execute_tool(*args, **kwargs):
    raise AssertionError(
        "evidence-coverage regression unexpectedly called a live tool"
    )


fake_registry.execute_tool = _unpatched_execute_tool
sys.modules.setdefault(
    "tools.tool_registry",
    fake_registry,
)

from research import media_research
from research.media_grounding import (
    build_grounding_retry_instruction,
)


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
    # 1. Prefer independent hosts for the second evidence source.
    # --------------------------------------------------

    raw_results = {
        "success": True,
        "results": [
            {
                "title": "Glass Harbor (TV Series 2020-2024) - Plot - IMDb",
                "url": "https://www.imdb.com/title/tt1111111/plotsummary/",
                "content": "Opening premise and plot summary.",
                "score": 0.99,
            },
            {
                "title": "Glass Harbor (TV Series 2020-2024) - IMDb",
                "url": "https://www.imdb.com/title/tt1111111/",
                "content": "Series overview.",
                "score": 0.97,
            },
            {
                "title": "Glass Harbor (TV series) - Wikipedia",
                "url": "https://en.wikipedia.org/wiki/Glass_Harbor_(TV_series)",
                "content": "Independent reference overview.",
                "score": 0.93,
            },
        ],
    }

    cleaned = media_research._extract_search_results(
        raw_results
    )

    selected = media_research._select_results_for_reading(
        cleaned,
        max_reads=2,
        research_mode="spoiler_light_overview",
        requested_medium="screen",
    )

    selected_urls = [
        item["url"]
        for item in selected
    ]

    assert len(selected_urls) == 2
    assert "imdb.com/title/tt1111111/plotsummary" in selected_urls[0]
    assert "wikipedia.org" in selected_urls[1]
    assert selected_urls[0] != selected_urls[1]

    # --------------------------------------------------
    # 2. Failed webpage reads are backfilled from safe ranked candidates.
    # --------------------------------------------------

    calls = []

    def fake_execute_tool(name, arguments):
        calls.append(
            (name, dict(arguments))
        )

        if name == "web_search":
            return {
                "success": True,
                "results": [
                    {
                        "title": "Glass Harbor (TV Series 2020-2024) - Plot - IMDb",
                        "url": "https://www.imdb.com/title/tt1111111/plotsummary/",
                        "content": "Opening premise.",
                        "score": 0.99,
                    },
                    {
                        "title": "Glass Harbor (TV series) - Wikipedia",
                        "url": "https://en.wikipedia.org/wiki/Glass_Harbor_(TV_series)",
                        "content": "Reference overview.",
                        "score": 0.95,
                    },
                    {
                        "title": "Glass Harbor | Official Series Page",
                        "url": "https://www.netflix.com/title/99999999",
                        "content": "Official introductory description.",
                        "score": 0.90,
                    },
                ],
            }

        if name == "web_read":
            url = arguments["url"]

            if "imdb.com" in url:
                return {
                    "success": False,
                    "message": "page extraction failed",
                }

            return {
                "success": True,
                "content": (
                    "A concise opening-premise description with the central "
                    "character, starting situation, and broad conflict."
                ),
            }

        raise AssertionError(
            f"unexpected tool: {name}"
        )

    original_execute_tool = media_research.execute_tool
    media_research.execute_tool = fake_execute_tool

    try:
        result = media_research.gather_media_research(
            "Can you give me a synopsis of Glass Harbor? I'm thinking about watching it.",
            _context("Glass Harbor"),
            max_reads=2,
        )
    finally:
        media_research.execute_tool = original_execute_tool

    assert result["success"] is True
    assert result["readable_source_count"] == 2
    assert result["read_attempt_count"] == 3
    assert result["read_backfill_count"] >= 1

    readable_urls = [
        source["url"]
        for source in result["sources"]
        if source["read_success"]
    ]

    assert len(readable_urls) == 2
    assert any(
        "wikipedia.org" in url
        for url in readable_urls
    )
    assert any(
        "netflix.com" in url
        for url in readable_urls
    )

    # --------------------------------------------------
    # 3. Repair removes unsupported filler instead of inventing new opinions.
    # --------------------------------------------------

    retry = build_grounding_retry_instruction([
        "unsupported media claim: invented broad danger claim",
    ])

    assert retry is not None
    assert "Keep subjective opinions if you want" not in retry
    assert "new tone judgments" in retry
    assert "becoming SHORTER" in retry
    assert "two-sentence answer" in retry

    # --------------------------------------------------
    # 4. Spoiler-light packet explicitly prefers brevity over plausible filler.
    # --------------------------------------------------

    packet = media_research.build_internal_research_packet({
        "success": True,
        "query": "Glass Harbor synopsis premise overview official",
        "topic": "Glass Harbor",
        "research_mode": "spoiler_light_overview",
        "recommendation_requested": False,
        "requested_medium": "screen",
        "spoiler_profile": "unknown",
        "sources": [
            {
                "title": "Glass Harbor overview",
                "url": "https://example.com/glass-harbor",
                "source_medium": "tv",
                "search_snippet": "Opening premise.",
                "read_success": True,
                "read_result": {
                    "success": True,
                    "content": "Opening premise and broad conflict only.",
                },
            },
        ],
    })

    assert "Prefer a compact 2-3 sentence synopsis" in packet
    assert "HARD CONTENT CEILING" in packet
    assert "use fewer sentences rather than broadening" in packet

    # Production remains title-agnostic.
    production_source = (
        SRC_DIR
        / "research"
        / "media_research.py"
    ).read_text(
        encoding="utf-8"
    ).lower()

    assert "glass harbor" not in production_source
    assert "breaking bad" not in production_source
    assert "tokyo ghoul" not in production_source

    print(
        "Mairon Phase 10.7.5 evidence-coverage tests: PASS"
    )


if __name__ == "__main__":
    run()
