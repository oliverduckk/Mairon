import re
from typing import Any, Dict, Optional

from core.evidence import (
    Evidence,
    EvidenceBundle,
)
from core.workflow_result import (
    WorkflowResult,
)
from tools.tool_registry import (
    execute_tool,
)


def _clean(
    value: Any,
) -> str:
    return " ".join(
        str(
            value
            or ""
        ).strip().split()
    )


def _email_value(
    email: Dict[str, Any],
    *keys: str,
) -> Optional[str]:
    for key in keys:
        value = _clean(
            email.get(
                key
            )
        )

        if value:
            return value

    return None


def _compact_verified_body_for_generation(
    body: str,
    char_budget: int = 4000,
) -> str:
    """
    Build a compact, source-faithful Gmail body view for model generation.

    The authoritative raw body is retained separately in Evidence.data and the
    WorkflowResult. This helper only reduces transport/marketing noise in the
    text supplied to the personality model.
    """

    raw = str(
        body
        or ""
    )

    lines = []

    for raw_line in raw.splitlines():
        line = str(
            raw_line
            or ""
        ).strip()

        if not line:
            continue

        # Standalone tracking/navigation URLs add tokens but little useful text.
        if re.fullmatch(
            r"\(?\s*https?://\S+\s*\)?",
            line,
            flags=re.IGNORECASE,
        ):
            continue

        # Decorative newsletter separators.
        if re.fullmatch(
            r"[*=_#~\-]{5,}",
            line,
        ):
            continue

        # Keep visible anchor text while removing parenthesised URLs.
        line = re.sub(
            r"\s*\(\s*https?://[^)]+\)",
            "",
            line,
            flags=re.IGNORECASE,
        ).strip()

        # Remove remaining bare URLs.
        line = re.sub(
            r"https?://\S+",
            "",
            line,
            flags=re.IGNORECASE,
        ).strip()

        line = re.sub(
            r"\s+",
            " ",
            line,
        ).strip()

        if not line:
            continue

        # Consecutive duplicate marketing/template lines add no evidence.
        if (
            lines
            and line == lines[
                -1
            ]
        ):
            continue

        lines.append(
            line
        )

    compact = []
    used = 0

    for line in lines:
        addition = len(
            line
        ) + (
            1
            if compact
            else 0
        )

        if (
            compact
            and used + addition > char_budget
        ):
            break

        compact.append(
            line
        )

        used += addition

    result = "\n".join(
        compact
    ).strip()

    if not result:
        # Never replace verified source text with invented content.
        result = raw.strip()[
            :char_budget
        ]

    if len(
        compact
    ) < len(
        lines
    ):
        result += (
            "\n[Verified email body compacted for generation.]"
        )

    return result



def read_selected_email(
    message_id: str,
) -> WorkflowResult:
    """
    Read exactly one Gmail message selected by Mairon Core.

    Selection authority belongs to Core. The model receives only the verified
    resulting email evidence and is free to summarise/explain it, but it does
    not choose a different Gmail message or reconstruct contents from prior
    assistant prose.
    """

    message_id = _clean(
        message_id
    )

    if not message_id:
        return WorkflowResult(
            success=False,
            status="missing_message_id",
            error=(
                "A specific Gmail message must be selected before it can be read."
            ),
        )

    result = execute_tool(
        "read_email",
        {
            "message_id": message_id,
        },
    )

    if not isinstance(
        result,
        dict,
    ):
        return WorkflowResult(
            success=False,
            status="unexpected_tool_result",
            error=(
                "Gmail returned an unexpected result while reading the email."
            ),
            data={
                "message_id": message_id,
            },
        )

    if result.get(
        "success"
    ) is not True:
        return WorkflowResult(
            success=False,
            status="gmail_read_failed",
            error=(
                result.get(
                    "message"
                )
                or "Gmail could not read that email."
            ),
            data={
                "message_id": message_id,
            },
        )

    email = result.get(
        "email"
    )

    if not isinstance(
        email,
        dict,
    ):
        return WorkflowResult(
            success=False,
            status="missing_email_payload",
            error=(
                "Gmail reported success but did not return the selected email."
            ),
            data={
                "message_id": message_id,
            },
        )

    body = str(
        email.get(
            "body"
        )
        or ""
    ).strip()

    subject = (
        _email_value(
            email,
            "subject",
        )
        or "(No subject)"
    )

    sender = (
        _email_value(
            email,
            "from",
            "sender",
            "from_address",
        )
        or "Unknown sender"
    )

    date = (
        _email_value(
            email,
            "date",
            "received_at",
        )
        or "Unknown date"
    )

    if not body:
        return WorkflowResult(
            success=False,
            status="email_body_unavailable",
            error=(
                "I found that email, but Gmail didn't return a readable plain-text body."
            ),
            data={
                "message_id": message_id,
                "subject": subject,
                "sender": sender,
                "date": date,
            },
        )

    evidence = EvidenceBundle(
        authority="gmail",
        success=True,
    )

    compact_body = (
        _compact_verified_body_for_generation(
            body
        )
    )

    # AnswerContract renders Evidence.claim to the model. Supply a compact,
    # source-faithful generation view there. Evidence.data and WorkflowResult
    # still retain the complete authoritative Gmail body.
    evidence.add(
        Evidence(
            claim=(
                "Verified Gmail message contents:\n"
                f"From: {sender}\n"
                f"Subject: {subject}\n"
                f"Date: {date}\n"
                "Body:\n"
                f"{compact_body}"
            ),
            provenance="gmail",
            confidence="verified",
            source_name=subject,
            source_id=message_id,
            observed_at=date,
            data={
                "sender": sender,
                "subject": subject,
                "date": date,
                "body": body,
            },
        )
    )

    return WorkflowResult(
        success=True,
        status="email_read",
        evidence=evidence,
        data={
            "message_id": message_id,
            "sender": sender,
            "subject": subject,
            "date": date,
            "body": body,
        },
    )
