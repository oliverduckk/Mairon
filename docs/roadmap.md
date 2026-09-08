# Mairon Development Roadmap

_Last updated: 7 September 2026_

This is the current high-level roadmap and handoff document for Mairon.

It is intended to be pasted or uploaded into a fresh Mairon development chat so the project can continue without re-explaining the entire build history.

---

# Project Vision

Mairon is a private-first personal AI assistant with a Core-owned authority model, persistent local state, safe access to approved tools/devices, and an eventual always-on Raspberry Pi presence.

The long-term architecture is:

```text
                    Phone / Remote Client
                            │
                            ▼
                 ┌─────────────────────┐
                 │   Raspberry Pi 5    │
                 │                     │
                 │ Always-on Mairon    │
                 │ Core / state        │
                 │ Wake word           │
                 │ STT / TTS           │
                 │ Routines            │
                 │ Permissions         │
                 │ Coordination        │
                 └─────────┬───────────┘
                           │
             ┌─────────────┴─────────────┐
             ▼                           ▼
    ┌─────────────────┐        ┌─────────────────────┐
    │ Windows Desktop │        │ External Services   │
    │                 │        │                     │
    │ Desktop Agent   │        │ Gmail / Calendar    │
    │ RTX 5080 node   │        │ Weather / Web       │
    │ Local files     │        │ Routes / APIs       │
    │ Windows actions │        │ Future integrations │
    └─────────────────┘        └─────────────────────┘
```

## Core engineering philosophy

- Local-first whenever practical.
- Private data stays local unless explicitly approved otherwise.
- Cloud AI is optional and permission-controlled.
- Core owns truth, permissions, state and deterministic workflows.
- Models provide language, personality and lightweight reasoning over supplied evidence.
- Qwen does **not** decide what is true.
- Prior assistant prose is dialogue continuity, not factual evidence.
- If a joke requires a fact, Core must actually possess that fact.
- Domain-specific authoritative routing must beat generic conversational routing.
- Consequential actions fail closed.
- The model never receives unrestricted shell/system authority.
- Personality sits on top of facts rather than inventing them.
- Fix semantic/mechanical classes of bugs rather than endlessly adding sentence-specific regexes.

---

# Current Project Snapshot

## Repository / development environment

- Project root: `C:\Projects\Mairon`
- Python virtual environment: `.venv`
- Test runner:

```powershell
python tests/run_all.py
```

- Development/debug Core:

```powershell
python src/main.py
```

- Windows Desktop Agent:

```powershell
python src/desktop_agent.py
```

- Standalone Windows launcher:
  - `Mairon.pyw`
  - Start/taskbar shortcut installed
  - custom Mairon `.ico`
  - no VS Code/PowerShell window required for ordinary use

## Current model setup

- Local default: `qwen3.5:9b`
- Optional cloud escalation: GPT-5.6 Luna
- Cloud escalation remains permission-gated.
- Desktop RTX 5080 is intended to become an optional heavy-compute node, not Mairon's permanent always-on brain.

## Current voice stack

Desktop voice MVP is already functional:

- GUI microphone button.
- Local microphone capture.
- Local STT.
- Transcript passed through the existing Mairon Core.
- Local TTS.
- Voice replies work in the Windows app.
- Current direction remains:
  - wake word later;
  - Pi hosts always-on voice later.

## Testing state

Last explicitly confirmed full regression pass in this development chat:

```text
109 passed
0 failed
```

That was after Phase 10.5.4 arithmetic power follow-ups.

Phase 10.6 subsequently added more tests (113+ discovered), and the session / rename / delete functionality has been live-tested successfully, but the latest semantic-title work still has an unresolved live issue. Do not assume the current latest 10.6 branch has a fully confirmed green suite until rerun.

---

# Completed Capability Foundations

## 1. Core / Authority / Conversation Foundation

**Status: STRONG V1 COMPLETE**

