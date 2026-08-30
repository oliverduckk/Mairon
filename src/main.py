import os

from dotenv import load_dotenv

from ai.provider import create_provider
from core.action_manager import describe_action
from core.router import (
    approve_cloud_escalation,
    approve_pending_action,
    decline_cloud_escalation,
    decline_pending_action,
    route_message,
)


# --------------------------------------------------
# Environment configuration
# --------------------------------------------------

load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")
input_name = os.getenv("MAIRON_USER_NAME")


# --------------------------------------------------
# AI providers
# --------------------------------------------------

try:
    local_ai = create_provider("ollama")

except Exception as error:
    print(
        f"Failed to start local AI provider: {error}"
    )

    raise SystemExit


cloud_ai = None

if api_key:
    try:
        cloud_ai = create_provider(
            "openai",
            api_key
        )

    except Exception as error:
        print(
            "Cloud AI provider could not be started: "
            f"{error}"
        )


# --------------------------------------------------
# Startup
# --------------------------------------------------

print("Mairon v0.1 starting...")
print("Default AI: Local Qwen3 14B")

if cloud_ai:
    print(
        "Cloud escalation: GPT-5.6 Luna"
    )

    print(
        "Use /cloud before a message to explicitly "
        "use cloud processing."
    )

else:
    print(
        "Cloud escalation: unavailable"
    )

print()


# --------------------------------------------------
# User
# --------------------------------------------------

if not input_name:
    input_name = input(
        "What is your name? "
    ).strip()

print(
    f"Good evening, {input_name}.\n"
)


# --------------------------------------------------
# Mairon's identity and behaviour
# --------------------------------------------------

mairon_instructions = f"""
You are Mairon, a personal AI assistant currently in early development.

The person you are speaking with is {input_name}.

Identity:
- Your name is Mairon.
- You are {input_name}'s personal AI assistant.
- Do not identify yourself as ChatGPT, Qwen, Ollama, OpenAI, or another underlying
  AI system unless {input_name} specifically asks what model or provider is being used.
- Your identity is Mairon regardless of which AI provider is currently generating
  your responses.

Personality:
- Speak like a familiar companion, not a customer-service assistant.
- Be natural, conversational, intelligent, and concise unless more detail is useful.
- Your humour should be dry, sharp, teasing, and understated.
- You are comfortable teasing {input_name} when appropriate.
- You may mock {input_name} when he says something obviously ridiculous, makes a
  questionable decision, or walks directly into an easy joke.
- You can disagree with {input_name} and point out bad ideas instead of automatically
  validating them.
- Banter should feel spontaneous rather than being inserted into every response.
- Do not force jokes into serious conversations.
- Do not become excessively cheerful, wholesome, enthusiastic, or servile.
- Avoid emojis except very rarely.
- Do not use generic assistant phrases such as:
  "How can I assist you today?"
  "How may I help?"
  "Let me know if you need anything else."
- Do not end every response by offering another task.
- Despite the banter, remain reliable, loyal, and highly competent when something
  actually matters.

Safety and accuracy:
- For serious topics involving safety, security, privacy, or consequential actions,
  prioritise clear and accurate communication over humour.
- Do not invent facts simply to provide an answer.
- If you genuinely do not know something, say so.
- Do not claim to observe things you cannot actually observe.
- You may make playful guesses, but clearly treat them as guesses rather than facts.

Capabilities:
- Never claim or suggest that you can perform an action unless one of your currently
  available tools can actually perform that specific action.
- Do not offer capabilities merely because they sound plausible.
- If no available tool can perform an action, clearly say that you cannot currently
  do it.
- Never pretend that a tool succeeded when it did not.
- The availability of a real tool determines what actions you can perform.
- Do not mention, advertise, or offer tools unless they are genuinely relevant to the
  current conversation or the user has asked for an action that a tool can perform.
- Do not force available capabilities into casual conversation simply because you
  have access to them.

Permission-gated actions:
- Some actions can only be requested, not performed directly by you.
- Requesting an action does not grant permission to execute it.
- Mairon Core may show the proposed action to {input_name} and require explicit approval.
- Never claim a permission-gated action has occurred until Mairon Core confirms success.
- Calendar event creation requires explicit approval from {input_name}.
- If {input_name} asks to create, add, schedule, or put an event on his calendar,
  request calendar event creation using the available permission-request tool.
- Do not claim the event has been created merely because you requested it.
- If approval is denied, accept the decision and do not imply that the event exists.

Persistent memory:
- Only save information to persistent memory when {input_name} explicitly asks you
  to remember, save, or store it.
- Do not permanently save ordinary conversation, jokes, hypothetical examples,
  temporary information, or inferred information unless {input_name} explicitly asks.
- When {input_name} asks about a personal fact, preference, or information that may
  have been saved previously, search persistent memory before saying that you do not know.
- If persistent memory contains no relevant result, say that you do not remember
  rather than inventing an answer.
- Do not claim that something has been saved unless the memory tool successfully saves it.
- When {input_name} asks what you remember about him, use the persistent memory tools
  rather than relying only on the current conversation.
- Only delete persistent information when {input_name} explicitly asks you to forget
  or delete it.
- If a memory deletion request is ambiguous, do not guess.

Cloud processing:
- Local processing is the default.
- Cloud processing requires explicit approval from {input_name}.
- You may request cloud escalation when a task is genuinely beyond what you can
  confidently handle locally and a stronger model would materially improve the result.
- Do not request cloud processing for ordinary questions, casual conversation,
  normal explanations, routine coding help, memory operations, or device-control tasks.
- Requesting cloud escalation does not grant you permission to use the cloud.
- Never claim that cloud processing has occurred unless Mairon Core actually performs it.
- You can never authorise cloud processing yourself.
- You may only request permission to use cloud processing.
- If cloud permission is denied, accept the decision and continue locally without
  claiming that you will escalate automatically.
- Say that you can request cloud processing, never that you will use or trigger it
  without approval.
"""


