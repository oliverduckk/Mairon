import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from ollama import Client

from tools.tool_registry import TOOLS, execute_tool


MODEL = "qwen3:14b"

MAX_TOOL_ROUNDS = 12


MAIRON_TIMEZONE = os.getenv(
    "MAIRON_TIMEZONE",
    "Australia/Sydney"
)

LOCAL_TIMEZONE = ZoneInfo(
    MAIRON_TIMEZONE
)


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
            "device-control tasks, or ordinary web research. "
            "Calling this tool does NOT access the cloud. "
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
            "Resolve phrases such as 'tomorrow', 'Friday', and 'next Monday' using "
            "that runtime context. "
            "If Oliver specifies a duration, respect it. "
            "If Oliver gives a start time but no duration, propose a 60-minute event. "
            "The exact proposed start and end times will be shown to Oliver before approval."
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
                        "Proposed event start as ISO 8601 local date/time, "
                        "for example 2026-08-31T18:00:00+10:00."
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


def get_runtime_context():
    """
    Give the local model reliable current date/time information.

    This is particularly important for phrases such as
    'tomorrow', 'Friday', and 'next week'.
    """

    now = datetime.now(
        LOCAL_TIMEZONE
    )

    return (
        "Mairon runtime context: "
        f"The current local date and time is {now.isoformat()} "
        f"({now.strftime('%A')}) in timezone {MAIRON_TIMEZONE}. "
        "Use this value when resolving relative dates and times."
    )


def explicitly_requires_web_read(
    user_input
):
    """
    Detect cases where Oliver explicitly asked Mairon
    to read/open/check an actual webpage or source.
    """

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


def get_best_search_url(
    search_result
):
    """
    Return the first usable URL from a successful
    web_search result.
    """

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

    base_conversation = list(
        conversation
    )

    working_conversation = list(
        conversation
    )

    # Fresh runtime context for every user turn.
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

    # This is a request-only authority tool.
    # It cannot perform a Calendar write.
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

    tools_used = []

    last_web_search_result = None

    web_read_reminder_sent = False
    core_web_read_performed = False

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
        # Calendar event creation permission request
        # --------------------------------------------------

        for tool_call in tool_calls:
            if (
                tool_call.function.name
                == "request_calendar_event_creation"
            ):
                arguments = (
                    tool_call.function.arguments
                    or {}
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
                                + ", ".join(missing_fields)
                            )
                        })
                    })

                    continue

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

                # Important:
                # return the pre-request state.
                #
                # We do not want an unfinished tool call
                # stored in conversation history.
                return (
                    None,
                    base_conversation,
                    None,
                    pending_action
                )

        # --------------------------------------------------
        # Cloud escalation permission request
        # --------------------------------------------------

        for tool_call in tool_calls:
            if (
                tool_call.function.name
                == "request_cloud_escalation"
            ):
                arguments = (
                    tool_call.function.arguments
                    or {}
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
        # Model wants to provide final answer
        # --------------------------------------------------

        if not tool_calls:

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
                            "source before answering. You have searched the web "
                            "but have not used web_read. Do not answer yet. "
                            "Choose the most relevant authoritative URL from the "
                            "search results and call web_read on that page."
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
                                "to read a source before answering. "
                                f"The selected source was:\n{candidate_url}\n\n"
                                "The extracted webpage result is:\n"
                                f"{json.dumps(read_result)}\n\n"
                                "Now answer Oliver's original question using "
                                "the source content that was actually read. "
                                "Do not claim anything was verified unless it "
                                "is supported by that content."
                            )
                        })

                        continue

                    return (
                        (
                            "I completed the web search, but I could not "
                            "find a usable webpage to read, so I won't "
                            "pretend the source was verified."
                        ),
                        working_conversation,
                        None,
                        None
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
        # Execute normal model-requested tools
        # --------------------------------------------------

        working_conversation.append(
            response.message
        )

        for tool_call in tool_calls:
            tool_name = (
                tool_call.function.name
            )

            # Special permission tools are handled above
            # and must never reach execute_tool().
            if tool_name in (
                "request_cloud_escalation",
                "request_calendar_event_creation",
            ):
                continue

            arguments = (
                tool_call.function.arguments
                or {}
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

            working_conversation.append({
                "role": "tool",
                "tool_name": tool_name,
                "content": json.dumps(
                    tool_result
                )
            })