- Local and cloud model-provider architecture.
- Local-first routing.
- Explicit cloud escalation.
- Runtime local date/time authority.
- Conversation state separate from model prose.
- Referent handling.
- Epistemic routing: Core decides how a fact should be known.
- Answer Contracts.
- Claim grounding / source-lock behaviour.
- Restricted generation context where required.
- Persistent preferences.
- Conversation journal.
- Recent/temporary context.
- Long-term local memory.
- Personality identity stored separately from model.
- Safety rules against invented embodiment/perception.
- Multiple rounds of conversational acceptance tests passed.

### Important architecture

```text
User
 ↓
Turn State
 ↓
Intent / Speech Act
 ↓
Conversation / Referent State
 ↓
Epistemic Router
 ↓
Authoritative workflow/data/evidence
 ↓
Answer Contract
 ↓
Personality model
 ↓
Output validation
 ↓
User
```

---

## 2. External Information / Personal Services

**Status: STRONG V1**

### Web / weather

- Web search.
- Webpage reading.
- Weather integration.
- Public-data tooling available to local model.
- Cloud access constrained by privacy boundary.

### Google Calendar

- Read events.
- Upcoming/next event.
- Calendar in routine/day workflows.
- Permission-gated Calendar writes.
- Event creation backend.

### Gmail

- Read-only OAuth.
- Search Gmail.
- Read specific emails.
- Follow-up handling.
- Inbox attention / triage.
- ACTION NEEDED / FYI / IGNORE classification.
- Marketing noise suppression.
- Gmail content remains private from cloud model.
- Fast email fallback path and evidence compaction implemented.

### Routes

- Google Routes API.
- Driving.
- Traffic-aware estimates.
- Public transport.
- Park-and-ride.
- Preferred work route.
- Conversational route follow-ups.
- Trusted private aliases.

### Routines / alarms

- Weekly routine state.
- WFH/office overrides.
- Day overview.
- Night Routine.
- Morning Routine.
- Alarm state management.
- Manual wake alarms override routine alarms.
- Disabled alarms stay disabled.
- Physical always-on alarm runner is still future Pi work.

---

# Phase 8 — Desktop Actions v1

**Status: COMPLETE**

Mairon can safely control approved parts of the Windows desktop.

## Applications

- Allowlisted open.
- Close.
- Focus.
- Verified foreground focus.
- No arbitrary executable/shell authority.

## Trusted browser actions

Trusted sites include:

- Google
- YouTube
- Reddit
- GitHub
- Gmail

Core owns trusted destination authority.

The Desktop Agent receives structured trusted-site requests rather than arbitrary URLs.

Browser-context close remains deliberately conservative:
- `close YouTube` / `close it` after a browser action will not blindly close Chrome.
- explicit `close Chrome` can close the application.

## Local files

Approved roots include the Mairon project and trusted user folders.

Features:

- deterministic local file search;
- ambiguity handling;
- ordinals;
- extension selection;
- approved-root validation;
- safe file/folder open;
- Core validates Agent-returned candidates;
- Agent independently revalidates execution paths;
- no arbitrary filesystem execution.

Cold search timeout was fixed with an action-specific timeout rather than weakening all Agent calls.

## Steam

- list installed Steam games;
- resolve game names / acronyms / learned aliases;
- launch via Steam AppID;
- UI/app boundary handled through Desktop Agent;
- deictic `close it` after a Steam game is safe and truthful;
- verified safe game termination is intentionally not implemented yet.

---

# Phase 9 — Windows Desktop Agent Boundary

**Status: COMPLETE V1**

Architecture:

```text
Mairon Core
    ↕ authenticated localhost IPC
Windows Desktop Agent
    ↓
trusted Windows actions
```

Current properties:

- localhost only;
- shared local secret;
- protocol v1;
- bounded request sizes;
- allowlisted actions only;
- no arbitrary command/shell/function/executable path;
- fail closed when Agent unavailable;
- no silent local fallback;
- request IDs;
- browser/file/Steam/application actions migrated across boundary.

