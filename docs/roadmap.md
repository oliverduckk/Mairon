# Mairon Development Roadmap

_Last updated: 17 September 2026_

This is the current high-level roadmap and project-state document for Mairon.

It supersedes the earlier 7 September 2026 roadmap. The older document was written before the full factual-grounding work, conversational-intelligence phases, and the persistent background-research architecture were completed.

For a fresh development chat, pair this roadmap with the latest **Project Mairon — Next-Chat Engineering Handover** and the exact current source files being modified.

---

# Project Vision

Mairon is a private-first personal AI assistant with:

- a Core-owned authority model;
- persistent local state;
- safe access to approved tools/devices;
- durable personal/contextual knowledge;
- optional cloud escalation;
- a Windows heavy-compute node;
- an eventual always-on Raspberry Pi Core;
- proactive/background work that remains subordinate to Oliver's active interactions.

Long-term architecture:

```text
                         Phone / Remote Client
                                  │
                                  ▼
                       ┌─────────────────────┐
                       │   Raspberry Pi 5    │
                       │                     │
                       │ Always-on Mairon    │
                       │ Core / state        │
                       │ Research jobs       │
                       │ Wake word           │
                       │ STT / TTS           │
                       │ Routines / alarms   │
                       │ Permissions         │
                       │ Coordination        │
                       └─────────┬───────────┘
                                 │
                    ┌────────────┴────────────┐
                    ▼                         ▼
          ┌─────────────────────┐   ┌─────────────────────┐
          │ Windows Desktop     │   │ External Services   │
          │                     │   │                     │
          │ Desktop Agent       │   │ Gmail / Calendar    │
          │ RTX 5080 node       │   │ Weather / Web       │
          │ Local files         │   │ Routes / APIs       │
          │ Heavy synthesis     │   │ Future integrations │
          └─────────────────────┘   └─────────────────────┘
```

---

# Core Engineering Philosophy

- Local-first whenever practical.
- Private data stays local unless explicitly approved otherwise.
- Cloud AI is optional and permission-controlled.
- Core owns truth, permissions, state and deterministic workflows.
- Models provide language, personality and bounded reasoning over supplied evidence.
- Qwen does **not** decide what is true.
- Prior assistant prose is dialogue/persona continuity, not factual evidence.
- Domain-specific authoritative routing beats generic conversational routing.
- If a joke requires a fact, Core must actually possess that fact.
- Consequential actions fail closed.
- The model never receives unrestricted shell/system authority.
- Personality sits on top of facts rather than inventing them.
- Fix semantic/mechanical bug classes, not exact benchmark sentences or entity names.
- For background research, quality matters more than speed.
- Deep research means careful evidence collection, not unlimited scope expansion.
- Active Oliver interaction always outranks background work.
- Production replacements must be based on exact current files, not stale snapshots.

Core architecture:

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
Authoritative workflow / data / evidence
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

# Current Project Snapshot

## Repository / development environment

```text
Project root: C:\Projects\Mairon
Python venv: .venv
```

Full regression suite:

```powershell
python tests/run_all.py
```

Terminal/debug client:

```powershell
python src/main.py
```

Desktop Agent:

```powershell
python src/desktop_agent.py
```

Standalone Windows launcher:

```text
Mairon.pyw
```

## Model setup

Local default:

```text
qwen3.5:9b
```

Optional cloud escalation:

```text
GPT-5.6 Luna
```

Desktop RTX 5080 is intended to become an opportunistic heavy-compute node rather than Mairon's permanent always-on brain.

## Testing state

Latest explicitly confirmed automated regression result:

```text
Passed: 153
Failed: 0
Total discovered: 153
```

This is the authoritative automated baseline as of 17 September 2026.

The latest live background-research acceptance has **not** yet been rerun after the newest changes because `src/ai/ollama_provider.py` currently has Pylance undefined-variable warnings for `_normalise_space`.

---

# Current Immediate Blockers

## 1. `ollama_provider.py` `_normalise_space` undefined

**Priority: IMMEDIATE**

Pylance currently reports nine undefined references to:

```text
_normalise_space
```

Visible locations:

```text
3732
3738
3744
3837
3844
3893
3941
3976
4156
```

Next action:

- inspect exact current `src/ai/ollama_provider.py`;
- determine whether calls should use an existing helper/import or whether the helper was lost during provider integration;
- preserve current provider architecture and compatibility strings;
- rerun targeted tests;
- rerun full suite;
- rerun live research acceptance.

