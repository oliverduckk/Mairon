import json
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
        "medium-fidelity regression unexpectedly called a live tool"
    )


fake_registry.execute_tool = _unpatched_execute_tool
sys.modules.setdefault(
    "tools.tool_registry",
    fake_registry,
)

from research import media_research
from research.media_grounding import verify_media_draft


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeResult:
    def __init__(self, content):
        self.message = _FakeMessage(
            content
        )


class _VerifierClient:
    def __init__(self):
        self.calls = []

    def chat(self, **kwargs):
        self.calls.append(
            kwargs
        )
        return _FakeResult(
            json.dumps({
                "supported": True,
                "unsupported_claims": [],
            })
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
    # 1. Infer semantic media boundaries without guessing a title/franchise.
    # --------------------------------------------------

    assert media_research.infer_requested_media_medium(
        "Can you give me a synopsis of Copper Horizon? I'm thinking about reading it.",
        _context("Copper Horizon"),
    ) == "textual"

    assert media_research.infer_requested_media_medium(
        "What's Glass Harbor about? I'm thinking about watching it.",
        _context("Glass Harbor"),
    ) == "screen"

    assert media_research.infer_requested_media_medium(
        "Give me a spoiler-free overview of the Copper Horizon manga.",
        _context("Copper Horizon"),
    ) == "manga"

    assert media_research.infer_requested_media_medium(
        "Give me a spoiler-free overview of the Glass Harbor anime.",
        _context("Glass Harbor"),
    ) == "anime"

    focus = media_research.build_media_read_focus(
        "Can you give me a synopsis of Copper Horizon? I'm thinking about reading it.",
        _context("Copper Horizon"),
        research_mode="spoiler_light_overview",
        requested_medium="textual",
    ).lower()

    assert "opening premise" in focus
    assert "protagonist" in focus
    assert "broad conflict" in focus
    assert "thinking about reading" not in focus

    # Exact stored spoiler-profile medium remains useful when the current turn
    # does not restate it.
    profile_context = _context("Copper Horizon")
    profile_context["profile"] = {
        "medium": "web_novel",
    }

    assert media_research.infer_requested_media_medium(
        "What is the premise?",
        profile_context,
    ) == "web_novel"

    # --------------------------------------------------
    # 2. Reading requests reject clear film/TV adaptations before web_read.
    # --------------------------------------------------

    raw_results = {
        "success": True,
        "results": [
            {
                "title": "Copper Horizon (2024 film) - IMDb",
                "url": "https://www.imdb.com/title/tt1234567/",
                "content": "Plot and cast for the 2024 adaptation.",
                "score": 0.99,
            },
            {
                "title": "Copper Horizon (novel) - Wikipedia",
                "url": "https://en.wikipedia.org/wiki/Copper_Horizon_(novel)",
                "content": "An introductory description of the written work.",
                "score": 0.95,
            },
            {
                "title": "Copper Horizon - Publisher Overview",
                "url": "https://publisher.example/copper-horizon",
                "content": "Premise and author information.",
                "score": 0.90,
            },
        ],
    }

    cleaned = media_research._extract_search_results(
        raw_results
    )

    assert cleaned[0]["source_medium"] in {
        "film",
        "screen",
    }
    assert cleaned[1]["source_medium"] == "novel"

    selected = media_research._select_results_for_reading(
        cleaned,
        max_reads=2,
        research_mode="spoiler_light_overview",
        requested_medium="textual",
    )

    selected_titles = [
        item.get("title")
        for item in selected
    ]

    assert "Copper Horizon (2024 film) - IMDb" not in selected_titles
    assert selected_titles[0] == "Copper Horizon (novel) - Wikipedia"

    # An explicit exact-medium request is stricter than a family boundary.
    exact_results = media_research._extract_search_results({
        "success": True,
        "results": [
            {
                "title": "Glass Harbor novel overview",
                "url": "https://example.com/glass-harbor-novel",
                "content": "Novel premise.",
                "score": 0.99,
            },
            {
                "title": "Glass Harbor manga overview",
                "url": "https://example.org/glass-harbor-manga",
                "content": "Manga premise.",
                "score": 0.90,
            },
        ],
    })

    exact_selected = media_research._select_results_for_reading(
        exact_results,
        max_reads=2,
        research_mode="spoiler_light_overview",
        requested_medium="manga",
    )

    assert [
        item.get("source_medium")
        for item in exact_selected
    ] == [
        "manga",
    ]

    # If every source is clearly the wrong adaptation, fail closed.
    wrong_only = media_research._extract_search_results({
        "success": True,
        "results": [
            {
                "title": "Copper Horizon film - IMDb",
                "url": "https://www.imdb.com/title/tt1111111/",
                "content": "Film plot.",
                "score": 0.99,
            },
            {
                "title": "Copper Horizon TV series",
                "url": "https://example.com/copper-horizon-tv-series",
                "content": "Television adaptation.",
                "score": 0.90,
            },
        ],
    })

    assert media_research._select_results_for_reading(
        wrong_only,
        max_reads=2,
        research_mode="spoiler_light_overview",
        requested_medium="textual",
    ) == []

    # --------------------------------------------------
    # 3. Evidence packet carries medium fidelity + stronger spoiler scope.
    # --------------------------------------------------

    packet = media_research.build_internal_research_packet({
        "success": True,
        "query": "Copper Horizon synopsis premise overview official",
        "topic": "Copper Horizon",
        "research_mode": "spoiler_light_overview",
        "recommendation_requested": False,
        "requested_medium": "textual",
        "spoiler_profile": "unknown",
        "sources": [
            {
                "title": "Copper Horizon (novel)",
                "url": "https://example.com/copper-horizon-novel",
                "source_medium": "novel",
                "search_snippet": "Opening premise.",
                "read_success": True,
                "read_result": {
                    "success": True,
                    "content": "The story begins with a family moving to a distant settlement.",
                },
            },
        ],
    })

    assert '"requested_medium": "textual"' in packet
    assert '"source_medium": "novel"' in packet
    assert "opening-premise / jacket-blurb scope" in packet
    assert "specific betrayal or conspiracy mechanics" in packet
    assert "Do not silently substitute an adaptation/source medium" in packet

    # --------------------------------------------------
    # 4. Verifier receives both spoiler-scope and medium-fidelity constraints.
    # --------------------------------------------------

    client = _VerifierClient()

    violations = verify_media_draft(
        client=client,
        model="qwen3.5:9b",
        user_input=(
            "Can you give me a synopsis of Copper Horizon? "
            "I'm thinking about reading it."
        ),
        draft=(
            "The story begins with a family moving to a distant settlement."
        ),
        research_evidence=packet,
    )

    assert violations == []
    verifier_system = client.calls[0][
        "messages"
    ][0][
        "content"
    ]

    assert "jacket-blurb scope" in verifier_system
    assert "betrayal/conspiracy mechanics" in verifier_system
    assert "MEDIUM-FIDELITY MODE" in verifier_system
    assert "textual" in verifier_system

    # --------------------------------------------------
    # 5. Provider diagnostics expose medium filtering in terminal logs.
    # --------------------------------------------------

    provider_source = (
        SRC_DIR
        / "ai"
        / "ollama_provider.py"
    ).read_text(
        encoding="utf-8"
    )

    assert "[Research] Requested media boundary:" in provider_source
    assert "[Research] Skipped medium-mismatched search results:" in provider_source

    # Production remains franchise/title agnostic.
    production_source = (
        SRC_DIR
        / "research"
        / "media_research.py"
    ).read_text(
        encoding="utf-8"
    ).lower()

    assert "copper horizon" not in production_source
    assert "glass harbor" not in production_source

    print(
        "Mairon Phase 10.7.4 medium-fidelity tests: PASS"
    )


if __name__ == "__main__":
    run()
