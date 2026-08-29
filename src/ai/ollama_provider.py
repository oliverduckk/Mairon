import json

from ollama import Client

from tools.tool_registry import TOOLS, execute_tool


MODEL = "qwen3:14b"


def create_client():
    return Client(host="http://localhost:11434")


def convert_tools_for_ollama():
    ollama_tools = []

    for tool in TOOLS:
        ollama_tools.append(
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["parameters"]
                }
            }
        )

    return ollama_tools


# Mairon's normal executable tools
OLLAMA_ACTION_TOOLS = convert_tools_for_ollama()


# This is NOT a normal executable tool.
# It only allows the local model to ask Mairon Core for cloud permission.
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
            "or device-control tasks. Calling this tool does NOT access the cloud. "
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

    # Work on a copy so a rejected cloud request does not leave
    # an unfinished tool call in Mairon's conversation history.
    base_conversation = list(conversation)
    working_conversation = list(conversation)

    working_conversation.append(
        {
            "role": "user",
            "content": user_input
        }
    )

    tools = list(OLLAMA_ACTION_TOOLS)

    if allow_cloud_escalation:
        tools.append(CLOUD_ESCALATION_TOOL)

    while True:
        response = client.chat(
            model=MODEL,
            messages=working_conversation,
            tools=tools
        )

        tool_calls = response.message.tool_calls or []

        # Cloud escalation is special.
        # Do NOT execute anything and do NOT contact OpenAI.
        for tool_call in tool_calls:
            if tool_call.function.name == "request_cloud_escalation":
                arguments = tool_call.function.arguments or {}

                reason = arguments.get(
                    "reason",
                    "The local model believes this request would benefit from cloud processing."
                )

                return None, base_conversation, reason

        # Normal assistant response
        working_conversation.append(response.message)

        if not tool_calls:
            return response.message.content, working_conversation, None

        # Execute normal approved tools
        for tool_call in tool_calls:
            tool_name = tool_call.function.name
            arguments = tool_call.function.arguments or {}

            print(f"[Tool] Mairon requested: {tool_name}")

            tool_result = execute_tool(
                tool_name,
                arguments
            )

            working_conversation.append(
                {
                    "role": "tool",
                    "tool_name": tool_name,
                    "content": json.dumps(tool_result)
                }
            )