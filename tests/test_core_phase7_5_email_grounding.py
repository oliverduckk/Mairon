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


from core.evidence import (
    Evidence,
    EvidenceBundle,
)
from core.workflow_result import (
    WorkflowResult,
)
import core.orchestrator as orchestrator_module
from core.orchestrator import (
    MaironCore,
)
from ai import ollama_provider


def _search_result():
    evidence = EvidenceBundle(
        authority="gmail",
        success=True,
    )

    evidence.add(
        Evidence(
            claim=(
                'Gmail returned a matching email summary: '
                '"Policy update" from Example Payments'
            ),
            provenance="gmail",
            confidence="verified",
            source_name="Policy update",
            source_id="msg-1",
            observed_at="Wed, 02 Sep 2026 10:00:00 +1000",
            data={
                "search_text": "Example Payments",
                "time_scope": "yesterday",
                "subject": "Policy update",
                "sender": "Example Payments",
            },
        )
    )

    return WorkflowResult(
        success=True,
        status="match_found",
        answer_fact=(
            'Yep — I found an email matching Example Payments yesterday: '
            '"Policy update" from Example Payments.'
        ),
        evidence=evidence,
        data={
            "search_text": "Example Payments",
            "days": 2,
            "time_scope": "yesterday",
            "matched_messages": 1,
        },
    )


def _read_result():
    evidence = EvidenceBundle(
        authority="gmail",
        success=True,
    )

    evidence.add(
        Evidence(
            claim=(
                "Verified Gmail message contents:\n"
                "From: Example Payments\n"
                "Subject: Policy update\n"
                "Body:\n"
                "We are updating our legal agreements. No action is required."
            ),
            provenance="gmail",
            confidence="verified",
            source_name="Policy update",
            source_id="msg-1",
            data={
                "body": (
                    "We are updating our legal agreements. "
                    "No action is required."
                ),
            },
        )
    )

    return WorkflowResult(
        success=True,
        status="email_read",
        evidence=evidence,
        data={
            "message_id": "msg-1",
            "subject": "Policy update",
            "body": (
                "We are updating our legal agreements. "
                "No action is required."
            ),
        },
    )


def run():
    # --------------------------------------------------
    # 1. Markdown emphasis cannot bypass recommendation prohibition.
    # --------------------------------------------------

    from core.answer_contract_runtime import (
        AnswerContractRuntime,
    )

    contract = AnswerContractRuntime(
        task="respond",
        speech_act="question",
        intent="email_read",
        subject="selected Gmail message",
        authority="gmail",
        epistemic_mode="tool_verified",
        allow_recommendations=False,
        allow_new_factual_claims=False,
        allow_follow_up_question=False,
        source="structured",
    )

    draft = (
        "No action is required, though you *should* check the policy page."
    )

    violations = (
        ollama_provider
        .find_forbidden_recommendation_violations(
            response_text=draft,
            core_answer_contract=contract,
        )
    )

    assert violations

    # --------------------------------------------------
    # 2. Action follow-up about active email re-enters Gmail evidence lane.
    # --------------------------------------------------

    original_search = (
        orchestrator_module.search_email
    )

    original_read = (
        orchestrator_module.read_selected_email
    )

    search_calls = []
    read_calls = []

    try:
        def fake_search_email(
            search_text,
            days=30,
            max_results=10,
            time_scope="rolling_days",
            now=None,
        ):
            search_calls.append(
                (
                    search_text,
                    time_scope,
                )
            )
            return _search_result()

        def fake_read_selected_email(
            message_id,
        ):
            read_calls.append(
                message_id
            )
            return _read_result()

        orchestrator_module.search_email = fake_search_email
        orchestrator_module.read_selected_email = fake_read_selected_email

        core = MaironCore()

        first = core.prepare_turn(
            "What did the email from Example Payments yesterday say?"
        )

        assert first.turn.intent == "email_read"
        assert read_calls == [
            "msg-1"
        ]

        follow = core.prepare_turn(
            "Do I need to do anything about it?"
        )

        assert follow.turn.intent == "email_read"
        assert (
            follow.turn.entities[
                "email_read_purpose"
            ]
            == "action_assessment"
        )

        # It reads the verified Gmail message again instead of treating
        # Mairon's previous generated summary as factual authority.
        assert read_calls == [
            "msg-1",
            "msg-1",
        ]

        assert (
            follow.answer_contract
            .allow_recommendations
            is True
        )

        rendered = (
            follow.answer_contract
            .to_model_instruction()
        )

        assert "No action is required." in rendered

    finally:
        orchestrator_module.search_email = original_search
        orchestrator_module.read_selected_email = original_read

    # --------------------------------------------------
    # 3. Structured triage parser requires every index exactly once.
    # --------------------------------------------------

    valid = (
        ollama_provider
        ._parse_inbox_triage_classification(
            '{"items":['
            '{"index":1,"category":"FYI"},'
            '{"index":2,"category":"ACTION"}'
            ']}',
            expected_count=2,
        )
    )

    assert valid == {
        1: "FYI",
        2: "ACTION",
    }

    assert (
        ollama_provider
        ._parse_inbox_triage_classification(
            '{"items":[{"index":1,"category":"FYI"}]}',
            expected_count=2,
        )
        is None
    )

    # --------------------------------------------------
    # 4. Core rendering owns subjects/counts and has no timestamps to distort.
    # --------------------------------------------------

    items = [
        {
            "index": 1,
            "sender": "Sender A",
            "subject": "Settings changed",
            "snippet": "A setting was changed",
            "unread": False,
        },
        {
            "index": 2,
            "sender": "Sender B",
            "subject": "Job recommendations",
            "snippet": "Recommended roles",
            "unread": True,
        },
    ]

    answer = (
        ollama_provider
        ._format_inbox_triage_answer(
            items=items,
            categories={
                1: "ACTION",
                2: "IGNORE",
            },
            window_label="today",
        )
    )

    assert "1 email looks actionable" in answer
    assert "Settings changed — Sender A" in answer
    assert "Job recommendations — Sender B" in answer
    assert "morning" not in answer.lower()
    assert "night" not in answer.lower()

    print(
        "Mairon Phase 7.5 Gmail evidence-followup / "
        "structured-triage grounding tests: PASS"
    )


if __name__ == "__main__":
    run()
