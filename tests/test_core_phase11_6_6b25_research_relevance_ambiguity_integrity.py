import sys
import types
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


# This regression exercises the public-research module with a deterministic
# fake tool boundary. Avoid importing optional Gmail/Calendar dependencies that
# the production tool registry pulls in but this unit does not need.
fake_registry = types.ModuleType("tools.tool_registry")
fake_registry.execute_tool = lambda *args, **kwargs: None
sys.modules["tools.tool_registry"] = fake_registry


import research.public_factual_research as public_research
from research.public_factual_grounding import (
    find_grounded_opinion_response_violations,
)


def _result(title, url, snippet="", published_date=None):
    return {
        "title": title,
        "url": url,
        "content": snippet,
        "score": 1.0,
        "published_date": published_date,
    }


def _read(content):
    return {
        "success": True,
        "content": content,
    }


def run():
    # --------------------------------------------------
    # 1. An explicit calendar date is a HARD referent constraint. Search
    #    results about "Episode 9" must not satisfy "September 9" merely
    #    because the entity/topic also matches.
    # --------------------------------------------------
    calls = []
    original_execute = public_research.execute_tool

    search_results = {
        "success": True,
        "results": [
            _result(
                "Re:Zero 2 episode 9 (34) – Natsuki Subaru and the Magical Menagerie",
                "https://wrong-one.example/review",
                "A review of Re:Zero episode 9 featuring Natsuki Subaru.",
            ),
            _result(
                "Re:ZERO Season 4 Episode 9 - Anime Review",
                "https://wrong-two.example/review",
                "Season 4 episode 9 review and Subaru discussion.",
            ),
            _result(
                "Natsuki Subaru special discussed on September 9",
                "https://resolved.example/september-9",
                "Coverage tied explicitly to September 9 and Natsuki Subaru.",
            ),
        ],
    }

    reads = {
        "https://wrong-one.example/review": _read(
            "Natsuki Subaru appears throughout this review of Re:Zero episode 9."
        ),
        "https://wrong-two.example/review": _read(
            "This page discusses Re:ZERO Season 4 Episode 9 and Subaru."
        ),
        "https://resolved.example/september-9": _read(
            "On September 9, this Natsuki Subaru item was discussed by the community."
        ),
    }

    def fake_execute(name, arguments):
        calls.append((name, dict(arguments)))

        if name == "web_search":
            return search_results

        if name == "web_read":
            return reads[arguments["url"]]

        raise AssertionError(name)

    public_research.execute_tool = fake_execute

    try:
        result = public_research.gather_public_factual_research(
            "Natsuki Subaru episode from September 9 everyone was talking about",
            max_reads=2,
            require_query_resolution=True,
        )
    finally:
        public_research.execute_tool = original_execute

    assert result["success"] is True, result
    assert result["query_resolution_required"] is True
    assert result["read_attempt_count"] == 3, result
    assert result["accepted_source_count"] == 1, result
    assert result["rejected_source_count"] >= 2, result

    accepted = [
        source
        for source in result["sources"]
        if source.get("accepted_as_evidence")
    ]
    assert [source["url"] for source in accepted] == [
        "https://resolved.example/september-9"
    ], accepted

    rejected_reasons = [
        reason
        for item in result["rejected_sources"]
        for reason in item.get("reasons", [])
    ]
    assert any(
        "unresolved_query_constraint:September 9" in reason
        for reason in rejected_reasons
    ), rejected_reasons

    packet = public_research.build_internal_public_factual_packet(result)
    assert "resolved.example/september-9" in packet
    assert "wrong-one.example" not in packet
    assert "wrong-two.example" not in packet

    # --------------------------------------------------
    # 2. "Episode 9" without a calendar-date phrase remains ordinary content
    #    identity. The B25 date guard must not invent a September constraint.
    # --------------------------------------------------
    assert public_research._query_resolution_constraints(
        "Natsuki Subaru episode 9"
    ) == []

    # --------------------------------------------------
    # 3. User-generated fiction/community pages are not independent editorial
    #    authority merely because they happen to be readable.
    # --------------------------------------------------
    wattpad = public_research.classify_public_source_authority(
        {
            "url": "https://www.wattpad.com/story/example",
            "source_host": "wattpad.com",
            "source_quality": "general_web",
        },
        research_identity="Horikita class vote COTE",
    )
    assert wattpad["authority_tier"] == "weak_community_or_social", wattpad
    assert wattpad["quality_eligible"] is False, wattpad

    # --------------------------------------------------
    # 4. A grounded-opinion response must still ANSWER the opinion request.
    #    Sentence salvage cannot turn an unsupported answer into only a
    #    follow-up question and call that success.
    # --------------------------------------------------
    question_only = find_grounded_opinion_response_violations(
        "do you think she handled it well though?",
        "Does that make you feel better about her, or are you still mad?",
    )
    assert question_only, question_only

    assert not find_grounded_opinion_response_violations(
        "do you think she handled it well though?",
        "I don't know enough about what happened there to judge it properly.",
    )
    assert not find_grounded_opinion_response_violations(
        "do you think she handled it well though?",
        "No, I think she handled it badly based on that context.",
    )

    # --------------------------------------------------
    # 5. Integration guards: foreground public research activates query
    #    resolution, rejected pages are not exposed as evidence-source logs,
    #    and grounded opinions get the adequacy check after source verification.
    # --------------------------------------------------
    provider_source = (
        PROJECT_ROOT / "src" / "ai" / "ollama_provider.py"
    ).read_text(encoding="utf-8")

    assert "require_query_resolution=True" in provider_source
    assert "source.get(\"accepted_as_evidence\") is not False" in provider_source
    assert "find_grounded_opinion_response_violations" in provider_source

    print("PASS: B25 research relevance + ambiguity integrity")


if __name__ == "__main__":
    run()
