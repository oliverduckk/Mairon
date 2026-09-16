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


from core.conversational_research import (
    build_contextual_opinion_research_query,
    normalise_public_research_query,
)


def run():
    # --------------------------------------------------
    # 1. Conversational wrappers should not pollute public-search identity.
    # --------------------------------------------------

    assert (
        normalise_public_research_query(
            "are we keen for the Natsuki Subaru episode tonight?"
        )
        == "Natsuki Subaru episode tonight"
    )

    assert (
        normalise_public_research_query(
            "bro can you tell me the latest NVIDIA driver?"
        )
        == "latest NVIDIA driver"
    )

    assert (
        normalise_public_research_query(
            "anyway why does my monitor sometimes flicker when VRR is on?"
        )
        == "why does my monitor sometimes flicker when VRR is on"
    )

    assert (
        normalise_public_research_query(
            "anyway explain why TCP needs a handshake"
        )
        == "explain why TCP needs a handshake"
    )

    assert (
        normalise_public_research_query(
            (
                "what was that Natsuki Subaru episode from September 9 "
                "everyone was talking about?"
            )
        )
        == "Natsuki Subaru episode from September 9"
    )

    # --------------------------------------------------
    # 2. Oliver's reaction is useful conversation context but usually poor
    #    search identity. Preserve the subject/event; remove the reaction tail.
    # --------------------------------------------------

    assert (
        normalise_public_research_query(
            (
                "Marin's handling of the final vote in ABCD "
                "is already pissing me off"
            )
        )
        == "Marin final vote in ABCD"
    )

    contextual = (
        build_contextual_opinion_research_query(
            user_input=(
                "do you think she handled it well though?"
            ),
            previous_user_text=(
                "Marin's handling of the final vote in ABCD "
                "is already pissing me off"
            ),
            subject="Marin",
        )
    )

    assert contextual == "Marin final vote in ABCD"

    # --------------------------------------------------
    # 3. Ordinary factual queries retain their factual identity.
    # --------------------------------------------------

    assert (
        normalise_public_research_query(
            "Who is the current CEO of AMD?"
        )
        == "Who is the current CEO of AMD"
    )

    # --------------------------------------------------
    # 4. Public research must use the normaliser while retaining the original
    #    wording for freshness/forecast interpretation.
    # --------------------------------------------------

    public_research_source = (
        PROJECT_ROOT
        / "src"
        / "research"
        / "public_factual_research.py"
    ).read_text(
        encoding="utf-8",
    )

    assert (
        "normalise_public_research_query"
        in public_research_source
    )

    assert (
        '"original_query": original_query'
        in public_research_source
    )

    # --------------------------------------------------
    # 5. Provider logs the actual bounded search query so failed research is
    #    diagnosable without exposing source bodies or hidden reasoning.
    # --------------------------------------------------

    provider_source = (
        PROJECT_ROOT
        / "src"
        / "ai"
        / "ollama_provider.py"
    ).read_text(
        encoding="utf-8",
    )

    assert (
        "[Research] Query: "
        in provider_source
    )

    # --------------------------------------------------
    # 6. Benchmark report captures only a filtered safe runtime trace.
    # --------------------------------------------------

    benchmark_runner_source = (
        PROJECT_ROOT
        / "benchmarks"
        / "run_conversational_intelligence.py"
    ).read_text(
        encoding="utf-8",
    )

    assert (
        "SAFE_RUNTIME_TRACE_PREFIXES"
        in benchmark_runner_source
    )
    assert (
        "contextlib.redirect_stdout"
        in benchmark_runner_source
    )
    assert (
        '"runtime_trace": list('
        in benchmark_runner_source
    )
    assert (
        "<summary>Safe runtime trace</summary>"
        in benchmark_runner_source
    )

    print(
        "Mairon Phase 11.2.4 research-query precision and benchmark-trace tests: PASS"
    )


if __name__ == "__main__":
    run()
