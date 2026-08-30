import json
import os
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from ollama import Client

from tools.tool_registry import TOOLS, execute_tool


MODEL = "qwen3:14b"

MAX_TOOL_ROUNDS = 12
MAX_INBOX_READS = 3


MAIRON_TIMEZONE = os.getenv(
    "MAIRON_TIMEZONE",
    "Australia/Sydney"
)

LOCAL_TIMEZONE = ZoneInfo(
    MAIRON_TIMEZONE
)


# --------------------------------------------------
# Client
# --------------------------------------------------

def create_client():
    return Client(
        host="http://localhost:11434"
    )


def convert_tools_for_ollama():
    ollama_tools = []

    for tool in TOOLS:
        ollama_tools.append({
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["parameters"]
            }
        })

    return ollama_tools


OLLAMA_ACTION_TOOLS = convert_tools_for_ollama()


def get_ollama_tool(tool_name):
    """
    Return one Ollama-formatted tool definition by name.
    """

    for tool in OLLAMA_ACTION_TOOLS:
        if (
            tool.get("function", {}).get("name")
            == tool_name
        ):
            return tool

    return None


READ_EMAIL_ONLY_TOOL = get_ollama_tool(
    "read_email"
)


# --------------------------------------------------
# Permission-request tools
# --------------------------------------------------

CLOUD_ESCALATION_TOOL = {
    "type": "function",
    "function": {
        "name": "request_cloud_escalation",
        "description": (
            "Request permission to use a more capable cloud AI model. "
            "Use this only when the user's request is genuinely beyond what you can "
            "confidently handle locally and cloud processing would materially improve "
            "the answer. Do not use this for ordinary factual questions, casual "
            "conversation, normal explanations, routine coding help, memory operations, "
            "device-control tasks, private email, private calendar data, or ordinary "
            "web research. Calling this tool does NOT access the cloud. "
            "It only asks Mairon Core to request permission from Oliver."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": (
                        "A short explanation of why cloud processing would materially "
                        "improve this particular request."
                    )
                }
            },
            "required": ["reason"],
            "additionalProperties": False
        }
    }
}


CALENDAR_EVENT_REQUEST_TOOL = {
    "type": "function",
    "function": {
        "name": "request_calendar_event_creation",
        "description": (
            "Request permission from Oliver to create a Google Calendar event. "
            "Calling this function DOES NOT create or modify anything. "
            "Mairon Core will show Oliver the exact proposed event and require "
            "explicit approval before performing the write. "
            "Use this when Oliver explicitly asks to add, create, schedule, or put "
            "an event on his calendar. "
            "Use ISO 8601 local date/time values. "
            "The current local date and time are supplied in your runtime context. "
            "If Oliver gives a start time but no duration, propose a 60-minute event."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Short calendar event title."
                },
                "start_time": {
                    "type": "string",
                    "description": (
                        "Proposed event start as ISO 8601 local date/time."
                    )
                },
                "end_time": {
                    "type": "string",
                    "description": (
                        "Proposed event end as ISO 8601 local date/time."
                    )
                },
                "location": {
                    "type": "string",
                    "description": (
                        "Event location if Oliver supplied one. "
                        "Otherwise use an empty string."
                    )
                },
                "description": {
                    "type": "string",
                    "description": (
                        "Event description if Oliver supplied one. "
                        "Otherwise use an empty string."
                    )
                }
            },
            "required": [
                "summary",
                "start_time",
                "end_time"
            ],
            "additionalProperties": False
        }
    }
}


# --------------------------------------------------
# Runtime context
# --------------------------------------------------

def get_runtime_context():
    """
    Give Qwen reliable local date/time information.
    """

    now = datetime.now(
        LOCAL_TIMEZONE
    )

    return (
        "Mairon runtime context: "
        f"The current local date and time is {now.isoformat()} "
        f"({now.strftime('%A')}) in timezone {MAIRON_TIMEZONE}. "
        "Use this when resolving relative dates and times."
    )


# --------------------------------------------------
# Requirement detection
# --------------------------------------------------

def explicitly_requires_web_read(
    user_input
):
    text = user_input.lower()

    read_phrases = [
        "read the source",
        "read the most relevant",
        "read an official",
        "read the official",
        "read the page",
        "read the webpage",
        "read the website",
        "open the source",
        "open the page",
        "open the webpage",
        "check the source",
        "check the official source",
        "check the page itself",
    ]

    return any(
        phrase in text
        for phrase in read_phrases
    )