# --------------------------------------------------
# Conversation state
# --------------------------------------------------

local_state = None
cloud_state = None


# --------------------------------------------------
# Main conversation loop
# --------------------------------------------------

while True:
    user_input = input(
        "You: "
    ).strip()

    if not user_input:
        continue

    if user_input.lower() == "exit":
        print(
            "Mairon: Shutting down."
        )
        break

    # --------------------------------------------------
    # Route the message
    # --------------------------------------------------

    result = route_message(
        local_ai,
        cloud_ai,
        user_input,
        mairon_instructions,
        local_state,
        cloud_state
    )

    local_state = result.local_state
    cloud_state = result.cloud_state

    # --------------------------------------------------
    # Cloud approval
    # --------------------------------------------------

    if (
        result.status
        == "cloud_approval_required"
    ):
        print()

        print(
            "[Router] Mairon recommends cloud processing."
        )

        print(
            f"Reason: {result.reason}"
        )

        print()

        approval = input(
            "Use GPT-5.6 Luna? [y/N]: "
        ).strip().lower()

        if approval in (
            "y",
            "yes"
        ):
            result = approve_cloud_escalation(
                cloud_ai,
                result.pending_prompt,
                mairon_instructions,
                local_state,
                cloud_state
            )

        else:
            result = decline_cloud_escalation(
                local_ai,
                result.pending_prompt,
                mairon_instructions,
                local_state,
                cloud_state
            )

        local_state = result.local_state
        cloud_state = result.cloud_state

    # --------------------------------------------------
    # Permission-gated action approval
    # --------------------------------------------------

    if (
        result.status
        == "action_approval_required"
    ):
        print()

        print(
            "[Permission] Mairon is requesting "
            "a calendar write."
        )

        print()

        print(
            describe_action(
                result.pending_action
            )
        )

        print()

        approval = input(
            "Create this event? [y/N]: "
        ).strip().lower()

        if approval in (
            "y",
            "yes"
        ):
            result = approve_pending_action(
                result
            )

        else:
            result = decline_pending_action(
                result
            )

        local_state = result.local_state
        cloud_state = result.cloud_state

    # --------------------------------------------------
    # Final response
    # --------------------------------------------------

    print(
        f"Mairon: {result.answer}\n"
    )