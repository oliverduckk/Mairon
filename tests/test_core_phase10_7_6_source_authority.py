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
        "source-authority regression unexpectedly called a live tool"
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


def run():
    # --------------------------------------------------
    # 1. Readability is not authority: classify provenance generically.
    # --------------------------------------------------

    assert media_research._source_quality_class(
        "https://en.wikipedia.org/wiki/Signal_Fire"
    ) == "reference"

    assert media_research._source_quality_class(
        "https://www.imdb.com/title/tt1111111/plotsummary/"
    ) == "secondary_database"

    assert media_research._source_quality_class(
        "https://example.org/signal-fire-review"
    ) == "general_web"

    # --------------------------------------------------
    # 2. A spoiler-light overview should anchor on stronger provenance when
    #    a reference/official source is available near the top of search.
    # --------------------------------------------------

    raw_results = {
        "success": True,
        "results": [
            {
                "title": "Signal Fire (TV Series 2022-) - Plot - IMDb",
                "url": "https://www.imdb.com/title/tt1111111/plotsummary/",
                "content": "Detailed plot contribution.",
                "score": 0.99,
            },
            {
                "title": "Signal Fire (TV series) - Wikipedia",
                "url": "https://en.wikipedia.org/wiki/Signal_Fire_(TV_series)",
                "content": "Reference opening premise.",
                "score": 0.96,
            },
            {
                "title": "Signal Fire | Official Series Page",
                "url": "https://www.netflix.com/title/99999999",
                "content": "Official introductory description.",
                "score": 0.91,
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

    assert len(selected) == 2
    assert selected[0]["source_quality"] == "secondary_database"
    assert any(
        item["source_quality"] in {
            "official_or_publisher",
            "reference",
        }
        for item in selected[1:]
    )

    # --------------------------------------------------
    # 3. Provenance quality must survive into the evidence packet so the
    #    verifier can apply asymmetric authority rather than treating all
    #    readable pages equally.
    # --------------------------------------------------

    packet = media_research.build_internal_research_packet({
        "success": True,
        "query": "Signal Fire synopsis premise overview official",
        "topic": "Signal Fire",
        "research_mode": "spoiler_light_overview",
        "recommendation_requested": False,
        "requested_medium": "screen",
        "spoiler_profile": "unknown",
        "sources": [
            {
                "title": "Signal Fire (TV series) - Wikipedia",
                "url": "https://en.wikipedia.org/wiki/Signal_Fire_(TV_series)",
                "source_quality": "reference",
                "source_medium": "tv",
                "search_snippet": "Opening premise.",
                "read_success": True,
                "read_result": {
                    "success": True,
                    "content": "Opening premise and broad conflict.",
                },
            },
            {
                "title": "Signal Fire - Plot - IMDb",
                "url": "https://www.imdb.com/title/tt1111111/plotsummary/",
                "source_quality": "secondary_database",
                "source_medium": "tv",
                "search_snippet": "Additional plot contribution.",
                "read_success": True,
                "read_result": {
                    "success": True,
                    "content": "A secondary plot detail not corroborated elsewhere.",
                },
            },
        ],
    })

    assert '"source_quality": "reference"' in packet
    assert '"source_quality": "secondary_database"' in packet
    assert "secondary_database/general_web are supporting sources" in packet

    grounding_source = (
        SRC_DIR
        / "research"
        / "media_grounding.py"
    ).read_text(
        encoding="utf-8"
    )

    assert "Treat source reliability asymmetrically" in grounding_source
    assert "secondary_database/general_web" in grounding_source
    assert "hidden identities or aliases" in grounding_source
    assert "FACTUAL SUPPORT and SCOPE COMPLIANCE are separate decisions" in grounding_source

    # --------------------------------------------------
    # 4. Repair remains deletion-first rather than replacing a rejected claim
    #    with a fresh unsupported opinion.
    # --------------------------------------------------

    retry = build_grounding_retry_instruction([
        "unsupported media claim: secondary-only criminal-world detail",
    ])

    assert retry is not None
    assert "REMOVED" in retry
    assert "becoming SHORTER" in retry

    # No acceptance fixture may leak into production routing.
    production_source = (
        SRC_DIR
        / "research"
        / "media_research.py"
    ).read_text(
        encoding="utf-8"
    ).lower()

    assert "signal fire" not in production_source
    assert "breaking bad" not in production_source
    assert "tokyo ghoul" not in production_source

    print(
        "Mairon Phase 10.7.6 source-authority tests: PASS"
    )


if __name__ == "__main__":
    run()
