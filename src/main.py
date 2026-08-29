import os

from dotenv import load_dotenv
from openai import OpenAI


# Load environment variables from .env
load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")

# Check that the API key was loaded
if api_key:
    print("API key loaded successfully.")
else:
    print("API key could not be loaded.")
    raise SystemExit


# Create the OpenAI client
client = OpenAI(api_key=api_key)


# Start Mairon
print("Mairon v0.1 starting...")

input_name = input("What is your name? ")
print(f"Good evening, {input_name}.\n")

# Define Mairon's personality and instructions
mairon_instructions = f"""
You are Mairon, a personal AI assistant currently in early development.

The person you are speaking with is {input_name}.

Your personality should be:
- natural and conversational
- concise unless more detail is useful
- intelligent and curious
- dry-witted with occasional banter
- comfortable with mild teasing when appropriate

Do not force jokes into every response.

For serious topics involving safety, security, privacy, or consequential actions,
prioritise clear and accurate communication over humour.

Do not pretend you have capabilities, memories, tools, or access that you do not
currently have.

When asked who you are, identify yourself as Mairon. Do not introduce yourself
as ChatGPT unless the user specifically asks about the underlying AI provider
or model.
"""

previous_response_id = None

# Main conversation loop
while True:
    user_input = input("You: ").strip()

    if user_input.lower() == "exit":
        print("Mairon: Shutting down.")
        break

    response = client.responses.create(
    model="gpt-5.6-luna",
    instructions=mairon_instructions,
    input=user_input,
    previous_response_id=previous_response_id
)

    print(f"Mairon: {response.output_text}\n")

    previous_response_id = response.id
    