Current approved action families include:

- ping;
- launch/close/focus application;
- trusted browser site/search;
- approved local file search/open;
- trusted folders;
- list installed Steam games;
- launch Steam AppID.

This boundary is the basis for the future Pi → Windows connection.

---

# Phase 10 — Windows Desktop Application

**Status: FOUNDATION COMPLETE / UX DEVELOPMENT ACTIVE**

## Phase 10.1 — Application-service boundary

**COMPLETE**

- `src/application_service.py` provides the UI-neutral application boundary.
- Desktop UI does not directly bypass Core/router/provider permissions.
- Existing Core is reused rather than duplicated for GUI use.

## Phase 10.2 — Visual shell

**COMPLETE V1**

Current design:

- Mairon dark theme:
  - main background `#1A1B2F`
  - accent `#D44963`
  - sidebar/composer `#16213E`
  - hover/secondary accent `#552C4A`
  - border `#343157`
- Inter / Plus Jakarta Sans direction.
- Left sidebar.
- Chat message bubbles.
- Composer.
- Upload placeholder button.
- microphone button.
- send button.
- animated `...` thinking indicator.
- response timing.
- system/Agent status.

## Phase 10.3 — Native GUI voice

**COMPLETE V1**

- microphone control;
- local STT;
- Core request;
- local TTS;
- voice integrated into desktop app rather than a separate workspace tab.

## Phase 10.4 — Windows launcher / taskbar / native behaviour

**COMPLETE**

A long Win32/Tk cleanup produced a normal Windows application:

- standalone `Mairon.pyw`;
- custom taskbar icon;
- Windows AppUserModel identity;
- single-instance handling;
- clicking pinned Mairon does not create duplicate app instances;
- native title bar;
- native drag/snap;
- normal minimise / restore behaviour;
- normal taskbar grouping;
- scrolling conversation surface;
- themed scrollbar;
- normal-weight composer font;
- improved typography.

The final decision was to **stop faking Windows chrome in Tk** and let Windows own the native title bar while DWM themes it to Mairon's palette.

---

# Phase 10.5 — Deterministic Arithmetic Authority

**Status: COMPLETE**

This phase was created after Mairon interpreted:

```text
add 557, 528, 527, 493, 452 and 1118
```

as if Oliver wanted numbers added to a list.

Arithmetic is now Core-owned.

Examples:

```text
add 557, 528, 527, 493, 452 and 1118
→ The total is 3,675.

double it
→ 7,350

half it
→ 3,675

triple it
→ 11,025

square it
→ 13,505,625

cube it
→ deterministic Core result
```

Implemented:

- safe arithmetic parser/evaluator;
- no Python `eval`;
- addition/subtraction/multiplication/division;
- percentages;
- simple symbolic expressions;
- powers;
- arithmetic follow-up referents;
- chained verified-result operations;
- division-by-zero handling;
- arithmetic authority outranks generic `"I meant..."` correction routing.

### Deliberately not doing

Do not turn arithmetic into an endless regex project.

Example currently outside deterministic v1:

```text
divide it by pi
```

Future richer maths should use one coherent safe maths normaliser/constants/functions engine rather than adding one sentence pattern at a time.

---

# Phase 10.6 — Conversation Sessions / Chat History

**Status: ACTIVE**

## Phase 10.6.1 — Real chat sessions

**WORKING**

Implemented:

- real session IDs;
- persistent local session database;
- `New Chat` creates an actual clean short-term conversation;
- Core/model conversational state resets between chats;
- previous chats persist;
- recent chats appear in sidebar;
- clicking a chat restores transcript;
- Core state snapshot restores authoritative referents;
- reopening a chat does **not** replay old actions.

Important example:

```text
Chat A
add 10 and 5
→ 15

New Chat
double it
→ must NOT inherit Chat A

Reopen Chat A
double it
→ 30
```

## Phase 10.6.2 — Rename / delete / automatic titles

