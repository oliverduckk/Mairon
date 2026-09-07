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


# Keep this regression self-contained. media_research only needs the registry's
# execute_tool symbol at import time; live calls are replaced with deterministic
# fakes below. This avoids importing Gmail/Calendar dependencies merely to test
# public-media research selection logic.
fake_registry = types.ModuleType(
    "tools.tool_registry"
)

def _unpatched_execute_tool(*args, **kwargs):
    raise AssertionError(
        "media research test used an unpatched execute_tool"
    )

fake_registry.execute_tool = (
    _unpatched_execute_tool
)

sys.modules.setdefault(
    "tools.tool_registry",
    fake_registry,
)

from research import media_research


def _spoiler_context():
    return {
        "title": "Lord of Mysteries",
        "profile": None,
        "must_ask_progress": False,
        "must_complete_progress": False,
        "must_confirm_latest": False,
        "progress_updated": False,
        "pending_question": None,
        "release_sensitive": False,
    }


def run():
    original_execute_tool = media_research.execute_tool

    try:
        calls = []

        def fake_execute_tool_success(
            tool_name,
            arguments,
        ):
            calls.append(
                (
                    tool_name,
                    dict(
                        arguments
                    ),
                )
            )

            if tool_name == "web_search":
                return {
                    "success": True,
                    "results": [
                        {
                            "title": "Best relevant source",
                            "url": "https://example.com/lotm",
                            "content": "Relevant synopsis result",
                            "score": 0.99,
                        },
                        {
                            "title": "Trusted publisher source",
                            "url": "https://yenpress.com/series/lord-of-mysteries",
                            "content": "Publisher result",
                            "score": 0.60,
                        },
                        {
                            "title": "Less relevant source",
                            "url": "https://example.org/other",
                            "content": "Other result",
                            "score": 0.50,
                        },
                    ],
                }

            if tool_name == "web_read":
                return {
                    "success": True,
                    "url": arguments[
                        "url"
                    ],
                    "content": "Readable grounded source content.",
                }

            raise AssertionError(
                "unexpected tool: "
                + str(
                    tool_name
                )
            )

        media_research.execute_tool = (
            fake_execute_tool_success
        )

        result = media_research.gather_media_research(
            user_input=(
                "can you provide me with a synopsis on Lord of Mysteries. "
                "Im thinking about reading it"
            ),
            spoiler_context=_spoiler_context(),
            max_reads=2,
        )

        assert result[
            "success"
        ] is True

        assert result[
            "search_result_count"
        ] == 3

        assert result[
            "selected_source_count"
        ] == 2

        assert result[
            "readable_source_count"
        ] == 2

        read_urls = [
            arguments[
                "url"
            ]
            for tool_name, arguments in calls
            if tool_name == "web_read"
        ]

        # Search relevance keeps the best result; provenance preference adds
        # one recognised publisher instead of globally re-sorting everything.
        assert read_urls == [
            "https://example.com/lotm",
            "https://yenpress.com/series/lord-of-mysteries",
        ]

        packet = (
            media_research.build_internal_research_packet(
                result
            )
        )

        assert "Best relevant source" in packet
        assert "Trusted publisher source" in packet

        # --------------------------------------------------
        # Failed webpage extraction is not evidence.
        # --------------------------------------------------

        def fake_execute_tool_failed_reads(
            tool_name,
            arguments,
        ):
            if tool_name == "web_search":
                return {
                    "success": True,
                    "results": [
                        {
                            "title": "Search result",
                            "url": "https://example.com/lotm",
                            "content": "Snippet only",
                            "score": 0.99,
                        },
                    ],
                }

            if tool_name == "web_read":
                return {
                    "success": False,
                    "message": "The webpage could not be extracted.",
                }

            raise AssertionError(
                "unexpected tool: "
                + str(
                    tool_name
                )
            )

        media_research.execute_tool = (
            fake_execute_tool_failed_reads
        )

        failed = media_research.gather_media_research(
            user_input="give me a synopsis of Lord of Mysteries",
            spoiler_context=_spoiler_context(),
            max_reads=2,
        )

        assert failed[
            "success"
        ] is False

        assert failed[
            "readable_source_count"
        ] == 0

        assert (
            "could be read successfully"
            in str(
                failed.get(
                    "failure_reason"
                )
            )
        )

        # A failed read must never be included in the evidence synthesis packet.
        failed_packet = (
            media_research.build_internal_research_packet(
                failed
            )
        )

        assert failed_packet == (
            "MEDIA RESEARCH RESULT:\n"
            "No readable public sources were retrieved."
        )

        # --------------------------------------------------
        # Grounded media turns do not expose the cloud escape hatch.
        # --------------------------------------------------

        provider_source = (
            SRC_DIR
            / "ai"
            / "ollama_provider.py"
        ).read_text(
            encoding="utf-8"
        )

        assert (
            "allow_cloud_escalation\n"
            "        and not research_evidence"
            in provider_source
        )

    finally:
        media_research.execute_tool = (
            original_execute_tool
        )

    print(
        "Mairon Phase 10.7.1 media-research reliability tests: PASS"
    )


if __name__ == "__main__":
    run()