## 2. Blank day-overview response in live terminal

Observed:

```text
what am i doing tomorrow?
```

Core correctly invoked:

```text
get_routine_context
get_calendar_events
get_wake_alarm
```

but returned a blank final Mairon message after ~46 seconds.

In the most recent visible run, background research logs appeared only after the foreground response returned, so the whole-turn research-preemption fix appears promising, but the blank answer itself remains unresolved.

After provider warnings are fixed, rerun this exact live case.

## 3. Background-research live re-acceptance

Need to verify the newest build in real execution, not only automated tests.

Required checks:

- foreground turn remains responsive;
- no background stage starts during active foreground work;
- idle grace begins after the foreground turn ends;
- topic cleanup works;
- planner-specific identities are evidence-grounded;
- research stays within the user's actual goal;
- source/query freshness reflects the current date;
- checkpoints and leases remain correct;
- no DB/file-handle regressions.

---

# Completed Foundation — Core / Authority / Conversation

**Status: STRONG V1**

Implemented:

- local/cloud provider architecture;
- local-first routing;
- explicit cloud escalation;
- runtime date/time authority;
- structured conversation state;
- referent handling;
- epistemic routing;
- Answer Contracts;
- claim grounding/source-lock behaviour;
- restricted generation context;
- persistent preferences;
- conversation journal;
- recent/temporary context;
- long-term local memory;
- personality identity separate from factual state;
- no invented embodiment/perception;
- multiple acceptance/regression rounds.

---

# External Information / Personal Services

## Web / weather

**STRONG V1**

- web search;
- webpage reading;
- weather integration;
- public-data tooling;
- privacy-aware cloud boundary.

## Google Calendar

**STRONG V1**

- read events;
- upcoming/next event;
- routine/day integration;
- permission-gated writes;
- event creation backend.

## Gmail

**STRONG V1**

- read-only OAuth;
- search;
- specific-email reads;
- follow-up handling;
- inbox attention/triage;
- ACTION NEEDED / FYI / IGNORE;
- marketing suppression;
- private content kept away from cloud model;
- compact evidence path;
- context-gated Gmail deictics.

## Routes

**STRONG V1**

- Google Routes API;
- driving;
- traffic-aware estimates;
- public transport;
- park-and-ride;
- preferred work route;
- conversational follow-ups;
- trusted private aliases.

## Routines / alarms

**STRONG V1**

- weekly routine;
- WFH/office overrides;
- day overview;
- night routine;
- morning routine;
- alarm state;
- manual wake-alarm override;
- disabled-alarm persistence.

Physical always-on alarm execution remains a future Pi capability.

---

# Phase 8 — Desktop Actions v1

**COMPLETE**

Applications:

- allowlisted open;
- close;
- focus;
- verified foreground focus;
- no arbitrary executable/shell authority.

Trusted browser actions include:

- Google;
- YouTube;
- Reddit;
- GitHub;
- Gmail.

Local file actions:

- deterministic search;
- ambiguity handling;
- ordinals;
- extension selection;
- approved-root validation;
- safe open;
- Core candidate validation;
- Agent revalidation.

Steam:

- installed-game enumeration;
- name/acronym/alias resolution;
- launch by AppID;
- safe browser/application boundaries.

---

# Phase 9 — Windows Desktop Agent Boundary

**COMPLETE V1**

```text
Mairon Core
    ↕ authenticated localhost IPC
Windows Desktop Agent
    ↓
trusted Windows actions
```

Properties:

- localhost only;
- shared local secret;
- protocol v1;
- bounded requests;
- allowlisted actions;
- no arbitrary shell/function/executable path;
- fail closed when unavailable;
- no silent local fallback;
- request IDs.

This remains the foundation for future Pi → Windows actions.

---

# Phase 10 — Windows Desktop Application

**FOUNDATION + MAJOR UX WORK COMPLETE**

Completed:

- UI-neutral application-service boundary;
- dark Mairon shell;
- native GUI voice;
- local STT/TTS;
- standalone launcher;
- custom taskbar identity;
- single-instance behaviour;
- native Windows title bar/snap/minimise/restore;
- conversation scrolling;
- persistent chat sessions;
- rename/delete;
- stable one-time titles;
- semantic titles;
- selectable/copyable message text;
- history UX improvements;
- native resizable sidebar;
- developer diagnostics drawer.