### Rename + delete

**WORKING**

- `⋯` menu on chat rows.
- Right-click fallback.
- Manual rename.
- Manual rename remains authoritative.
- Delete with confirmation.
- Deleting active chat creates a fresh `New Chat`.
- Long sidebar titles are visually ellipsized so the menu remains visible.

### Stable auto-title

**WORKING**

Initial bug:
- automatic title was regenerated on every message.

Fixed:
- automatic title is created only from the first completed turn;
- later messages do not change it;
- manual titles never get overwritten.

### Phase 10.6.2.2 — Semantic auto titles

**CURRENT / NOT WORKING CORRECTLY IN LIVE APP**

Goal:

```text
"can you explain Starlink to me and tell me if it is worth the price"
→ Starlink Overview
```

rather than:

```text
Can You Explain Starlink to Me and Tell Me...
```

Current intended implementation:

- deterministic fallback title immediately;
- isolated background Qwen call;
- first user message + first assistant answer only;
- no tools;
- no conversation state;
- no factual authority;
- short 2–6 word title;
- one-time semantic upgrade;
- manual rename always wins;
- desktop refresh after background title completes.

### Current live bug

Despite the implementation, general chats are still displaying the cleaned/truncated first message rather than the semantic title.

Examples seen:

```text
Can You Explain Starlink to Me and Tell Me...
Can You Provide Me with a Synopsis for the...
```

Arithmetic titles work because Core has a deterministic title rule:

```text
Arithmetic Calculation
```

**Next action:** debug why the isolated title generator or one-time semantic-title update is not being applied/persisted/refreshed.

Do not add more title heuristics until the actual semantic-title pipeline is diagnosed.

---

# Immediate Known Bugs / Next Fixes

These were discovered during live testing and should be handled before piling on more UI features.

## 1. Semantic chat titles not applying

**Priority: HIGH / CURRENT**

- fallback title persists;
- determine whether:
  - local title model call is failing;
  - title output is rejected by cleaner;
  - background thread is not completing;
  - `apply_semantic_chat_title()` is refusing the current `title_origin`;
  - UI refresh occurs before/without the persisted semantic title;
  - local provider shape passed into the generator is wrong.

Development should be done through VS Code/terminal first so logs can show the exact failure.

## 2. Factual hallucinations on named works / knowledge questions

**Priority: HIGH**

Live failures:

### Shadow Slave

Mairon invented a completely incorrect synopsis involving:
- a character named Niall;
- an ability named `"Shadow Slave"`;
- invented worldbuilding.

### The Beginning After the End

Mairon incorrectly said:
- the protagonist was `"King"` reincarnated as Arthur;
- Arthur was raised by adoptive parents;
- other fabricated story details.

This is not acceptable factual behaviour.

### Required architectural direction

For named factual entities / works where correctness matters:

```text
User factual question
 ↓
Core decides whether model memory is sufficient
 ↓
if verification needed:
    web search / authoritative sources
 ↓
evidence
 ↓
Answer Contract
 ↓
Mairon response
```

Do not simply try to improve the personality prompt.

This is an epistemic-routing / factual-grounding problem.

## 3. Correction turn misrouted to Gmail

After being corrected about TBATE, Oliver said:

```text
YOU HAVE THE INTERNET TO LOOK SHIT UP.
YOU SHOULDN'T NEED ME TO EXPLAIN IT TO YOU
```

Mairon replied:

```text
Which email do you want me to read?
```

This is a routing failure.

Likely causes to inspect:
- Gmail follow-up / read-email intent too broad;
- previous context leaking incorrectly;
- generic `"read"`/information wording matching email intent;
- correction/factual-verification intent losing precedence.

Fix the routing class, not the exact sentence.

## 4. Chat text cannot be selected/copied

**Priority: MEDIUM / UX**

Current Tk message bubbles render text in a way that prevents normal mouse text selection.

Desired behaviour:

