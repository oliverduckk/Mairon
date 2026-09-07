from __future__ import annotations

import re
from typing import Optional


MAX_GENERATED_TITLE_LENGTH = 44
MAX_TITLE_WORDS = 7


def _clean_generated_title(
    value: str,
) -> Optional[str]:
    text = str(
        value
        or ""
    ).strip()

    if not text:
        return None

    # Models occasionally wrap the title despite being told not to.
    text = text.splitlines()[
        0
    ].strip()

    text = re.sub(
        r"^(?:title|chat title)\s*:\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )

    text = text.strip(
        " \"'`*_#"
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    ).strip()

    if not text:
        return None

    words = text.split()

    if len(
        words
    ) > MAX_TITLE_WORDS:
        text = " ".join(
            words[
                :MAX_TITLE_WORDS
            ]
        )

    if len(
        text
    ) > MAX_GENERATED_TITLE_LENGTH:
        text = text[
            :MAX_GENERATED_TITLE_LENGTH
        ].rstrip(
            " ,.!?:;-"
        )

    if len(
        text
    ) < 2:
        return None

    # Reject obvious instruction leakage / prose rather than forcing a bad
    # generated title into the sidebar.
    lowered = text.lower()

    bad_prefixes = (
        "here is",
        "here's",
        "sure",
        "the title",
        "a good title",
        "i would",
        "i'd",
    )

    if lowered.startswith(
        bad_prefixes
    ):
        return None

    return text


def generate_semantic_chat_title(
    *,
    local_ai,
    model_name: str,
    user_text: str,
    assistant_text: str,
) -> Optional[str]:
    """
    Generate one low-risk presentation title using an isolated local-model call.

    This call receives no Mairon conversation state, tools, memories, account
    data, Answer Contract, or prior chat history. Its output is UI metadata only
    and never becomes factual authority.
    """

    if not isinstance(
        local_ai,
        dict,
    ):
        return None

    client = local_ai.get(
        "client"
    )

    if client is None:
        return None

    model_value = str(
        model_name
        or ""
    ).strip()

    if not model_value:
        return None

    user_value = str(
        user_text
        or ""
    ).strip()

    assistant_value = str(
        assistant_text
        or ""
    ).strip()

    if not user_value:
        return None

    # A little answer context helps broad questions get topic-level names
    # without feeding the generator the entire session.
    if len(
        assistant_value
    ) > 900:
        assistant_value = (
            assistant_value[
                :900
            ]
        )

    if len(
        user_value
    ) > 700:
        user_value = (
            user_value[
                :700
            ]
        )

    messages = [
        {
            "role": "system",
            "content": (
                "Create a short sidebar title for a chat. "
                "Return ONLY the title and nothing else. "
                "Use 2 to 6 words normally. "
                "Describe the broad topic, like ChatGPT conversation titles. "
                "Do not copy the full user sentence. "
                "Do not use quotation marks, markdown, emojis, or a trailing period. "
                "Examples: 'Starlink Overview', 'Japan Trip Planning', "
                "'Minecraft Fortress Boundaries', 'Resume Review', "
                "'Home Internet Troubleshooting'."
            ),
        },
        {
            "role": "user",
            "content": (
                "FIRST USER MESSAGE:\n"
                + user_value
                + "\n\nFIRST ASSISTANT RESPONSE:\n"
                + assistant_value
            ),
        },
    ]

    try:
        response = client.chat(
            model=model_value,
            messages=messages,
            options={
                "temperature": 0.2,
                "num_predict": 24,
            },
        )

    except TypeError:
        # Older Ollama client versions may not accept options in this shape.
        try:
            response = client.chat(
                model=model_value,
                messages=messages,
            )

        except Exception:
            return None

    except Exception:
        return None

    try:
        raw = response.message.content

    except Exception:
        try:
            raw = response[
                "message"
            ][
                "content"
            ]

        except Exception:
            return None

    return _clean_generated_title(
        raw
    )
