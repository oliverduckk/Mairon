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


import tools.gmail_tools as gmail_tools
import tools.tool_registry as tool_registry


def run():
    # --------------------------------------------------
    # 1. Exact Gmail windows use epoch after:/before: boundaries
    #    and NEVER widen to 30 days.
    # --------------------------------------------------

    captured_queries = []

    original_search_emails = (
        gmail_tools.search_emails
    )

    def fake_search_emails(
        query,
        max_results=10,
    ):
        captured_queries.append(
            query
        )

        return {
            "success": True,
            "gmail_query": query,
            "email_count": 0,
            "emails": [],
        }

    gmail_tools.search_emails = (
        fake_search_emails
    )

    try:
        result = gmail_tools.find_emails(
            search_text="Prosple",
            days=2,
            unread_only=False,
            max_results=10,
            after_epoch=1000,
            before_epoch=2000,
            expand_search=False,
        )

    finally:
        gmail_tools.search_emails = (
            original_search_emails
        )

    assert result["success"] is True
    assert result["search_expanded"] is False
    assert result["search_strategy"] == (
        "exact_window_exhausted"
    )

    assert len(
        captured_queries
    ) == 2

    assert captured_queries[
        0
    ] == (
        'after:1000 before:2000 "Prosple"'
    )

    assert captured_queries[
        1
    ] == (
        "after:1000 before:2000 Prosple"
    )

    assert all(
        "newer_than:30d"
        not in query
        for query in captured_queries
    )

    # --------------------------------------------------
    # 2. Rolling search behaviour is preserved.
    # --------------------------------------------------

    captured_queries.clear()

    gmail_tools.search_emails = (
        fake_search_emails
    )

    try:
        rolling = gmail_tools.find_emails(
            search_text="Prosple",
            days=2,
            unread_only=False,
            max_results=10,
        )

    finally:
        gmail_tools.search_emails = (
            original_search_emails
        )

    assert rolling["success"] is True

    assert any(
        'newer_than:2d "Prosple"'
        == query
        for query in captured_queries
    )

    assert any(
        'newer_than:30d "Prosple"'
        == query
        for query in captured_queries
    )

    # --------------------------------------------------
    # 3. tool_registry forwards exact-window arguments.
    # --------------------------------------------------

    forwarded = {}

    original_registry_find = (
        tool_registry.find_emails
    )

    def fake_registry_find(
        search_text="",
        days=30,
        unread_only=False,
        max_results=10,
        after_epoch=None,
        before_epoch=None,
        expand_search=True,
    ):
        forwarded.update({
            "search_text": search_text,
            "days": days,
            "unread_only": unread_only,
            "max_results": max_results,
            "after_epoch": after_epoch,
            "before_epoch": before_epoch,
            "expand_search": expand_search,
        })

        return {
            "success": True,
            "email_count": 0,
            "emails": [],
        }

    tool_registry.find_emails = (
        fake_registry_find
    )

    try:
        tool_registry.execute_tool(
            "find_emails",
            {
                "search_text": "Prosple",
                "days": 2,
                "unread_only": False,
                "max_results": 10,
                "after_epoch": 1000,
                "before_epoch": 2000,
                "expand_search": False,
            },
        )

    finally:
        tool_registry.find_emails = (
            original_registry_find
        )

    assert forwarded == {
        "search_text": "Prosple",
        "days": 2,
        "unread_only": False,
        "max_results": 10,
        "after_epoch": 1000,
        "before_epoch": 2000,
        "expand_search": False,
    }

    print(
        "Gmail exact-window plumbing regression tests: PASS"
    )


if __name__ == "__main__":
    run()