- drag-select user or Mairon message text;
- Ctrl+C;
- right-click Copy;
- ideally `Ctrl+A` only inside focused selectable message rather than hijacking whole app.

Possible implementation direction:
- use read-only `Text` widgets or another selectable text surface inside message bubbles;
- preserve bubble appearance;
- do not make chat messages editable.

---

# Next Planned Development Stages

## Phase 10.6.2.3 — Semantic-title reliability

**NEXT**

- instrument title-generation path;
- fix provider/title persistence/update problem;
- confirm broad ChatGPT-style titles;
- ensure title generation cannot overwrite manual names;
- confirm no response latency regression.

Definition of done:

```text
new general chat
→ first response appears normally
→ within a few seconds sidebar/header becomes a concise topic title
→ later turns never rename it
```

## Phase 10.6.3 — Better conversation-history UX

After titles are reliable:

- more than six recent chats;
- sidebar scroll for chat list;
- history search/filter;
- grouping such as:
  - Today
  - Yesterday
  - Previous 7 Days
  - Older
- rename/delete polish;
- possibly archive later.

Do not overbuild this before factual correctness fixes.

## Phase 10.7 — General Factual Web Authority / Grounding

**HIGH PRIORITY**

Goal: stop Qwen confidently inventing facts for named works, products, people, technologies and other factual topics.

Likely work:

- classify named-entity factual questions;
- decide when local model memory is insufficient;
- use existing web search/page-reading tools;
- prefer official/high-quality sources;
- build compact evidence;
- answer from evidence;
- deterministic fallback if evidence fails;
- preserve personality only after factual claims are grounded.

Regression cases should include:
- Shadow Slave synopsis;
- TBATE synopsis;
- Starlink overview/current pricing questions;
- corrections after a hallucinated factual answer.

## Phase 10.8 — Selectable / Copyable Chat Messages

- selectable text in bubbles;
- Ctrl+C;
- right-click Copy;
- preserve current styling;
- no accidental editing;
- potentially message-level copy button later.

## Phase 10.9 — Desktop App UX / Diagnostics

Potential additions:

- optional developer diagnostics panel:
  - detected intent;
  - authority;
  - workflow;
  - model;
  - Agent action;
  - timings;
- useful during development instead of requiring terminal logs for everything.
- Keep normal user UI clean when diagnostics are off.

---

# Raspberry Pi Direction

## Why the Pi is now increasingly justified

Mairon is becoming a persistent assistant rather than merely a desktop chatbot.

The Pi will eventually provide:

- always-on Core;
- wake word;
- microphones;
- TTS;
- alarms;
- routine execution;
- persistent state;
- remote coordination;
- desktop wake coordination.

The Windows desktop remains the heavy node.

## Desktop wake policy

Current intended policy:

```text
Desktop already online
→ use it when appropriate

Desktop offline + Oliver explicitly says "turn my PC on"
→ wake immediately

Desktop offline + requested task inherently requires PC
→ ask Oliver before waking it

Desktop offline + task can be completed on Pi/cloud
→ do not wake PC
```

Default future setting:

```text
Desktop wake policy: Always ask
```

except when Oliver explicitly requested the PC be turned on.

## Typical Pi → PC use cases

Most RTX 5080-heavy work will happen while Oliver is already sitting at the PC.

The Pi will more often wake the PC for:

- explicit `"turn my PC on"`;
- remote file/document retrieval while Oliver is away;
- rare local/private heavy-compute tasks.

## Power-state direction

Do not repeatedly boot/shutdown the desktop for tiny jobs.

Preferred future model:

```text
sleep
→ Wake-on-LAN
→ task
→ grace period
→ return to sleep if Mairon woke it and user is not actively using it
```

Mairon must track whether **it** woke the desktop before deciding whether it may return it to sleep.

Never blindly shut down an actively used PC.

---

# Future Phase — Raspberry Pi Core

**PLANNED AFTER DESKTOP/CORE RELIABILITY**

