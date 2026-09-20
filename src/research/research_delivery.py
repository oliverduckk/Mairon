from __future__ import annotations

from typing import Any, Optional


RESEARCH_DELIVERY_USER_PREFIX = (
    "__MAIRON_RESEARCH_DELIVERY__:"
)


def _normalise_space(
    value: Any,
) -> str:
    return " ".join(
        str(
            value
            or ""
        ).split()
    )


def research_delivery_turn_marker(
    job_id: Any,
) -> str:
    value = _normalise_space(
        job_id
    )

    if not value:
        raise ValueError(
            "research job id is required"
        )

    return (
        RESEARCH_DELIVERY_USER_PREFIX
        + value
    )


def is_research_delivery_turn(
    turn: Any,
) -> bool:
    if not isinstance(
        turn,
        dict,
    ):
        return False

    return str(
        turn.get(
            "user_text"
        )
        or ""
    ).startswith(
        RESEARCH_DELIVERY_USER_PREFIX
    )


def build_research_delivery_text(
    job: Any,
) -> Optional[str]:
    """
    Build the visible message from a VERIFIED persisted final report.

    No model is called here. Phase 11.5.4 already performed grounded synthesis
    and verification, so delivery must not paraphrase the report and introduce
    new unsupported factual claims.
    """

    if not isinstance(
        job,
        dict,
    ):
        return None

    if str(
        job.get(
            "status"
        )
        or ""
    ).strip().lower() != "completed":
        return None

    result = job.get(
        "result"
    )

    if not isinstance(
        result,
        dict,
    ):
        return None

    if (
        result.get(
            "user_ready"
        )
        is not True
        or result.get(
            "final_report_verified"
        )
        is not True
    ):
        return None

    # Phase 11.5.4 persists the verified report in two forms:
    # - final_report: structured metadata containing a ``text`` field;
    # - final_report_text: the exact verified presentation text.
    #
    # Delivery must never stringify the metadata dictionary itself. Doing so
    # exposes internal provenance/source structures instead of the report.
    report = str(
        result.get(
            "final_report_text"
        )
        or ""
    ).strip()

    final_report = result.get(
        "final_report"
    )

    if not report and isinstance(
        final_report,
        dict,
    ):
        report = str(
            final_report.get(
                "text"
            )
            or final_report.get(
                "report_text"
            )
            or ""
        ).strip()

    # Backward compatibility for any older build that stored final_report as
    # a plain string rather than the Phase 11.5.4 structured object.
    if (
        not report
        and isinstance(
            final_report,
            str,
        )
    ):
        report = final_report.strip()

    if not report:
        synthesis = result.get(
            "final_synthesis"
        )

        if isinstance(
            synthesis,
            dict,
        ):
            report = str(
                synthesis.get(
                    "report_text"
                )
                or ""
            ).strip()

    if not report:
        return None

    topic = _normalise_space(
        job.get(
            "topic"
        )
    )

    lead_in = (
        "Alright — I finished the background research"
        + (
            " on "
            + topic
            if topic
            else ""
        )
        + "."
    )

    return (
        lead_in
        + "\n\n"
        + report
    )


def append_research_delivery_to_model_history(
    *,
    current_state,
    assistant_text: str,
    system_instructions: Optional[str] = None,
):
    """
    Add a proactive Mairon delivery as an assistant-only history item.

    There is deliberately no synthetic Oliver message. The original request is
    already part of the conversation that created the job, and inventing a new
    user turn would corrupt conversational provenance.
    """

    if current_state is None:
        state = []

        if system_instructions:
            state.append({
                "role": "system",
                "content": str(
                    system_instructions
                ),
            })

    else:
        state = list(
            current_state
        )

    state.append({
        "role": "assistant",
        "content": str(
            assistant_text
            or ""
        ),
    })

    return state