def explicitly_requires_email_read(
    user_input
):
    text = user_input.lower()

    detail_phrases = [
        "tell me what",
        "what did the email",
        "what does the email",
        "what did it say",
        "what does it say",
        "what delivery method",
        "what shipping",
        "what did i order",
        "what size",
        "how much did",
        "how much was",
        "read the email",
        "read that email",
        "read the message",
        "full email",
        "full message",
        "email contents",
        "in the email",
        "from the email",
        "according to the email",
    ]

    return any(
        phrase in text
        for phrase in detail_phrases
    )


def is_inbox_attention_request(
    user_input
):
    """
    Detect inbox-review requests where Oliver wants Mairon
    to decide what is important or actionable.
    """

    text = user_input.lower()

    attention_phrases = [
        "need my attention",
        "needs my attention",
        "need attention",
        "needs attention",
        "important emails",
        "important email",
        "emails matter",
        "email matters",
        "need to act",
        "needs action",
        "need action",
        "action required",
        "actionable emails",
        "actionable email",
        "what should i respond",
        "what do i need to respond",
        "inbox brief",
        "inbox review",
    ]

    return any(
        phrase in text
        for phrase in attention_phrases
    )


def get_inbox_review_days(
    user_input
):
    """
    Resolve the requested inbox review window.

    Default is seven days.
    """

    text = user_input.lower()

    match = re.search(
        r"(?:last|past|previous)\s+(\d+)\s+days?",
        text
    )

    if match:
        return max(
            1,
            min(
                int(match.group(1)),
                90
            )
        )

    if "today" in text:
        return 1

    if (
        "last week" in text
        or "past week" in text
        or "this week" in text
    ):
        return 7

    if (
        "last month" in text
        or "past month" in text
    ):
        return 30

    return 7


# --------------------------------------------------
# Day-overview detection / workflow
# --------------------------------------------------

def is_day_overview_request(
    user_input
):
    """
    Detect questions asking what a day looks like overall.

    These requests should combine routine context with
    Calendar rather than relying on either source alone.
    """

    text = user_input.lower().strip()

    overview_phrases = [
        "what am i doing today",
        "what am i doing tomorrow",
        "what do i have today",
        "what do i have tomorrow",
        "what's happening today",
        "what's happening tomorrow",
        "what is happening today",
        "what is happening tomorrow",
        "what does today look like",
        "what does tomorrow look like",
        "what's my day today",
        "what's my day tomorrow",
        "what is my day today",
        "what is my day tomorrow",
        "what am i up to today",
        "what am i up to tomorrow",
    ]

    return any(
        phrase in text
        for phrase in overview_phrases
    )


def resolve_overview_date(
    user_input
):
    """
    Resolve today/tomorrow overview requests using
    Mairon's configured local timezone.
    """

    text = user_input.lower()

    today = datetime.now(
        LOCAL_TIMEZONE
    ).date()

    if "tomorrow" in text:
        target_date = (
            today
            + timedelta(
                days=1
            )
        )

        return {
            "date": target_date.isoformat(),
            "relative_name": "tomorrow",
            "calendar_period": "tomorrow",
        }

    return {
        "date": today.isoformat(),
        "relative_name": "today",
        "calendar_period": "today",
    }