Old roadmap blockers for semantic titles and selectable message text are no longer current blockers.

---

# Phase 10.5 — Deterministic Arithmetic Authority

**COMPLETE**

Core-owned arithmetic includes:

- addition/subtraction/multiplication/division;
- percentages;
- simple symbolic expressions;
- powers;
- result follow-ups;
- double/half/triple/square/cube;
- division-by-zero handling;
- safe evaluation without Python `eval`.

Future richer maths should use a coherent safe maths engine rather than endless regex additions.

---

# Phase 10.6 — Conversation Sessions / History

**COMPLETE ENOUGH**

Implemented:

- persistent session IDs;
- local session DB;
- clean new-chat state;
- transcript restore;
- authoritative Core state snapshot restore;
- no replay of old actions;
- recent-history sidebar;
- rename/delete;
- manual-title authority;
- semantic auto-title;
- later-turn title stability;
- selectable messages;
- improved history UX.

---

# Phase 10.7 — General Factual Authority / Grounding

**SUBSTANTIALLY COMPLETE**

This phase solved the earlier named-work/product hallucination architecture rather than merely prompting Qwen harder.

Completed areas:

## 10.7.1 — Media research reliability

- stronger public-source path for named works;
- better evidence handling.

## 10.7.2 — Direct public-source evidence

- page/source evidence over free model memory for current/specific named facts.

## 10.7.3 — Spoiler-safe quality

- research and responses respect spoiler constraints.

## 10.7.4 — Medium fidelity

- manga/light novel/web novel/anime/etc. distinctions preserved where relevant.

## 10.7.5 — Evidence coverage/source diversity

- wider support for factual claims;
- less single-source dependence.

## 10.7.6 — Authority weighting

- stronger sources preferred.

## 10.7.7 — Answer-scope authority

- sources must support the scope actually answered.

## 10.7.8 — Verified sentence salvage

- preserve supported parts rather than discarding the entire answer when one claim fails.

## 10.7.9 — Structured verifier

- explicit claim/evidence verification.

## 10.7.10 — General factual authority

Important distinction:

```text
stable definitions / explanations
→ local_model_knowledge / stable_model_knowledge

current / specific / exact / named facts
→ public web evidence
```

## 10.7.11 — Integration boundaries

- factual-grounding rules integrated without letting generic model prose override Core.

## 10.7.12 — Public factual projection guard

A verified current fact does not license unsolicited future prediction.

Important Answer Contract boundary includes the idea:

```text
Do not extrapolate a verified current fact into a prediction.
```

## 10.7.13 — Context-gated Gmail deictics

- deictic email handling constrained to real Gmail context.

---

# Phase 10.10 — Pi/Desktop Preparation

Completed:

```text
10.10.1 handshake ✅
10.10.2 wake decision ✅
10.10.3 presence + wake config ✅
```

Hardware boundary intentionally paused after this point.

No Pi purchase yet.

---

# Phase 11 — Conversational Intelligence

Benchmark dimensions:

```text
understanding / intent
context / referent
epistemic trust
personality
research / initiative
```

Target:

- strong average quality;
- zero catastrophic trust failures.

Current default benchmark model:

```text
qwen3.5:9b
```

A larger `qwen3.5:27b` A/B was much slower and did not solve structural state/knowledge problems by itself.

Architecture first; bigger model later if it adds real value.

---

# Phase 11.2 — Conversational Continuity & Referent Intelligence

**COMPLETE ENOUGH / STRUCTURAL**

Implemented:

- same-chat referent resolution before research;
- recommendation constraint continuity;
- clean topic switching;
- typed/bounded context;
- prior assistant prose not factual evidence;
- social claim ceiling.

## 11.2.3 — Knowledge-aware conversational opinions

Implemented:

- contextual public grounding for opinion turns;
- `public_source_verified_opinion`;
- subjective conclusion allowed when factual premises are sourced;
- privacy-aware public context detection;
- fail-closed opinion fallback.

Important provider compatibility boundary:

```python
grounded_opinion_subject = None
if core_is_grounded_opinion:
    grounded_opinion_subject = core_subject_hint
```

## 11.2.4 — Research query precision + benchmark trace

Implemented:

- wrapper removal;
- better public-research query extraction;
- trace across Core / Research / Grounding / Personality / AI / Conversation / Context.

---

# Phase 11.3 — Seriousness & Consequential Advice Gate

**COMPLETE**