Hardware direction:

- Raspberry Pi 5 8GB;
- official 27W PSU;
- active cooler;
- 256GB NVMe + official M.2 HAT+;
- setup/recovery microSD;
- Ethernet;
- USB/far-field microphone;
- USB audio/speaker;
- optional RTC/UPS later.

Pi work:

- Linux Mairon service;
- boot startup;
- crash recovery;
- secure state migration;
- wake word `"Mairon"`;
- STT/TTS;
- physical alarm runner;
- secure Pi ↔ Windows Desktop Agent transport;
- WOL;
- PC state detection;
- health/status endpoint;
- logs;
- backups.

---

# Future — Secure Remote File Retrieval

Important target use case:

```text
Oliver away from home:
"Mairon, send me my resume from the PC."
```

Desired flow:

```text
Phone
 ↓
Pi/Core
 ↓
resolve approved file request
 ↓
desktop offline?
 ↓
ask permission to wake it
 ↓
Wake-on-LAN
 ↓
authenticated Desktop Agent online
 ↓
find approved candidate
 ↓
Core validates referent/candidate
 ↓
secure transfer
 ↓
phone receives file
 ↓
confirm only after transfer succeeds
```

No general Windows file share exposed to the internet.

Long-term remote-safe file authority may use opaque Agent-issued file/capability IDs rather than raw Windows paths.

---

# Future — Wake Word / Always-On Voice

Desktop GUI voice already proves the speech loop.

Next voice milestone after Pi:

```text
"Mairon"
 ↓
wake detector
 ↓
local STT
 ↓
Core
 ↓
response
 ↓
local TTS
 ↓
short follow-up listening window
```

Planned:

- wake word `"Mairon"`;
- local detection;
- activation chime;
- follow-up window;
- silence timeout;
- `"thanks" / "stop" / "never mind"` termination;
- avoid self-triggering on TTS;
- eventual barge-in/interruption.

---

# Future — Generic Permission Framework

Current approvals are capability-specific.

Eventually build reusable action permissions:

- low risk: auto-approved;
- medium risk: confirmation;
- destructive/high consequence: strong confirmation;
- audit log;
- expiring/standing permissions;
- revoke standing permission;
- remote approval UI.

Future Desktop Power Authority should use this framework.

---

# Future — Proactive Mairon

Move from:

```text
User asks → Mairon answers
```

toward:

```text
Relevant event occurs
→ Core decides whether it is worth interrupting Oliver
→ notify only when useful
```

Possible:

- reminders;
- Calendar preparation;
- important email follow-up;
- weather warnings;
- delivery notifications;
- routine anomalies;
- university deadlines;
- project reminders.

Principle:

> Mairon should not become a notification spam machine.

---

# Future — Phone / Remote Mairon

- secure phone app or web client;
- authentication;
- encrypted Pi connection;
- no raw Windows exposure;
- text;
- voice;
- push notifications;
- remote approvals;
- Calendar/Gmail;
- WOL;
- file retrieval;
- travel mode.

---

# Future — Smart Home / Devices

Only after Core/voice/Pi reliability:

- lights;
- scenes;
- bedroom controls;
- controlled PC actions;
- safe device allowlist;
- device state before action;
- consequence-based confirmation.

---

# Future — Personal Context Features

Parked until core architecture is ready.

Potential domains:

- fitness/workout rotation;
- Garmin recovery/sleep;
- university timetable/assignments/exams;
- work/WFH context;
- travel itinerary/packing/travel mode;
- reading/watch state;
- shopping/chore lists;
- package tracking;
- sports;
- music;
- network/home-server diagnostics.

---

# Engineering Quality — Ongoing

## Regression discipline

Do not assume every failed old test means production should be rolled back.

Historical examples include fossil fixtures after intentional architecture changes.

Classify each failure as:

```text
production bug
vs
stale fixture
```

before changing working production code.

## Current test philosophy

