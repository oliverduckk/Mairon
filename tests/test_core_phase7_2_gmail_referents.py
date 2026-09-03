import ast
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
from core.conversation_state import (
    ConversationState,
)
from core.intent_router import (
    classify_turn,
)
import core.orchestrator as orchestrator_module
from core.orchestrator import (
    MaironCore,
)
from core.workflows import email_read


def _search_result(
    search_text,
    time_scope,
    message_id,
    subject,
    sender,
):
    evidence = EvidenceBundle(
        authority="gmail",
        success=True,
    )

    evidence.add(
        Evidence(
            claim=(
                f'Gmail returned a matching email summary: "{subject}" '
                f"from {sender}"
            ),
            provenance="gmail",
            confidence="verified",
            source_name=subject,
            source_id=message_id,
            observed_at="Wed, 02 Sep 2026 01:37:25 -0700",
            data={
                "search_text": search_text,
                "time_scope": time_scope,
                "subject": subject,
                "sender": sender,
            },
        )
    )

    return WorkflowResult(
        success=True,
        status="match_found",
        answer_fact=(
            f"Yep — I found an email matching {search_text} {time_scope}: "
            f'"{subject}" from {sender}.'
        ),
        evidence=evidence,
        data={
            "search_text": search_text,
            "days": 2,
            "time_scope": time_scope,
            "matched_messages": 1,
            "most_recent_subject": subject,
            "most_recent_sender": sender,
        },
    )