def handle_day_overview_request(
    client,
    user_input,
    conversation
):
    """
    Build a deterministic view of today/tomorrow using
    both routine context and Google Calendar.

    Neither source is allowed to silently substitute
    for the other.
    """

    target = resolve_overview_date(
        user_input
    )

    date_string = target[
        "date"
    ]

    relative_name = target[
        "relative_name"
    ]

    calendar_period = target[
        "calendar_period"
    ]

    print(
        "[Core] Day overview: combining routine "
        f"and calendar for {date_string}."
    )

    print(
        "[Tool] Mairon Core required: get_routine_context"
    )

    routine_result = execute_tool(
        "get_routine_context",
        {
            "date": date_string
        }
    )

    print(
        "[Tool] Mairon Core required: get_calendar_events"
    )

    calendar_result = execute_tool(
        "get_calendar_events",
        {
            "period": calendar_period
        }
    )

    working_conversation = list(
        conversation
    )

    working_conversation.append({
        "role": "system",
        "content": get_runtime_context()
    })

    working_conversation.append({
        "role": "user",
        "content": user_input
    })

    working_conversation.append({
        "role": "system",
        "content": (
            f"Oliver asked for an overall view of {relative_name}. "
            f"The resolved calendar date is {date_string}.\n\n"

            "Mairon Core has already retrieved BOTH sources required "
            "for this answer:\n\n"

            "ROUTINE / DAILY CONTEXT:\n"
            f"{json.dumps(routine_result, ensure_ascii=False)}\n\n"

            "GOOGLE CALENDAR:\n"
            f"{json.dumps(calendar_result, ensure_ascii=False)}\n\n"

            "Answer Oliver's original question by combining these sources. "
            "Routine describes what he normally does and any one-day overrides. "
            "Calendar describes specific scheduled events. "
            "Do not claim a Calendar event came from routine context or vice versa. "

            f"Refer to {date_string} as '{relative_name}' when appropriate. "
            "Do not incorrectly call tomorrow 'today'. "

            "If routine says it is a workday, mention whether he is working "
            "from home or in the office when that information is known. "
            "If work location is missing, say that briefly rather than guessing. "

            "Specific Calendar events should supplement the routine, not replace it. "
            "Keep the answer conversational and concise. "
            "Do not mention tools, JSON, function calls, or implementation details."
        )
    })

    response = client.chat(
        model=MODEL,
        messages=working_conversation
    )

    working_conversation.append(
        response.message
    )

    return (
        response.message.content,
        working_conversation,
        None,
        None
    )


# --------------------------------------------------
# Result helpers
# --------------------------------------------------

def get_best_search_url(
    search_result
):
    if not search_result:
        return None

    if not search_result.get(
        "success"
    ):
        return None

    results = search_result.get(
        "results",
        []
    )

    for result in results:
        url = result.get(
            "url"
        )

        if (
            isinstance(url, str)
            and (
                url.startswith("https://")
                or url.startswith("http://")
            )
        ):
            return url

    return None


def get_email_message_ids(
    search_result
):
    if not search_result:
        return []

    if not search_result.get(
        "success"
    ):
        return []

    emails = search_result.get(
        "emails",
        []
    )

    message_ids = []

    for email in emails:
        message_id = email.get(
            "message_id"
        )

        if message_id:
            message_ids.append(
                message_id
            )

    return message_ids


def normalise_tool_arguments(
    arguments
):
    """
    Ollama normally returns a dict, but tolerate JSON text
    defensively at the tool boundary.
    """

    if isinstance(
        arguments,
        dict
    ):
        return dict(
            arguments
        )

    if isinstance(
        arguments,
        str
    ):
        try:
            parsed = json.loads(
                arguments
            )

            if isinstance(
                parsed,
                dict
            ):
                return parsed

        except Exception:
            pass

    return {}


# --------------------------------------------------
# Inbox-review finalisation
# --------------------------------------------------

def finalise_inbox_review(
    client,
    working_conversation
):
    """
    Finish inbox triage with tools completely removed.

    Internal workflow limits and tool mechanics must never
    appear in the user-facing answer.
    """

    working_conversation.append({
        "role": "system",
        "content": (
            "Produce the final inbox-attention brief now. "
            "Do not call or request any more tools. "
            "Do not mention tools, function calls, internal limits, "
            "budgets, implementation details, JSON, Unicode, or the "
            "inbox-review process itself. "
            "Do not say that anything needs to reset. "

            "Answer only the user's actual question. "

            "Prioritise messages as follows:\n"
            "- ACTION NEEDED: Oliver genuinely needs to do something.\n"
            "- FYI: worth knowing, but no action is currently required.\n"
            "- Ignore ordinary marketing and promotional noise.\n\n"

            "You do not need to list ignored marketing emails unless "
            "doing so is useful. Keep the answer concise and practical. "
            "If an important message is ambiguous, say briefly what is "
            "known from the available evidence rather than discussing "
            "why more information was not retrieved."
        )
    })

    final_response = client.chat(
        model=MODEL,
        messages=working_conversation
    )

    working_conversation.append(
        final_response.message
    )

    return (
        final_response.message.content,
        working_conversation,
        None,
        None
    )


# --------------------------------------------------
# Deterministic inbox-attention workflow
# --------------------------------------------------

