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


OLLAMA_TOOLS = convert_tools_for_ollama()


def get_response(client, user_input, instructions, conversation=None):
    if conversation is None:
        conversation = [
            {
                "role": "system",
                "content": instructions
            }
        ]

    conversation.append(
        {
            "role": "user",
            "content": user_input
        }
    )

    while True:
        response = client.chat(
            model=MODEL,
            messages=conversation,
            tools=OLLAMA_TOOLS
        )

        conversation.append(response.message)

        if not response.message.tool_calls:
            return response.message.content, conversation

        for tool_call in response.message.tool_calls:
            tool_name = tool_call.function.name
            arguments = tool_call.function.arguments or {}

            print(f"[Tool] Mairon requested: {tool_name}")

            tool_result = execute_tool(
                tool_name,
                arguments
            )

            conversation.append(
                {
                    "role": "tool",
                    "tool_name": tool_name,
                    "content": json.dumps(tool_result)
                }
            )