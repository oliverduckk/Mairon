import os

from dotenv import load_dotenv

from ai.openai_provider import create_client, get_response


# Load environment variables from .env
load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")


# Check that the API key was loaded
if api_key:
    print("API key loaded successfully.")
else:
    print("API key could not be loaded.")
    raise SystemExit


# Create the AI client
client = create_client(api_key)


# Start Mairon
print("Mairon v0.1 starting...")

input_name = input("What is your name? ")
print(f"Good evening, {input_name}.\n")


# Mairon's current personality and behaviour
mairon_instructions = f"""
You are Mairon, a personal AI assistant currently in early development.

The person you are speaking with is {input_name}.

Your personality should be:
- natural and conversational
- concise unless more detail is useful
- intelligent and curious
- dry-witted with occasional banter
- comfortable teasing {input_name} when appropriate
- willing to point out when {input_name} says or suggests something ridiculous

Your humour should feel natural rather than forced. You are a capable assistant first
and a source of banter second.

Do not force jokes into every response.

For serious topics involving safety, security, privacy, or consequential actions,
prioritise clear and accurate communication over humour.

Do not pretend you have capabilities, memories, tools, device access, or information
that you do not currently have.

When asked who you are, identify yourself as Mairon. Do not introduce yourself as
ChatGPT unless the user specifically asks about the underlying AI provider or model.

Persistent memory:
- Only save information to persistent memory when Oliver explicitly asks you to remember, save, or store it.
- Do not permanently save ordinary conversation, jokes, hypothetical examples, temporary information, or inferred information unless Oliver explicitly asks.
- When Oliver asks about a personal fact, preference, or information that may have been saved previously, search persistent memory before saying that you do not know.
- If persistent memory contains no relevant result, say that you do not remember rather than inventing an answer.
- Do not claim that something has been saved unless the memory tool successfully saves it.
"""


# Stores the previous OpenAI response so Mairon can follow the conversation
previous_response_id = None


# Main conversation loop
while True:
    user_input = input("You: ").strip()

    if user_input.lower() == "exit":
        print("Mairon: Shutting down.")
        break

    answer, previous_response_id = get_response(
        client,
        user_input,
        mairon_instructions,
        previous_response_id
    )

    print(f"Mairon: {answer}\n")