def handle_inbox_attention_request(
    client,
    user_input,
    conversation
):
    """
    Run inbox triage as a constrained local workflow.

    Core fetches the requested email window once.

    Qwen may inspect only specific matching emails and may
    never wander into weather, web search, memory, routes,
    Calendar, or other unrelated capabilities.
    """

    days = get_inbox_review_days(
        user_input
    )

    print(
        "[Core] Inbox review: fetching read and unread "
        f"email from the last {days} day(s)."
    )

    print(
        "[Tool] Mairon Core required: get_recent_emails"
    )

    inbox_result = execute_tool(
        "get_recent_emails",
        {
            "days": days,
            "max_results": 20,
            "unread_only": False
        }
    )

    working_conversation = list(
        conversation
    )

    working_conversation.append({
        "role": "system",
        "content": get_runtime_context()
    })

    working_conversation.append({
        "role": "user",
        "content": user_input
    })

    if not inbox_result.get(
        "success"
    ):
        error_message = inbox_result.get(
            "message",
            "Unknown Gmail error."
        )

        answer = (
            "I couldn't complete the inbox review because "
            f"Gmail returned an error: {error_message}"
        )

        working_conversation.append({
            "role": "assistant",
            "content": answer
        })

        return (
            answer,
            working_conversation,
            None,
            None
        )

    emails = inbox_result.get(
        "emails",
        []
    )

    if not emails:
        answer = (
            f"You don't have any emails in the last {days} "
            "day(s) in that review window."
        )

        working_conversation.append({
            "role": "assistant",
            "content": answer
        })

        return (
            answer,
            working_conversation,
            None,
            None
        )

    valid_message_ids = {
        email.get("message_id")
        for email in emails
        if email.get("message_id")
    }

    working_conversation.append({
        "role": "system",
        "content": (
            "You are performing a private local inbox-attention review for Oliver. "
            "Stay strictly on the inbox task. "

            "The email summaries below were fetched from Gmail by Mairon Core "
            "and include both read and unread messages. "
            "Read status is not the same as importance.\n\n"

            "Classify messages using these rules:\n"

            "- ACTION NEEDED: Oliver genuinely needs to do something, reply, "
            "pay, submit, fix, confirm, attend, investigate, or make a decision.\n"

            "- FYI: useful information worth knowing, but no action is currently required.\n"

            "- IGNORE: ordinary marketing, promotions, newsletters, surveys, "
            "sales, or noise.\n\n"

            "Use sender, subject, date, and snippet first. "
            "Most messages should be classifiable from those summaries alone. "

            "Only use read_email when a message appears potentially important "
            "but the summary genuinely does not contain enough information to "
            "decide whether Oliver should act. "

            "Do not read promotional emails merely to inspect them. "
            "Do not search memory. "
            "Do not discuss Unicode or formatting. "
            "Do not discuss tools or implementation. "
            "Do not drift into unrelated topics. "

            "Security notifications such as sign-ins, password resets, "
            "account changes, OAuth authorizations, or recovery events should "
            "generally be surfaced if Oliver may need to verify that he initiated them. "

            "Keep the eventual final answer concise and useful.\n\n"

            "EMAIL SUMMARIES:\n"
            f"{json.dumps(emails, ensure_ascii=False)}"
        )
    })

    available_tools = (
        [READ_EMAIL_ONLY_TOOL]
        if READ_EMAIL_ONLY_TOOL
        else []
    )

    read_count = 0
    read_cache = {}

    # --------------------------------------------------
    # Allow a few focused inspection rounds
    # --------------------------------------------------

    for _ in range(6):

        # Once the inspection budget is used, immediately
        # remove tools and force a normal final answer.
        if read_count >= MAX_INBOX_READS:
            return finalise_inbox_review(
                client,
                working_conversation
            )

        if available_tools:
            response = client.chat(
                model=MODEL,
                messages=working_conversation,
                tools=available_tools
            )

        else:
            response = client.chat(
                model=MODEL,
                messages=working_conversation
            )

        tool_calls = (
            response.message.tool_calls
            or []
        )

        # Qwen has finished inspecting messages.
        #
        # Do not return its intermediate response directly.
        # Force one final tool-free pass so it returns to
        # Oliver's ORIGINAL inbox-review request and
        # considers all email summaries, not merely the
        # last message it inspected.
        if not tool_calls:
            working_conversation.append(
                response.message
            )

            return finalise_inbox_review(
                client,
                working_conversation
            )

        working_conversation.append(
            response.message
        )

        for tool_call in tool_calls:
            tool_name = (
                tool_call.function.name
            )

            arguments = normalise_tool_arguments(
                tool_call.function.arguments
            )

            if tool_name != "read_email":
                working_conversation.append({
                    "role": "tool",
                    "tool_name": tool_name,
                    "content": json.dumps({
                        "success": False,
                        "message": (
                            "That capability is not available "
                            "during inbox review."
                        )
                    })
                })

                continue

            message_id = (
                arguments.get(
                    "message_id"
                )
                or ""
            ).strip()

            if message_id not in valid_message_ids:
                working_conversation.append({
                    "role": "tool",
                    "tool_name": "read_email",
                    "content": json.dumps({
                        "success": False,
                        "message": (
                            "That message is not part of the "
                            "current inbox review."
                        )
                    })
                })

                continue

            # Re-reading an already inspected message does
            # not consume another inspection.
            if message_id in read_cache:
                read_result = read_cache[
                    message_id
                ]

                working_conversation.append({
                    "role": "tool",
                    "tool_name": "read_email",
                    "content": json.dumps(
                        read_result,
                        ensure_ascii=False
                    )
                })

                continue

            # If Qwen requested several reads in one model
            # response, satisfy only those that fit within
            # the review's private inspection budget.
            if read_count >= MAX_INBOX_READS:
                working_conversation.append({
                    "role": "tool",
                    "tool_name": "read_email",
                    "content": json.dumps({
                        "success": False,
                        "message": (
                            "This message was not expanded. "
                            "Use its existing sender, subject, "
                            "date, and snippet when completing "
                            "the inbox review."
                        )
                    })
                })

                continue

            print(
                "[Tool] Mairon requested: read_email"
            )

            read_result = execute_tool(
                "read_email",
                {
                    "message_id": message_id
                }
            )

            read_cache[
                message_id
            ] = read_result

            read_count += 1

            working_conversation.append({
                "role": "tool",
                "tool_name": "read_email",
                "content": json.dumps(
                    read_result,
                    ensure_ascii=False
                )
            })

        # If that batch used the remaining reads, don't
        # expose another tool-enabled round to Qwen.
        if read_count >= MAX_INBOX_READS:
            return finalise_inbox_review(
                client,
                working_conversation
            )

    # If Qwen somehow loops without finishing, Core ends
    # the workflow cleanly rather than exposing internals.
    return finalise_inbox_review(
        client,
        working_conversation
    )