def run():
    # --------------------------------------------------
    # 1. ConversationState preserves Gmail referents independently
    #    from generic active_intent.
    # --------------------------------------------------

    state = ConversationState()

    search_turn = classify_turn(
        "Did I receive an email from ExampleCorp yesterday?",
        conversation_state=state,
    )

    result = _search_result(
        search_text="ExampleCorp",
        time_scope="yesterday",
        message_id="example-1",
        subject="Account update",
        sender="ExampleCorp <mail@example.com>",
    )

    state.remember_email_search_result(
        turn=search_turn,
        workflow_result=result,
    )

    state.update_from_turn(
        search_turn
    )

    # An unrelated Gmail workflow becomes generic active state.
    triage_turn = classify_turn(
        "Which emails from today need my attention?",
        conversation_state=state,
    )

    assert triage_turn.intent == "inbox_attention"

    state.update_from_turn(
        triage_turn
    )

    assert state.active_intent == "inbox_attention"

    preserved = state.resolve_single_email_message(
        target="ExampleCorp",
        allow_bare=False,
    )

    assert preserved is not None
    assert preserved["message_id"] == "example-1"

    # Bare deixis after an intervening inbox review is intentionally NOT
    # guessed from the older targeted context.
    assert (
        state.resolve_single_email_message(
            target=None,
            allow_bare=True,
        )
        is None
    )

    # --------------------------------------------------
    # 2. Explicit body-read request resolves the old verified target
    #    even though inbox_attention is now the generic active intent.
    # --------------------------------------------------

    read_turn = classify_turn(
        "What did that ExampleCorp email actually say?",
        conversation_state=state,
    )

    assert read_turn.intent == "email_read"
    assert read_turn.entities["search_text"] == "ExampleCorp"
    assert read_turn.entities["message_id"] == "example-1"
    assert read_turn.is_follow_up is True

    # --------------------------------------------------
    # 3. Core reuses the verified message_id instead of re-searching Gmail.
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
                    days,
                    time_scope,
                )
            )

            return _search_result(
                search_text=search_text,
                time_scope=time_scope,
                message_id="example-1",
                subject="Account update",
                sender="ExampleCorp <mail@example.com>",
            )

        def fake_read_selected_email(
            message_id,
        ):
            read_calls.append(
                message_id
            )

            evidence = EvidenceBundle(
                authority="gmail",
                success=True,
            )

            evidence.add(
                Evidence(
                    claim=(
                        "Verified Gmail message contents:\n"
                        "From: ExampleCorp <mail@example.com>\n"
                        "Subject: Account update\n"
                        "Date: Wed, 02 Sep 2026 01:37:25 -0700\n"
                        "Body:\n"
                        "We are updating our terms next month. "
                        "No action is required."
                    ),
                    provenance="gmail",
                    confidence="verified",
                    source_name="Account update",
                    source_id=message_id,
                    data={
                        "body": (
                            "We are updating our terms next month. "
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
                    "message_id": message_id,
                    "subject": "Account update",
                    "body": (
                        "We are updating our terms next month. "
                        "No action is required."
                    ),
                },
            )

        orchestrator_module.search_email = (
            fake_search_email
        )

        orchestrator_module.read_selected_email = (
            fake_read_selected_email
        )

        core = MaironCore()

        first = core.prepare_turn(
            "Did I receive an email from ExampleCorp yesterday?"
        )

        assert first.turn.intent == "email_search"
        assert first.direct_response is not None
        assert search_calls == [
            (
                "ExampleCorp",
                2,
                "yesterday",
            )
        ]

        # Intervening triage changes generic active_intent. Provider would
        # execute the actual triage; Core state update still happens here.
        middle = core.prepare_turn(
            "Which emails from today need my attention?"
        )

        assert middle.turn.intent == "inbox_attention"
        assert (
            core.conversation_state.active_intent
            == "inbox_attention"
        )

        detail = core.prepare_turn(
            "What did that ExampleCorp email actually say?"
        )

        assert detail.turn.intent == "email_read"

        # No second search: Core reused the stored verified Gmail message ID.
        assert len(search_calls) == 1
        assert read_calls == [
            "example-1"
        ]

        assert detail.direct_response is None
        assert detail.workflow_result.success is True
        assert detail.answer_contract.allow_new_factual_claims is False
        assert detail.answer_contract.allow_follow_up_question is False

        rendered = (
            detail.answer_contract.to_model_instruction()
        )

        assert "Verified Gmail message contents:" in rendered
        assert "No action is required." in rendered
        assert "ExampleCorp" in rendered

    finally:
        orchestrator_module.search_email = (
            original_search
        )

        orchestrator_module.read_selected_email = (
            original_read
        )

    # --------------------------------------------------
    # 4. If no prior referent exists, a named read request performs
    #    search -> unique message selection -> read in the SAME turn.
    # --------------------------------------------------

    search_calls.clear()
    read_calls.clear()

    try:
        orchestrator_module.search_email = (
            fake_search_email
        )

        orchestrator_module.read_selected_email = (
            fake_read_selected_email
        )

        fresh_core = MaironCore()

        decision = fresh_core.prepare_turn(
            "What did the email from ExampleCorp yesterday say?"
        )

        assert decision.turn.intent == "email_read"
        assert search_calls == [
            (
                "ExampleCorp",
                2,
                "yesterday",
            )
        ]
        assert read_calls == [
            "example-1"
        ]
        assert decision.direct_response is None

    finally:
        orchestrator_module.search_email = (
            original_search
        )

        orchestrator_module.read_selected_email = (
            original_read
        )

    # --------------------------------------------------
    # 5. The low-level read workflow exposes actual Gmail BODY text
    #    as verified model-visible evidence, not only Evidence.data.
    # --------------------------------------------------

    original_execute = (
        email_read.execute_tool
    )

    try:
        def fake_execute_tool(
            tool_name,
            arguments,
        ):
            assert tool_name == "read_email"
            assert arguments == {
                "message_id": "body-1"
            }

            return {
                "success": True,
                "email": {
                    "message_id": "body-1",
                    "from": "Sender <sender@example.com>",
                    "subject": "Important details",
                    "date": "Thu, 03 Sep 2026 10:00:00 +1000",
                    "body": "This is the actual verified email body.",
                },
            }

        email_read.execute_tool = (
            fake_execute_tool
        )

        body_result = (
            email_read.read_selected_email(
                "body-1"
            )
        )

        assert body_result.success is True

        claim = (
            body_result
            .evidence
            .evidence[0]
            .claim
        )

        assert (
            "This is the actual verified email body."
            in claim
        )

    finally:
        email_read.execute_tool = (
            original_execute
        )

    # --------------------------------------------------
    # 6. Production code is semantic, not benchmark-specific.
    # --------------------------------------------------

    def executable_string_literals(
        path,
    ):
        """
        Collect runtime string constants while excluding docstrings.

        Architecture guards should detect benchmark-specific executable logic,
        not fail because a developer comment/docstring explains the scenario
        that motivated a general mechanism.
        """

        tree = ast.parse(
            path.read_text(
                encoding="utf-8"
            )
        )

        values = []

        def visit_body(
            body,
        ):
            start = 0

            if (
                body
                and isinstance(
                    body[0],
                    ast.Expr,
                )
                and isinstance(
                    body[0].value,
                    ast.Constant,
                )
                and isinstance(
                    body[0].value.value,
                    str,
                )
            ):
                # Module/class/function docstring.
                start = 1

            for node in body[
                start:
            ]:
                visit_node(
                    node
                )

        def visit_node(
            node,
        ):
            if isinstance(
                node,
                (
                    ast.Module,
                    ast.FunctionDef,
                    ast.AsyncFunctionDef,
                    ast.ClassDef,
                ),
            ):
                visit_body(
                    node.body
                )

                # Function decorators/defaults/annotations are executable-ish
                # metadata and should still be checked.
                if isinstance(
                    node,
                    (
                        ast.FunctionDef,
                        ast.AsyncFunctionDef,
                    ),
                ):
                    for extra in (
                        list(
                            node.decorator_list
                        )
                        + list(
                            node.args.defaults
                        )
                        + [
                            item
                            for item in (
                                node.returns,
                            )
                            if item is not None
                        ]
                    ):
                        visit_node(
                            extra
                        )

                return

            if (
                isinstance(
                    node,
                    ast.Constant,
                )
                and isinstance(
                    node.value,
                    str,
                )
            ):
                values.append(
                    node.value.lower()
                )

            for child in ast.iter_child_nodes(
                node
            ):
                visit_node(
                    child
                )

        visit_node(
            tree
        )

        return values

    runtime_strings = []

    for path in (
        SRC_DIR / "core" / "conversation_state.py",
        SRC_DIR / "core" / "intent_router.py",
        SRC_DIR / "core" / "orchestrator.py",
    ):
        runtime_strings.extend(
            executable_string_literals(
                path
            )
        )

    runtime_blob = "\n".join(
        runtime_strings
    )

    for forbidden in (
        "paypal email actually say",
        "paypal yesterday",
        "espn fantasy games",
        "prosple job",
        "4.37s",
        "6.51s",
    ):
        assert forbidden not in runtime_blob

    print(
        "Mairon Phase 7.2 Gmail referent persistence / "
        "verified body-read tests: PASS"
    )


if __name__ == "__main__":
    run()
