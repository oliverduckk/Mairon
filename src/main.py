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


# Main conversation loop
while True:
    user_input = input("You: ").strip()

    if user_input.lower() == "exit":
        print("Mairon: Shutting down.")
        break

    response = client.responses.create(
        model="gpt-5.6-luna",
        input=user_input
    )

    print(f"Mairon: {response.output_text}\n")