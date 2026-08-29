import json

from openai import OpenAI

from tools.tool_registry import TOOLS, execute_tool


MODEL = "gpt-5.6-luna"


def create_client(api_key):
    return OpenAI(api_key=api_key)


def get_response(client, user_input, instructions, previous_response_id=None):
    response = client.responses.create(
        model=MODEL,
        instructions=instructions,
        input=user_input,
        previous_response_id=previous_response_id,
        tools=TOOLS,
        parallel_tool_calls=False
    )

    for item in response.output:
        if item.type == "function_call":
            print(f"[Tool] Mairon requested: {item.name}")

            arguments = json.loads(item.arguments or "{}")

            tool_result = execute_tool(
                item.name,
                arguments
            )

            final_response = client.responses.create(
                model=MODEL,
                instructions=instructions,
                previous_response_id=response.id,
                tools=TOOLS,
                parallel_tool_calls=False,
                input=[
                    {
                        "type": "function_call_output",
                        "call_id": item.call_id,
                        "output": json.dumps(tool_result)
                    }
                ]
            )

            return final_response.output_text, final_response.id

    return response.output_text, response.id