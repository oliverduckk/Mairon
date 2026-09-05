import sys
from pathlib import Path
from types import SimpleNamespace


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


import application_service as service_module

from application_service import (
    MaironApplication,
)


class FakeCore:
    def prepare_turn(
        self,
        user_text,
    ):
        return SimpleNamespace(
            turn=SimpleNamespace(
                intent="test_direct",
            ),
            epistemic_route=SimpleNamespace(
                authority="core_test",
                mode="deterministic",
            ),
            needs_clarification=False,
            clarification_question=None,
            direct_response=(
                "Core direct response."
            ),
            answer_contract=None,
        )


def run():
    # --------------------------------------------------
    # 1. Direct Core responses work without a UI or live provider.
    # --------------------------------------------------

    original_record = (
        service_module
        .record_conversation_turn
    )

    original_append = (
        service_module
        .append_visible_turn_to_model_history
    )

    original_capture = (
        service_module
        .capture_user_preference
    )

    original_recall = (
        service_module
        .build_user_preference_recall_response
    )

    journal_calls = []

    try:
        service_module.record_conversation_turn = (
            lambda **kwargs: journal_calls.append(
                dict(
                    kwargs
                )
            )
        )

        service_module.append_visible_turn_to_model_history = (
            lambda **kwargs: {
                "history": [
                    kwargs[
                        "user_input"
                    ],
                    kwargs[
                        "assistant_text"
                    ],
                ]
            }
        )

        service_module.capture_user_preference = (
            lambda **kwargs: None
        )

        service_module.build_user_preference_recall_response = (
            lambda **kwargs: None
        )

        app = MaironApplication(
            user_name="Oliver",
            local_ai=None,
            cloud_ai=None,
            core=FakeCore(),
            create_providers=False,
        )

        result = app.submit_text(
            "test direct"
        )

        assert result.status == (
            "answered"
        )

        assert result.answer == (
            "Core direct response."
        )

        assert result.intent == (
            "test_direct"
        )

        assert result.authority == (
            "core_test"
        )

        assert (
            result.response_seconds
            is not None
        )

        assert app.last_user_input == (
            "test direct"
        )

        assert app.last_assistant_answer == (
            "Core direct response."
        )

        assert len(
            journal_calls
        ) == 1

        assert journal_calls[
            0
        ][
            "channel"
        ] == "text"

    finally:
        service_module.record_conversation_turn = (
            original_record
        )

        service_module.append_visible_turn_to_model_history = (
            original_append
        )

        service_module.capture_user_preference = (
            original_capture
        )

        service_module.build_user_preference_recall_response = (
            original_recall
        )

    # --------------------------------------------------
    # 2. Pending approvals block unrelated new input until resolved.
    # --------------------------------------------------

    original_route = (
        service_module.route_message
    )

    original_capture = (
        service_module
        .capture_user_preference
    )

    original_recall = (
        service_module
        .build_user_preference_recall_response
    )

    original_record = (
        service_module
        .record_conversation_turn
    )

    class ConversationCore:
        def prepare_turn(
            self,
            user_text,
        ):
            return SimpleNamespace(
                turn=SimpleNamespace(
                    intent=(
                        "casual_conversation"
                    ),
                ),
                epistemic_route=SimpleNamespace(
                    authority=(
                        "conversation_model"
                    ),
                    mode="conversation",
                ),
                needs_clarification=False,
                clarification_question=None,
                direct_response=None,
                answer_contract=SimpleNamespace(
                    to_model_instruction=(
                        lambda: "test contract"
                    )
                ),
            )

    try:
        service_module.capture_user_preference = (
            lambda **kwargs: None
        )

        service_module.build_user_preference_recall_response = (
            lambda **kwargs: None
        )

        service_module.record_conversation_turn = (
            lambda **kwargs: None
        )

        service_module.route_message = (
            lambda *args, **kwargs: SimpleNamespace(
                status=(
                    "cloud_approval_required"
                ),
                answer=None,
                reason="test reason",
                pending_prompt="test cloud",
                pending_action=None,
                local_state="local-state",
                cloud_state="cloud-state",
            )
        )

        app = MaironApplication(
            user_name="Oliver",
            local_ai={
                "client": object(),
                "module": object(),
            },
            cloud_ai={
                "client": object(),
                "module": object(),
            },
            core=ConversationCore(),
            create_providers=False,
        )

        pending = app.submit_text(
            "test cloud"
        )

        assert pending.status == (
            "cloud_approval_required"
        )

        assert app.has_pending_approval is True

        blocked = app.submit_text(
            "another request"
        )

        assert blocked.status == (
            "pending_approval_exists"
        )

    finally:
        service_module.route_message = (
            original_route
        )

        service_module.capture_user_preference = (
            original_capture
        )

        service_module.build_user_preference_recall_response = (
            original_recall
        )

        service_module.record_conversation_turn = (
            original_record
        )

    print(
        "Mairon Phase 10.1 application-service tests: PASS"
    )


if __name__ == "__main__":
    run()