Architecture:

```text
advice/help request
+
real-world consequence domain
+
incident/mistake/compromise signal
→ consequential_advice
→ public_source_verified_advice
```

Domains include:

- finance;
- account security;
- identity documents;
- legal/official matters.

Seriousness gate prevents inappropriate banter when consequences are real.

---

# Phase 11.4 — Opinion & Debate State

**STRUCTURALLY COMPLETE**

Structured debate state:

```text
active subject: A vs B
Oliver comparative stance: A > B
Mairon stance: left / right / unclear
```

Rules:

- assistant wording is dialogue/persona state, not factual evidence;
- Mairon must establish its own side or explicit uncertainty;
- generic dodges do not satisfy debate continuation;
- user-attributed comparisons must not be mistaken for Mairon's own view;
- later `"defend your take"` uses the stored stance;
- stance can be revised/withdrawn.

Major remaining limitation exposed by benchmarks:

> Mairon can preserve stance honesty but cannot debate/recommend substantively when it lacks actual topic knowledge.

This led directly to Phase 11.5.

---

# Phase 11.5 — Background Research & Persistent Topic Knowledge

**CURRENT MAJOR DEVELOPMENT TRACK**

This is now one of the most important Mairon capabilities.

Core vision:

```text
public/external topic
+
Mairon lacks enough knowledge
        ↓
offer substantial research when appropriate
        ↓
Oliver approves
        ↓
durable ResearchJob
        ↓
bounded background work
        ↓
iterative evidence collection
        ↓
quality threshold
        ↓
grounded synthesis
        ↓
persistent reusable knowledge
        ↓
future selective refresh
```

Explicit requests already grant permission:

```text
research smart watches while im asleep
research this in the background
look into this overnight
```

No duplicate confirmation should be required.

---

# Phase 11.5.1 — Research Opportunity + Permission

**COMPLETE**

Implemented:

- insufficient-knowledge research opportunity;
- ask permission for substantial public research;
- `"go for it"` approval;
- explicit research commands skip confirmation;
- conversation-scoped pending research permission;
- durable job DB;
- duplicate active-job deduplication;
- priority/depth/checkpoint/result/metadata/error fields;
- Windows-safe SQLite connection handling.

Database:

```text
data/private/research_jobs.sqlite3
```

Statuses:

```text
queued
running
paused
completed
cancelled
failed
```

---

# Phase 11.5.2 — Background Worker / Claim-Lease Lifecycle

**COMPLETE / LIVE MECHANICS PROVEN**

Implemented:

- atomic job acquisition;
- worker ID;
- lease ownership;
- lease expiry;
- attempt count;
- stale-running-job recovery;
- bounded initial public-evidence pass;
- evidence persistence;
- quick job completion;
- honest pause for deeper jobs;
- daemon worker;
- development telemetry.

Desired multi-worker future:

```text
always-on Core job store
        ↓
workers claim with lease
   ┌────────────┴────────────┐
   ▼                         ▼
Pi worker                 PC worker
```

A job must never run simultaneously on both workers.

---

# Phase 11.5.3 — Iterative Checkpointed Deep Research

**IMPLEMENTED / CURRENT LIVE RE-ACCEPTANCE PENDING**

Pipeline:

```text
initial evidence
→ checkpoint
→ planner identifies remaining gap
→ targeted query
→ search/read
→ source deduplication
→ checkpoint
→ yield
→ repeat
```

Important design:

- one bounded research operation at a time;
- many interruption points;
- persisted progress survives shutdown;
- no giant multi-hour blocking call;
- normal conversation remains independent.

Evidence collection eventually reaches:

```text
deep_evidence_collection_complete
→ next_stage = final_synthesis
→ user_ready = false
```

The raw notes are deliberately not called a finished answer.

---

# Phase 11.5.3.1 — Research Isolation, Query Grounding & Goal Fidelity

**IMPLEMENTED / REGRESSION GREEN / LIVE RERUN PENDING**

## Whole-turn foreground lease

Old timestamp-only preemption was insufficient.

Current intended model:

```text
begin_interactive_turn()
→ entire foreground workflow
→ finally end_interactive_turn()
→ idle grace begins
→ background worker may resume
```

Background research must never begin a new stage while foreground interaction is active.

## Query-grounding rule

Local planner may propose research dimensions but may not bootstrap unsupported specific identities.

Allowed:

```text
battery life
durability
official specs
independent reviews
```