- standalone tests;
- full `python tests/run_all.py`;
- live terminal acceptance;
- desktop app smoke test;
- inspect real routing logs when behaviour is suspicious.

Development should primarily use VS Code / `src/main.py` when debugging because it exposes:

```text
[Core] intent -> authority
[AI] provider/model
[Grounding]
[Context]
[Desktop Agent]
[Timing]
```

The Windows app is the final user-experience acceptance surface.

## Before replacements

- work from latest lineage;
- prefer full replacement files;
- do not reconstruct stale versions;
- verify file markers/rough size where useful;
- restart imported Python processes after replacement because modules do not hot-reload.

## Git discipline

At a milestone:

```powershell
git status --short
```

Review expected files before:

```powershell
git add ...
git commit -m "..."
git push origin main
```

Never stage:

- `.env`
- `.venv`
- `data/`
- private OAuth/token files
- local editor state

Do not claim a push happened without explicit confirmation/output.

---

# Current Important File Lineage

As of this roadmap, the intended latest implementation is approximately:

```text
src/main.py
    terminal/debug client

src/application_service.py
    Phase 10.6.2.2 session + semantic-title integration

src/desktop_app.py
    Phase 10.6.2.2 desktop UI

src/continuity/chat_session_store.py
    Phase 10.6.2.2 sessions / rename / delete / title provenance

src/continuity/chat_title_generator.py
    Phase 10.6.2.2 isolated local semantic title generator

src/core/arithmetic.py
    Phase 10.5.4 deterministic arithmetic + result/power follow-ups

src/core/workflows/arithmetic.py
    deterministic arithmetic workflow

src/core/intent_router.py
    Phase 10.5.x arithmetic precedence layered on existing routing

src/core/epistemic_router.py
    deterministic arithmetic authority

src/core/orchestrator.py
    arithmetic workflow integrated into Core

src/desktop_agent.py
    Windows Desktop Agent boundary

src/core/desktop_agent_protocol.py
src/core/desktop_agent_client.py
    authenticated bounded Desktop Agent IPC
```

Older app/browser/file/Steam workflow modules remain part of the working stack.

---

# Current Immediate Development Order

Do these in order unless a newly discovered bug changes priority:

1. **Fix semantic auto-title pipeline.**
2. **Fix named factual-question grounding / hallucination problem.**
3. **Fix the bizarre Gmail misroute after factual correction.**
4. **Make chat message text selectable/copyable.**
5. Improve history/search/grouping UX.
6. Add optional developer diagnostics inside the app.
7. Continue preparing the Core/Desktop boundary for Pi.
8. Raspberry Pi always-on Core.
9. Wake word / physical alarms / Pi voice.
10. Secure remote phone/file retrieval.
11. Generic permission framework.
12. Proactive/device/smart-home features.

---

# New-Chat Handoff Instructions

When continuing development in a new ChatGPT project chat:

1. Upload/paste this roadmap.
2. State that it is the current Mairon handoff document.
3. For architectural discussion, this document is enough.
4. For code replacement work, provide the **latest exact source files being modified** if the new chat does not already have them.
5. A full repository ZIP is not necessary for every conversation, but it is useful when:
   - many interdependent files need inspection;
   - lineage is uncertain;
   - the new chat needs a full architecture audit.
6. Prefer individual latest files for small phases.
7. Do not let a new chat regenerate old files from memory when exact current files are available.

---

# Current Milestone

## Mairon Windows Desktop Client + Persistent Conversation UX

The current objective is:

```text
Reliable Core
+ safe Windows actions
+ standalone desktop app
+ voice
+ persistent chat sessions
+ correct factual authority
```

The immediate blocker is **not** Raspberry Pi hardware.

The immediate blockers are:

```text
semantic title reliability
+
general factual grounding
+
routing correctness
+
basic selectable/copyable chat UX
```

Once these are stable, the project can move confidently toward the Pi without carrying avoidable desktop/Core correctness problems into the always-on architecture.