# --------------------------------------------------
# Main local provider
# --------------------------------------------------

def get_response(
    client,
    user_input,
    instructions,
    conversation=None,
    allow_cloud_escalation=False
):
    if conversation is None:
        conversation = [
            {
                "role": "system",
                "content": instructions
            }
        ]

    # --------------------------------------------------
    # Inbox-attention requests use their own constrained
    # private workflow.
    # --------------------------------------------------

    if is_inbox_attention_request(
        user_input
    ):
        return handle_inbox_attention_request(
            client,
            user_input,
            conversation
        )

    # --------------------------------------------------
    # Overall day questions combine routine + Calendar.
    # --------------------------------------------------

    if is_day_overview_request(
        user_input
    ):
        return handle_day_overview_request(
            client,
            user_input,
            conversation
        )

    base_conversation = list(
        conversation
    )

    working_conversation = list(
        conversation
    )

    working_conversation.append({
        "role": "system",
        "content": get_runtime_context()
    })

    working_conversation.append({
        "role": "user",
        "content": user_input
    })

    tools = list(
        OLLAMA_ACTION_TOOLS
    )

    tools.append(
        CALENDAR_EVENT_REQUEST_TOOL
    )

    if allow_cloud_escalation:
        tools.append(
            CLOUD_ESCALATION_TOOL
        )

    require_web_read = (
        explicitly_requires_web_read(
            user_input
        )
    )

    require_email_read = (
        explicitly_requires_email_read(
            user_input
        )
    )

    tools_used = []

    last_web_search_result = None
    last_email_search_result = None

    web_read_reminder_sent = False
    core_web_read_performed = False

    email_read_reminder_sent = False
    core_email_read_performed = False

    tool_rounds = 0

    while True:
        tool_rounds += 1

        if tool_rounds > MAX_TOOL_ROUNDS:
            return (
                (
                    "I hit Mairon's maximum tool-processing "
                    "limit before completing the request."
                ),
                working_conversation,
                None,
                None
            )

        response = client.chat(
            model=MODEL,
            messages=working_conversation,
            tools=tools
        )

        tool_calls = (
            response.message.tool_calls
            or []
        )

        # --------------------------------------------------
        # Calendar write permission request
        # --------------------------------------------------

        for tool_call in tool_calls:
            if (
                tool_call.function.name
                == "request_calendar_event_creation"
            ):
                arguments = normalise_tool_arguments(
                    tool_call.function.arguments
                )

                required_fields = [
                    "summary",
                    "start_time",
                    "end_time",
                ]

                missing_fields = [
                    field
                    for field in required_fields
                    if not arguments.get(field)
                ]

                if missing_fields:
                    working_conversation.append(
                        response.message
                    )

                    working_conversation.append({
                        "role": "tool",
                        "tool_name": (
                            "request_calendar_event_creation"
                        ),
                        "content": json.dumps({
                            "success": False,
                            "message": (
                                "Calendar creation request is "
                                "missing required fields: "
                                + ", ".join(
                                    missing_fields
                                )
                            )
                        })
                    })

                    break

                pending_action = {
                    "type": "create_calendar_event",
                    "summary": arguments["summary"],
                    "start_time": arguments["start_time"],
                    "end_time": arguments["end_time"],
                    "location": arguments.get(
                        "location"
                    ) or None,
                    "description": arguments.get(
                        "description"
                    ) or None,
                }

                return (
                    None,
                    base_conversation,
                    None,
                    pending_action
                )

        # --------------------------------------------------
        # Cloud permission request
        # --------------------------------------------------

        for tool_call in tool_calls:
            if (
                tool_call.function.name
                == "request_cloud_escalation"
            ):
                arguments = normalise_tool_arguments(
                    tool_call.function.arguments
                )

                reason = arguments.get(
                    "reason",
                    (
                        "The local model believes this request "
                        "would benefit from cloud processing."
                    )
                )

                return (
                    None,
                    base_conversation,
                    reason,
                    None
                )

        # --------------------------------------------------
        # Qwen wants to provide final answer
        # --------------------------------------------------

        if not tool_calls:

            # ==============================================
            # Webpage read enforcement
            # ==============================================

            web_search_was_used = (
                "web_search" in tools_used
            )

            web_read_was_used = (
                "web_read" in tools_used
            )

            missing_required_web_read = (
                require_web_read
                and web_search_was_used
                and not web_read_was_used
            )

            if missing_required_web_read:

                if not web_read_reminder_sent:
                    working_conversation.append(
                        response.message
                    )

                    working_conversation.append({
                        "role": "system",
                        "content": (
                            "Oliver explicitly required you to read an actual "
                            "source before answering. You searched the web but "
                            "have not used web_read. Do not answer yet. "
                            "Choose the most relevant authoritative URL and "
                            "call web_read."
                        )
                    })

                    web_read_reminder_sent = True

                    continue

                if not core_web_read_performed:
                    candidate_url = (
                        get_best_search_url(
                            last_web_search_result
                        )
                    )

                    if candidate_url:
                        print(
                            "[Tool] Mairon Core required: web_read"
                        )

                        read_result = execute_tool(
                            "web_read",
                            {
                                "url": candidate_url,
                                "focus": user_input
                            }
                        )

                        tools_used.append(
                            "web_read"
                        )

                        core_web_read_performed = True

                        working_conversation.append({
                            "role": "system",
                            "content": (
                                "Mairon Core enforced Oliver's requirement "
                                "to read a source before answering.\n\n"
                                f"Source:\n{candidate_url}\n\n"
                                "Extracted content:\n"
                                f"{json.dumps(read_result)}\n\n"
                                "Answer the original question using the "
                                "content that was actually read."
                            )
                        })

                        continue

            # ==============================================
            # Gmail read enforcement
            # ==============================================

            email_search_was_used = (
                "find_emails" in tools_used
                or "get_recent_emails" in tools_used
            )

            email_read_was_used = (
                "read_email" in tools_used
            )

            missing_required_email_read = (
                require_email_read
                and email_search_was_used
                and not email_read_was_used
            )

            if missing_required_email_read:

                message_ids = get_email_message_ids(
                    last_email_search_result
                )

                if (
                    len(message_ids) == 1
                    and not core_email_read_performed
                ):
                    message_id = message_ids[0]

                    print(
                        "[Tool] Mairon Core required: read_email"
                    )

                    read_result = execute_tool(
                        "read_email",
                        {
                            "message_id": message_id
                        }
                    )

                    tools_used.append(
                        "read_email"
                    )

                    core_email_read_performed = True

                    working_conversation.append({
                        "role": "system",
                        "content": (
                            "Mairon Core enforced Oliver's requirement "
                            "to inspect the contents of the relevant email "
                            "before answering.\n\n"
                            "The selected email was read and returned:\n"
                            f"{json.dumps(read_result)}\n\n"
                            "Now answer Oliver's original question using "
                            "the actual email contents. Do not ask Oliver "
                            "whether you should read the email: it has "
                            "already been read."
                        )
                    })

                    continue

                if (
                    len(message_ids) > 1
                    and not email_read_reminder_sent
                ):
                    working_conversation.append(
                        response.message
                    )

                    working_conversation.append({
                        "role": "system",
                        "content": (
                            "Oliver's question requires information from "
                            "inside one of the matching emails. You have "
                            "only searched Gmail and have not used read_email. "
                            "Do not answer yet. Select the most relevant "
                            "message_id from the Gmail results and call "
                            "read_email."
                        )
                    })

                    email_read_reminder_sent = True

                    continue

                if (
                    len(message_ids) > 1
                    and not core_email_read_performed
                ):
                    message_id = message_ids[0]

                    print(
                        "[Tool] Mairon Core required: read_email"
                    )

                    read_result = execute_tool(
                        "read_email",
                        {
                            "message_id": message_id
                        }
                    )

                    tools_used.append(
                        "read_email"
                    )

                    core_email_read_performed = True

                    working_conversation.append({
                        "role": "system",
                        "content": (
                            "Mairon Core enforced the required Gmail read. "
                            "The most relevant available matching message "
                            "was read.\n\n"
                            f"{json.dumps(read_result)}\n\n"
                            "Answer Oliver using the contents that were "
                            "actually retrieved."
                        )
                    })

                    continue

            # ==============================================
            # Requirements satisfied
            # ==============================================

            working_conversation.append(
                response.message
            )

            return (
                response.message.content,
                working_conversation,
                None,
                None
            )

        # --------------------------------------------------
        # Execute normal model-requested tools
        # --------------------------------------------------

        working_conversation.append(
            response.message
        )

        for tool_call in tool_calls:
            tool_name = (
                tool_call.function.name
            )

            if tool_name in (
                "request_cloud_escalation",
                "request_calendar_event_creation",
            ):
                continue

            arguments = normalise_tool_arguments(
                tool_call.function.arguments
            )

            print(
                f"[Tool] Mairon requested: {tool_name}"
            )

            tool_result = execute_tool(
                tool_name,
                arguments
            )

            tools_used.append(
                tool_name
            )

            if tool_name == "web_search":
                last_web_search_result = (
                    tool_result
                )

            if tool_name in (
                "find_emails",
                "get_recent_emails",
            ):
                last_email_search_result = (
                    tool_result
                )

            working_conversation.append({
                "role": "tool",
                "tool_name": tool_name,
                "content": json.dumps(
                    tool_result
                )
            })

            if tool_name == "set_work_location":
                relative_date_instruction = ""

                if "tomorrow" in user_input.lower():
                    relative_date_instruction = (
                        " Oliver explicitly described this work-location "
                        "override as applying tomorrow. Preserve that "
                        "relative date correctly and do not call it today."
                    )

                working_conversation.append({
                    "role": "system",
                    "content": (
                        "The requested work-location update has now been processed. "
                        "Finish Oliver's original request immediately using the "
                        "set_work_location result already returned. "
                        "Do not start a new task and do not inspect Gmail, Calendar, "
                        "weather, routes, memory, the web, or any other source unless "
                        "Oliver explicitly asked for that additional information in "
                        "the same message. "
                        "For a simple work-location update, give a brief confirmation "
                        "and mention the derived recommended wake time when available. "
                        "Do not mention tools, function calls, JSON, or implementation "
                        "details."
                        + relative_date_instruction
                    )
                })

                # State mutation is complete. Remove all tools for the
                # response pass so Qwen cannot wander into an unrelated
                # Gmail/Calendar/weather query after successfully updating
                # tomorrow's context.
                final_response = client.chat(
                    model=MODEL,
                    messages=working_conversation
                )

                working_conversation.append(
                    final_response.message
                )

                return (
                    final_response.message.content,
                    working_conversation,
                    None,
                    None
                )