Specific models/people/versions must already appear in:

- Oliver's request/topic; or
- retrieved evidence.

Unsupported planner queries are rejected.

If every planner query is rejected, Core falls back to conservative topic-based discovery.

## Goal-scope fidelity

Research categories include:

```text
catalogue_lookup
purchase_decision
pairwise_opinion
open_ended
```

Principle:

> Deep = careful, not infinitely broad.

Catalogue research stays catalogue-focused.

Purchase-decision research may investigate reviews, drawbacks, prices, reliability and alternatives.

## Legacy topic canonicalisation

Old durable topics containing execution wording can recover the clean research topic from the original request.

---

# Research Quality Philosophy

Oliver's priority for substantial research:

> Quality over timeliness.

A good answer after hours is preferable to quick slop.

Completion should eventually consider:

- goal fidelity;
- relevant user constraints;
- primary/official evidence where appropriate;
- source diversity;
- disagreement resolution;
- freshness;
- important drawbacks;
- recommendation justification;
- remaining uncertainty.

Source-count thresholds are useful floors, not sufficient definitions of quality.

Safety caps should pause for review rather than bluff completion.

---

# Phase 11.5.4 — Grounded Final Synthesis

**NEXT MAJOR IMPLEMENTATION AFTER CURRENT BUG + LIVE ACCEPTANCE**

Target:

```text
accumulated evidence
        ↓
grounded synthesis
        ↓
recommendations / conclusions when requested
        ↓
claim verification
        ↓
durable final report
        ↓
user_ready = true
```

Requirements:

- factual premises only from stored evidence;
- unsupported model-memory facts forbidden;
- provenance retained;
- explicit uncertainty where evidence remains incomplete;
- subjective conclusions allowed only when grounded in verified factual premises;
- synthesis is interruptible/checkpointable where practical;
- interactive Mairon still has priority.

---

# Phase 11.5.5 — Research Quality / Completion Criteria

**PLANNED**

Calibrate using real jobs.

Potential dimensions:

- question fully understood;
- necessary user constraints available;
- primary sources found;
- independent sources found;
- conflicting claims resolved;
- current facts refreshed;
- source authority appropriate;
- important failure modes/drawbacks covered when relevant;
- recommendation confidence justified;
- unresolved gaps recorded.

Depth presets may influence evidence targets:

```text
quick
normal
deep
```

They should not promise exact wall-clock times.

---

# Phase 11.5.6 — Reusable Persistent Topic Knowledge

**PLANNED / HIGH VALUE**

Separate verified facts from persona/opinion state:

```text
VERIFIED TOPIC KNOWLEDGE
- claim
- source/provenance
- confidence
- verified_at
- freshness class
- topic/entity links

MAIRON PERSONA STATE
- preference
- stance
- opinion
- reason grounded in verified knowledge
```

Goal:

- research once, reuse later;
- avoid disposable essays;
- build durable expertise around topics Oliver repeatedly cares about.

Examples:

- COTE;
- TBATE;
- Re:Zero;
- Shadow Slave;
- Garmin watches;
- running shoes;
- travel destinations;
- technology purchases.

---

# Phase 11.5.7 — Incremental Knowledge Refresh

**PLANNED**

Target:

```text
existing topic knowledge
→ classify stable vs stale
→ refresh only changed/current claims
→ retain still-valid stable knowledge
```

Examples:

Stable:

- fiction canon already established;
- historical explanations;
- technical concepts.

Freshness-sensitive:

- prices;
- current product lineups;
- availability;
- software versions;
- news;
- schedules;
- public-service information.

Do not restart from zero unnecessarily.

---

# Phase 11.5.8 — Completed-Job Delivery / Notifications

**PLANNED**

Features:

- job-status surface;
- completed research inbox;
- notify when useful;
- no notification spam;
- progress inspection;
- resume/review controls;
- later presence-aware callback.

Example future personality callback:

```text
Welcome home princess, I am ready to discuss your precious little Re:Zero theories.
```

The callback is persona; the completed research state must be real first.

---

# Future Research Scheduler — Pi + PC Cooperation

This is likely the strongest reason for eventually buying the Pi.

Oliver does not want to purchase the Pi until the feature proves its value on the desktop.

Estimated all-in Pi build discussed:

```text
approximately AUD 500–700
```

Reality constraints:

- PC may be off for entire days;
- some days PC is on only 4–5 hours;
- gaming must preempt background GPU/model work;
- Pi cannot merely wait for the desktop to exist.

Desired work split:

## Pi

- always-on job store;
- orchestration;
- networking;
- search/source collection;
- page parsing;
- indexing;
- lightweight inference where practical;
- alarms/routines/presence;
- job resumption.

## Windows RTX 5080

- optional heavy local synthesis;
- large-model reasoning;
- opportunistic acceleration;
- never a hard dependency for every research job.

Priority order:

```text
1. Oliver active interaction
2. time-sensitive tasks / alarms / notifications
3. background research
4. maintenance / index refresh
```

Future resource-aware scheduler:

- detect gaming/active GPU use;
- pause expensive research stages;
- resume when idle;
- use Pi while desktop unavailable;
- optionally dispatch heavy stage when PC appears;
- persist progress regardless of worker changes.

---

# Raspberry Pi Direction

## Current status

Pi/Desktop preparation completed:

```text
10.10.1 handshake
10.10.2 wake decision
10.10.3 presence + wake configuration
```

Hardware work is paused.

## Purchase rule

Do not buy the Pi simply because it is the next architectural step.

The Pi should buy:

- 24/7 research continuation;
- always-on alarms/routines;
- wake word;
- persistent coordination;
- remote access;
- presence-aware behaviour.

The desktop version should prove those capabilities are valuable first.

## Voice cloning

Explicitly parked until/after the Pi stage.

---

# Future — Wake Word / Always-On Voice

Desktop GUI voice already proves:

```text
microphone
→ local STT
→ Core
→ response
→ local TTS
```

Future Pi milestone:

```text
"Mairon"
→ wake detector
→ local STT
→ Core
→ response
→ local TTS
→ follow-up window
```

Planned:

- local wake detection;
- activation chime;
- follow-up window;
- silence timeout;
- stop/thanks/never-mind handling;
- avoid TTS self-triggering;
- eventual interruption/barge-in.

---

# Future — Secure Remote File Retrieval

Target:

```text
Oliver away:
"Mairon, send me my resume from the PC."
```

Flow:

```text
Phone
 ↓
Pi/Core
 ↓
resolve approved file request
 ↓
desktop offline?
 ↓
ask permission to wake if needed
 ↓
Wake-on-LAN
 ↓
authenticated Desktop Agent
 ↓
approved file candidate
 ↓
Core validates
 ↓
secure transfer
 ↓
phone receives file
```

No raw Windows file share exposed to the public internet.

---

# Future — Generic Permission Framework

Eventually unify capability-specific approvals:

- low risk → auto-approved;
- medium risk → confirmation;
- destructive/high consequence → strong confirmation;
- audit log;
- standing permissions;
- expiry;
- revocation;
- remote approval UI.

Desktop power authority should eventually use this framework.

---

# Future — Proactive Mairon

Move from:

```text
User asks
→ Mairon answers
```

toward:

```text
relevant event/research completion occurs
→ Core decides whether interruption is worthwhile
→ notify only when useful
```

Potential:

- reminders;
- calendar preparation;
- important-email follow-up;
- weather warnings;
- deliveries;
- university deadlines;
- project reminders;
- completed research.

Principle:

> Mairon must not become a notification spam machine.

---

# Future — Phone / Remote Mairon

Planned:

- secure phone/web client;
- authentication;
- encrypted Pi connection;
- text;
- voice;
- push notifications;
- remote approvals;
- Calendar/Gmail;
- WOL;
- file retrieval;
- travel mode;
- background-research status.

---

# Future — Smart Home / Devices

Only after Core/voice/Pi reliability:

- lights;
- scenes;
- bedroom controls;
- safe device allowlists;
- device state before actions;
- consequence-aware confirmations.

---

# Future — Personal Context Features

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

Personal context must not silently leak into public research beyond the allowed task.

---

# Engineering Quality — Ongoing

## Regression discipline

A failed old test can mean:

```text
production bug
or
stale fixture
```

Do not roll back correct production architecture merely to satisfy a fossil test.

Recent example:

- Phase 11.5.2/11.5.3 tests still expected literal `note_interactive_activity()`;
- Phase 11.5.3.1 intentionally replaced it with `begin_interactive_turn()` / `end_interactive_turn()`;
- tests were updated to validate the new contract.

## Test layers

Use all three:

```text
unit/regression
+
targeted integration
+
real live acceptance
```

