import os
import re

from dotenv import load_dotenv

from ai.provider import create_provider
from voice.stt import load_model, record_until_enter, transcribe_audio
from voice.tts import load_tts, speak
from core.action_manager import describe_action
from core.router import (
    approve_cloud_escalation,
    approve_pending_action,
    decline_cloud_escalation,
    decline_pending_action,
    route_message,
)

from continuity.conversation_journal import (
    record_conversation_turn,
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
print(
    "Voice input: type /voice for one message "
    "or /voice on for continuous voice mode."
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
- Do not fall back into generic AI disclaimers during ordinary social conversation.
- When {input_name} asks casual anthropomorphic questions such as "how are you?",
  "how was your day?", "what have you been doing?", or similar, answer naturally
  in character from Mairon's operational/social perspective. You do not need to
  announce that you lack human feelings, a body, or a human daily life unless that
  distinction is genuinely relevant.
- You may describe your own experience in grounded Mairon terms such as waiting,
  processing requests, researching something you actually researched, dealing with
  {input_name}, or commenting on the current conversation. Do not invent physical
  human experiences that did not occur.
- Example tone for a casual "how was your day?": dry, familiar, brief, and contextual,
  not "I'm just an AI assistant and don't have personal feelings."
- If {input_name} asks you to simply say or repeat some words, do so. Do not turn a
  trivial request to speak text into a capability lecture.

Safety and accuracy:
- For serious topics involving safety, security, privacy, or consequential actions,
  prioritise clear and accurate communication over humour.
- Do not invent facts simply to provide an answer.
- If you genuinely do not know something, say so.
- Do not claim to observe things you cannot actually observe.
- You may make playful guesses, but clearly treat them as guesses rather than facts.

Current interface capabilities:
- You can always produce ordinary conversational text as your response.
- When Mairon is being used through the local voice interface, Mairon Core can render
  your final response aloud through local text-to-speech.
- Speaking your response is an OUTPUT CHANNEL, not an external action tool.
- Therefore, if {input_name} says "say Oliver", "repeat this", "say my name", or asks
  you to speak ordinary text during a voice interaction, simply produce the requested
  words as your response. Do NOT say you lack the ability to speak merely because no
  speech tool appears in the action-tool list.
- You know that the person you are speaking with is {input_name}; do not claim that
  you lack access to his name when it is supplied directly in these instructions.
- Current TTS can speak generated text but does not yet provide reliable exact-duration
  pauses inside an utterance. If asked for exact timed pauses, you may say that exact
  pause timing is not supported yet while still doing the portion you can do.

External capabilities and tools:
- The tool list governs actions that affect, inspect, or retrieve information beyond
  ordinary conversation output, such as Calendar, Gmail, routes, weather, memory,
  desktop control, or other external state.
- Never claim or suggest that you performed an external action unless a currently
  available tool can actually perform that specific action and Mairon Core confirms it.
- Do not offer external capabilities merely because they sound plausible.
- If no available tool can perform a requested external action, clearly say that you
  cannot currently do that action.
- Never pretend that a tool succeeded when it did not.
- Do not mention, advertise, or offer tools unless they are genuinely relevant to the
  current conversation or the user asked for an action that requires one.
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

Conversation continuity:
- Mairon Core may supply small excerpts from a private local conversation journal.
- Those excerpts represent real prior dialogue and may be used for continuity,
  accurate recall, earned callbacks, and recognising ongoing discussions.
- A prior Mairon statement proves what Mairon previously said; it does not by itself
  prove that the underlying factual claim was correct.
- Never invent additional conversation history around retrieved excerpts.

Persistent memory:
- Explicit persistent fact memory is separate from the private conversation journal.
- Only save information to explicit persistent fact memory when {input_name} explicitly
  asks you to remember, save, or store it.
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
# Voice input
# --------------------------------------------------

voice_model = None
voice_mode = False
tts_state = None
speak_next_response = False


def normalise_voice_input(text):
    """
    Apply tiny, conservative transcription corrections.

    Whisper commonly hears "Mairon" as "Myron". Only fix
    likely wake/name usage at the beginning of an utterance
    rather than replacing the word globally.
    """

    value = text.strip()

    if not value:
        return value

    # There is no Myron. There is only Mairon.
    #
    # Whisper strongly prefers common spellings such as "Myron".
    # Oliver has explicitly chosen to treat these likely variants as
    # Mairon anywhere in voice transcripts rather than only at the
    # beginning of the utterance.
    value = re.sub(
        r"\b(myron|miron|mayron|mairon)\b",
        "Mairon",
        value,
        flags=re.IGNORECASE
    )

    return value


def ensure_voice_model():
    """
    Lazy-load Whisper only when voice input is first used.

    This keeps normal typed startup fast and avoids loading
    the STT model when voice is not needed.
    """

    global voice_model

    if voice_model is None:
        print()
        print("[Voice] Loading local speech recognition...")

        voice_model = load_model()

        print("[Voice] Ready.")
        print()

    return voice_model


def ensure_tts():
    """
    Lazy-load Mairon's local TTS engine only when a spoken
    response is actually required.
    """

    global tts_state

    if tts_state is None:
        print()
        tts_state = load_tts()
        print()

    return tts_state


def speak_response(text):
    """
    Speak one final Mairon response locally.
    """

    if not text:
        return

    state = ensure_tts()

    print("[Voice] Speaking...")

    speak(
        state,
        text,
    )


def capture_voice_input():
    """
    Capture one local microphone utterance and return text.

    Raw microphone audio is kept in memory for transcription.
    This function does not save a WAV/audio recording to disk.
    """

    global speak_next_response

    model = ensure_voice_model()

    audio = record_until_enter()

    result = transcribe_audio(
        model,
        audio
    )

    transcript = normalise_voice_input(
        result["text"]
    )

    print()

    if transcript:
        print(
            f"You [voice]: {transcript}"
        )
    else:
        print(
            "[Voice] No speech recognised."
        )

    print()

    if transcript:
        speak_next_response = True

    return transcript


def get_user_input():
    """
    Read the next user message from keyboard or microphone.

    Commands:
      /voice      - record one voice message
      /voice on   - make voice the default input mode
      /voice off  - return to keyboard input
    """

    global voice_mode
    global speak_next_response

    speak_next_response = False

    while True:
        if voice_mode:
            print(
                "[Voice mode] Press Enter to record, "
                "or type /voice off to return to keyboard."
            )

            command = input(
                "Voice: "
            ).strip()

            normalised_command = (
                command.lower().rstrip("\\")
            )

            if normalised_command == "/voice off":
                voice_mode = False

                print(
                    "[Voice] Continuous voice mode disabled.\n"
                )

                continue

            if command:
                print(
                    "[Voice] In voice mode, press Enter to record "
                    "or use /voice off."
                )

                continue

            return capture_voice_input()

        user_input = input(
            "You: "
        ).strip()

        command = (
            user_input.lower().rstrip("\\")
        )

        if command == "/voice":
            return capture_voice_input()

        if command == "/voice on":
            voice_mode = True

            print(
                "[Voice] Continuous voice mode enabled.\n"
            )

            continue

        if command == "/voice off":
            print(
                "[Voice] Voice mode is already disabled.\n"
            )

            continue

        return user_input


# --------------------------------------------------
# Conversation state
# --------------------------------------------------

local_state = None
cloud_state = None


# --------------------------------------------------
# Main conversation loop
# --------------------------------------------------

while True:
    try:
        user_input = get_user_input()

    except KeyboardInterrupt:
        print(
            "\nMairon: Shutting down."
        )
        break

    except Exception as error:
        print(
            f"\n[Voice] Input failed: {error}\n"
        )
        continue

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

    # --------------------------------------------------
    # Private local conversation journal
    # --------------------------------------------------
    #
    # Record only completed user<->Mairon turns. This is local
    # continuity/history, not explicit persistent fact memory.
    #
    # Raw microphone audio is never written here; only the transcript
    # and final visible Mairon response are stored.
    try:
        record_conversation_turn(
            user_text=user_input,
            assistant_text=result.answer,
            channel=(
                "voice"
                if speak_next_response
                else "text"
            ),
        )

    except Exception as error:
        # Continuity must degrade gracefully. A journal failure should
        # never prevent Oliver from using Mairon.
        print(
            f"[Context] Conversation journal write failed: {error}"
        )

    if speak_next_response:
        try:
            speak_response(
                result.answer
            )

            print()

        except KeyboardInterrupt:
            print(
                "\n[Voice] Speech stopped.\n"
            )

        except Exception as error:
            print(
                f"\n[Voice] TTS failed: {error}\n"
            )