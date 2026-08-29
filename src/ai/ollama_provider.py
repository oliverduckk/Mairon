from ollama import Client


MODEL = "qwen3:14b"


def create_client():
    return Client(host="http://localhost:11434")


def get_response(client, messages):
    response = client.chat(
        model=MODEL,
        messages=messages
    )

    return response.message.content