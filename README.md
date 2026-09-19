# Mairon

**Current build: v0.2-dev**  
**Current development state: Phase 11.5.4 complete — Grounded Final Synthesis**  
**Regression baseline: 154 / 154 passing**

Mairon is a local-first, privacy-conscious personal AI assistant built around a deterministic Core rather than a single unrestricted language-model loop.

The long-term goal is an always-available personal assistant that can converse naturally, use private tools safely, remember useful context, work by text and voice, perform grounded research, and eventually run across desktop, Raspberry Pi, home devices, and mobile access.

Mairon is still under active development. It is not intended to be a finished general-purpose assistant yet.

---

## Current architecture

Mairon's central design rule is simple:

> **The language model does not decide what is true or what it is allowed to do. Core does.**

A simplified interaction looks like this:

```text
User
  |
  v
Conversation / turn state
  |
  v
Intent + speech-act routing
  |
  v
Epistemic routing
  |
  +----> Core-owned deterministic workflows
  |
  +----> Private/local tools
  |
  +----> Public factual research
  |
  v
Grounded evidence / authoritative state
  |
  v
Answer Contract
  |
  v
Personality / language generation
  |
  v
Grounding + response validation
  |
  v
Final output
```

The model is downstream of Core. Core owns routing, permissions, tool state, durable workflow state, factual provenance, and validation.

---

## Models

### Local default

Mairon currently uses:

```text
qwen3.5:9b
```

through Ollama as the default local model.

The local model can be changed with:

```text
MAIRON_LOCAL_MODEL
```

### Cloud escalation

Cloud processing is optional and permission-controlled.

Current cloud escalation target:

```text
GPT-5.6 Luna
```

Mairon can recommend cloud processing when a task genuinely benefits from it, but Core does not silently send private work to the cloud.

A user can also explicitly request cloud processing from the terminal with:

```text
/cloud
```

---

## Interfaces

Mairon currently has two main local interfaces:

- a desktop chat application with persistent conversation sessions and chat history;
- a terminal interface at `src/main.py`.

The terminal also supports local voice input:

```text
/voice
/voice on
```

Voice is still part of the v0.2 development milestone. Wake-word operation and the later always-on physical architecture are not complete yet.

---

## Core capabilities

The current build includes a growing set of Core-owned capabilities, including:

- deterministic intent and speech-act routing;
- short-term conversational state and referent tracking;
- persistent local chat sessions;
- response Answer Contracts;
- claim grounding and source-lock validation;
- personality / social-generation constraints;
- deterministic arithmetic;
- persistent memory workflows;
- local system-information and allowlisted application actions;
- weather;
- routes;
- Google Calendar read/write with permission boundaries;
- Gmail read access;
- routines and alarms;
- web search and web reading;
- local voice input/output;
- optional permission-gated cloud escalation.

Private credentials, OAuth files, runtime databases, and other sensitive state are intended to remain outside source control.

---

## Background research

Mairon now supports durable background research jobs rather than treating research as one disposable model call.

The current research pipeline is:

```text
Explicit research request
        |
        v
Durable SQLite research job
        |
        v
Initial public evidence pass
        |
        v
Iterative deep research
        |
        +--> planner/query grounding
        +--> source + host diversity floors
        +--> hard research-round cap
        |
        v
Evidence collection complete
        |
        v
Grounded final synthesis
        |
        v
Persisted synthesis checkpoint
        |
        v
Evidence-grounded verification
        |
        +--> verified -> completed / user_ready
        |
        +--> unsupported -> review required
        |
        v
Delivery
```

### Phase 11.5.4 — Grounded Final Synthesis

Phase 11.5.4 is complete and live-tested.

The final report is generated only from the durable research request and collected evidence. Planner output is not treated as authoritative factual evidence.

The synthesis draft is persisted before verification so a restart or failure does not force Mairon to repeat the research.

The verifier fails closed: unsupported or structurally unverifiable reports are not silently marked complete.

A real Garmin smartwatch research job was used as the live integration test and successfully survived repeated research stages, migrations, restarts, synthesis checkpointing, verifier recovery, and final grounded verification.

Current durable completion state:

```text
status = completed
research_phase = final_synthesis_complete
next_stage = delivery
user_ready = true
final_report_verified = true
```

---

## Reliability and regression testing

Mairon has a growing regression suite covering Core routing, workflows, conversation behaviour, grounding, background research, durable recovery, and research synthesis.

Current baseline:

```text
Passed: 154
Failed: 0
Total discovered: 154
```

Run the complete regression suite with:

```powershell
python tests\run_all.py
```

Individual phase tests can also be run directly from `tests\`.

---

## Running Mairon

Activate the project's virtual environment and ensure the required local services and credentials are configured.

### Terminal

```powershell
python src\main.py
```

### Desktop application

```powershell
python src\desktop_app.py
```

### Local model

Ollama must be available for local generation. The current default model is:

```text
qwen3.5:9b
```

Service-specific integrations such as Calendar, Gmail, routes, and cloud escalation require their own local environment configuration and credentials.

Secrets should never be committed to Git.

---

## Development principles

Mairon is deliberately being built around a few rules:

1. **Local first.** Private or ordinary work should stay local whenever practical.
2. **Core owns authority.** Models generate language; Core owns state, permissions, provenance, and deterministic workflows.
3. **Fail closed.** If grounding or permission checks fail, Mairon should stop rather than bluff.
4. **Durable work.** Long-running jobs should survive restarts and continue from checkpoints.
5. **Explicit permissions.** Consequential or cloud actions should not happen merely because a model suggested them.
6. **Personality after truth.** Banter and character should never override factual correctness or safety.
7. **Regression before expansion.** Major milestones should keep the existing suite green before new capability work continues.

---

## Version milestones

Mairon's version numbers are informal development milestones rather than strict semantic-version releases.

### v0.1 — Brain

Core personal-assistant foundations:

- local/cloud model architecture;
- privacy boundaries;
- memory;
- private tools;
- weather/web;
- Gmail and Calendar;
- routines and alarms;
- deterministic routing and workflows.

**Status: complete.**

### v0.2-dev — Desktop, Voice and Conversational Intelligence

Current development era:

- desktop chat UI;
- persistent chat sessions;
- local STT/TTS;
- stronger conversational intelligence;
- grounding and Answer Contracts;
- background research;
- durable research recovery;
- grounded final synthesis;
- upcoming research delivery;
- wake word and richer voice behaviour still to come.

**Status: active.**

### v0.3 — Physical Mairon

Planned:

- Raspberry Pi always-on Core;
- microphones and speakers;
- desktop compute node;
- safe Wake-on-LAN;
- service/watchdog reliability.

### v0.4 — Home Assistant

Planned:

- safe smart-home/device control;
- proactive routines;
- expanded permission framework.

### v0.5 — Everywhere

Planned:

- secure phone access;
- remote notifications;
- travel/mobile context.

### v1.0

The long-term target is a reliable, private-first personal assistant that is useful across text, voice, home, desktop, and mobile contexts without giving a language model unrestricted authority over private data or actions.

---

## Next development target

The research pipeline now produces a verified report with:

```text
next_stage = delivery
```

The next research milestone is therefore **delivery**: surfacing completed verified background research naturally to the user instead of leaving the final report only in durable job state.

After that, development can continue toward reusable topic knowledge, refreshable research state, richer voice behaviour, and the later physical Mairon architecture.

---

## Project status

Mairon is a personal experimental project under active development. APIs, database schemas, commands, prompts, internal module boundaries, and version labels may change frequently while the architecture is still evolving.