For major user-facing capabilities, 153/153 alone is not enough.

Background research specifically requires real acceptance because threads, tool registries, SQLite, Ollama and live timing can interact in ways fakes do not reproduce.

## Debug surface

Prefer VS Code + terminal for active development.

Useful traces:

```text
[Core]
[AI]
[Grounding]
[Context]
[Tool]
[Research]
[Desktop Agent]
[Timing]
```

Windows app remains the final user-facing acceptance surface.

## File lineage

Before replacing production code:

- inspect exact current file;
- do not regenerate from stale memory;
- preserve intentional compatibility boundaries;
- restart Python processes after replacement;
- prefer full-file replacement when Oliver requests code files.

## Git discipline

Before milestone commit:

```powershell
git status --short
```

Do not stage:

```text
.env
.venv
data/
OAuth/token files
editor-local state
```

One known fact:

- Oliver confirmed a commit immediately before Phase 11.5.2 began.

Do not assume later 11.5.2 / 11.5.3 / 11.5.3.1 changes are committed until `git status` confirms it.

---

# Current Important File Lineage

Immediate research/provider files:

```text
src/ai/ollama_provider.py
    local provider, foreground interaction lease integration,
    research permission/queue integration
    CURRENT PYLANCE BLOCKER: _normalise_space undefined

src/core/conversational_research.py
    contextual research detection/query normalisation
    explicit background-research request parsing

src/research/research_jobs.py
    durable SQLite job store
    statuses/checkpoints/results
    lease ownership/expiry
    attempt count
    crash recovery

src/research/research_worker.py
    daemon background execution
    foreground-preemption boundary
    bounded stages
    canonical topic recovery
    iterative research execution

src/research/deep_research.py
    deep-research planner
    gap identification
    quality snapshot
    planner-query grounding
    goal-scope classification
    safety cap

src/research/public_factual_research.py
    bounded public search/read evidence collection

src/research/public_factual_grounding.py
    structured source-backed verification
```

Important tests:

```text
tests/test_core_phase11_5_1_research_permission.py
tests/test_core_phase11_5_2_background_worker.py
tests/test_core_phase11_5_3_iterative_deep_research.py
tests/test_core_phase11_5_3_1_research_isolation.py
```

---

# Current Development Order

Do these in order unless a newly discovered regression changes priority:

1. **Fix `ollama_provider.py` `_normalise_space` undefined references.**
2. Run targeted research/provider tests.
3. Run full suite and retain **153/153 or higher**.
4. Rerun live background-research acceptance.
5. Recheck blank day-overview response.
6. Confirm whole-turn foreground preemption works live.
7. Confirm goal-scoped/grounded research queries work live.
8. Confirm current-date/freshness behaviour is sensible.
9. Commit the stable Phase 11.5.3.1 milestone.
10. Build **11.5.4 Grounded Final Synthesis**.
11. Build research quality/completion calibration.
12. Build reusable sourced topic knowledge.
13. Build incremental knowledge refresh.
14. Build completed-job delivery/notifications.
15. Revisit 9B vs 27B debate A/B once research-backed debate has real substance.
16. Continue Pi scheduler/always-on work only after desktop research proves value.
17. Voice cloning remains later.

---

# Next-Chat Handoff Instructions

When continuing in a fresh project chat:

1. Upload the current **Project Mairon — Next-Chat Engineering Handover**.
2. Upload this roadmap.
3. State that **153/153 automated tests passed**, but latest live rerun is pending.
4. Upload the latest exact source files being modified.
5. Start with `src/ai/ollama_provider.py`.
6. Do not let the new chat reconstruct provider/research files from older snapshots.
7. Use individual files for focused phases.
8. Use a larger repo snapshot only if lineage becomes uncertain or broad architecture inspection is required.

---

# Current Milestone

The project is now beyond merely:

```text
desktop chatbot + tools
```

The active milestone is:

```text
Reliable Core
+
safe Windows actions
+
standalone desktop UI
+
persistent conversation
+
factual grounding
+
structured opinion/debate state
+
durable asynchronous background research
+
future reusable verified topic knowledge
```

The immediate blocker is **not Raspberry Pi hardware**.

The immediate blocker is:

```text
provider correctness
+
live foreground/background isolation
+
final research synthesis
```

Once that is stable, Mairon will have the foundations for genuinely useful always-on Pi behaviour rather than simply moving an unfinished desktop assistant onto new hardware.
