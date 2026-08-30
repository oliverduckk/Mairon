import json

from ollama import Client

from tools.tool_registry import TOOLS, execute_tool


MODEL = "qwen3:14b"

MAX_TOOL_ROUNDS = 12


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
            "It only asks Mairon Core to request permission from the user."
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


def explicitly_requires_web_read(user_input):
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


def get_best_search_url(search_result):
    """
    Return the highest-ranked usable URL from a web_search result.

    Tavily already returns results ordered by relevance, so the
    first valid result is our deterministic fallback if the model
    refuses to select and read one itself.
    """

    if not search_result:
        return None

    if not search_result.get("success"):
        return None

    results = search_result.get(
        "results",
        []
    )

    for result in results:
        url = result.get("url")

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

    base_conversation = list(conversation)
    working_conversation = list(conversation)

    working_conversation.append({
        "role": "user",
        "content": user_input
    })

    tools = list(
        OLLAMA_ACTION_TOOLS
    )

    if allow_cloud_escalation:
        tools.append(
            CLOUD_ESCALATION_TOOL
        )

    require_web_read = explicitly_requires_web_read(
        user_input
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
                    "I hit Mairon's maximum tool-processing limit "
                    "before completing the request."
                ),
                working_conversation,
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
        # Cloud escalation request
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
                    reason
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

                # ------------------------------------------
                # First failure:
                # give Qwen one explicit chance to correct
                # itself and choose a source.
                # ------------------------------------------

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

                # ------------------------------------------
                # Second failure:
                # Core stops asking nicely and performs the
                # required read itself.
                # ------------------------------------------

                if not core_web_read_performed:
                    candidate_url = get_best_search_url(
                        last_web_search_result
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
                            "I completed the web search, but I could not find "
                            "a usable webpage to read, so I won't pretend the "
                            "source was verified."
                        ),
                        working_conversation,
                        None
                    )

            # Requirement satisfied, or none existed.
            working_conversation.append(
                response.message
            )

            return (
                response.message.content,
                working_conversation,
                None
            )

        # --------------------------------------------------
        # Execute model-requested tools
        # --------------------------------------------------

        working_conversation.append(
            response.message
        )

        for tool_call in tool_calls:
            tool_name = (
                tool_call.function.name
            )

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