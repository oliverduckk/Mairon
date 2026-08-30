# Mairon Development Roadmap

_Last updated: 30 August 2026_

This document is the permanent high-level roadmap for Mairon.

It serves four purposes:

1. Track what is already working.
2. Show the current development stage.
3. Keep future work organised without losing good ideas.
4. Prevent feature creep from derailing the next concrete milestone.

---

## Project Vision

Mairon is a private-first personal AI assistant that can understand context, remember useful information, interact with approved services and devices, and eventually operate as an always-available voice assistant around the home and remotely through a phone.

The long-term architecture is:

```text
                         ┌──────────────────────┐
                         │      Phone App       │
                         │  Secure remote UI    │
                         └──────────┬───────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────┐
│                    Raspberry Pi 5                       │
│                                                         │
│  Wake word • STT • TTS • Core orchestration • Memory   │
│  Permissions • Routines • Tools • Device control       │
│                                                         │
└───────────────────────┬─────────────────────────────────┘
                        │
            ┌───────────┴───────────┐
            ▼                       ▼
┌──────────────────────┐   ┌─────────────────────────────┐
│    Desktop PC        │   │ External services / APIs    │
│                      │   │                             │
│ Heavy local AI       │   │ Gmail • Calendar • Weather │
│ Private compute      │   │ Web • Maps • future tools  │
│ Wake-on-LAN          │   │                             │
└──────────────────────┘   └─────────────────────────────┘
```

### Core philosophy

- Local-first whenever practical.
- Private data stays local unless explicitly approved otherwise.
- Cloud AI is optional and permission-controlled.
- The AI model never receives unrestricted shell or system authority.
- Mairon's identity, memory, personality and permissions are separate from whichever model is currently answering.
- Core code owns authoritative state such as dates, alarms, routines and permissions.
- Models may request authority; they do not grant themselves authority.
- Deterministic workflows should own consequential or easily-confused tasks.
- Personality should sit on top of facts, not invent them.
- Useful automation beats novelty.

---

# Phase 1 — Foundation

**Status: COMPLETE**

- [x] Python project created.
- [x] Virtual environment established.
- [x] Git repository and GitHub remote configured.
- [x] `.gitignore` protects `.env`, runtime databases and local OAuth/private files.
- [x] Local runtime data stored separately from source code.
- [x] `.env` configuration system.
- [x] Configured local timezone: `Australia/Sydney`.
- [x] Mairon owner/user identity configured locally.
- [x] Local AI provider architecture.
- [x] Ollama integration.
- [x] Qwen3 14B configured as the default local model.
- [x] OpenAI provider integration.
- [x] GPT-5.6 Luna configured as optional cloud escalation.
- [x] Separate local and cloud conversation state.
- [x] Cloud escalation requires explicit approval.
- [x] Cloud tools restricted to public/non-private capabilities.
- [x] Runtime date/time context supplied to the model.
- [x] Core-side relative-date correction prevents stale model dates.
- [x] Initial architecture documentation created.

### Git checkpoint

- [x] Initial repository setup pushed.
- [x] Google Calendar milestone pushed.
- [x] Routine/alarm/morning/routing milestone pushed.

---

# Phase 2 — Personality, Memory and Safety Boundaries

**Status: CORE COMPLETE / CONTINUOUS POLISH**

### Personality

- [x] Mairon identity prompt.
- [x] Familiar companion tone.
- [x] Dry humour and contextual teasing.
- [x] Avoid excessively cheerful or servile assistant language.
- [x] Avoid generic endings such as “How can I assist?”
- [x] Safety and accuracy override humour.
- [x] Explicit rule against pretending to observe the user's physical state.
- [x] Grounded morning-response validator.
- [x] Deterministic fallback when morning wording violates grounding rules.

### Persistent memory

- [x] SQLite-backed local memory.
- [x] Save memory.
- [x] Search memory.
- [x] List memories.
- [x] Delete memory.
- [x] Persistent memory remains local-only.
- [x] Explicit-save philosophy rather than silently storing everything.

### Temporary / recent context

- [x] Recent-context storage separate from permanent memory.
- [x] Expiring recent context.
- [x] Bedtime context stored temporarily.
- [x] Recent context can support near-term routine decisions.

### Safety / authority boundaries

- [x] No arbitrary shell execution available to AI.
- [x] Application launching is allowlisted.
- [x] Cloud cannot access Gmail.
- [x] Cloud cannot access Calendar private data.
- [x] Cloud cannot access local memory.
- [x] Cloud cannot access routines or alarms.
- [x] Calendar writes require approval.
- [x] Read-only Gmail OAuth.
- [x] Core is authoritative for routine/alarm dates.
- [x] Core workflows prevent models wandering into unrelated tools.

### Future polish

- [ ] Broader factual-grounding validator for non-morning workflows.
- [ ] Personality regression tests.
- [ ] Better distinction between harmless banter and unsupported factual claims.
- [ ] Configurable personality intensity.
- [ ] Possible context-dependent personality modes without changing core identity.

---

# Phase 3 — Tools and External Information

**Status: STRONG V1 COMPLETE**

## System tools

- [x] System information.
- [x] Allowlisted application launching.
- [x] Refusal of arbitrary PowerShell/shell execution.

## Weather

- [x] Open-Meteo integration.
- [x] Configurable local weather location.
- [x] Weather usable by ordinary conversation.
- [x] Weather included in Morning Routine.

## Web

- [x] Tavily-backed web search.
- [x] Webpage reading.
- [x] Core can require source reading when appropriate.
- [x] Web tools available locally.
- [x] Public web tools available to cloud model.

### Ideas

- [ ] Source-quality ranking.
- [ ] Prefer official sources automatically for factual questions.
- [ ] News brief mode.
- [ ] Topic monitoring / change detection.
- [ ] Cache recent searches where useful.

---

# Phase 4 — Google Calendar

**Status: V1 COMPLETE**

- [x] Google OAuth configured.
- [x] Read Calendar events.
- [x] Retrieve upcoming/next event.
- [x] Calendar integrated into day overview.
- [x] Calendar integrated into Night Routine.
- [x] Calendar integrated into Morning Routine.
- [x] Calendar event creation backend exists.
- [x] Calendar creation is permission-gated.
- [x] Explicit approval required before writes.
- [x] Test event creation completed.

### Ideas

- [ ] Modify existing events with approval.
- [ ] Delete events with approval.
- [ ] Accept/decline invitations with approval.
- [ ] Detect travel-time conflicts.
- [ ] Warn about impossible back-to-back locations.
- [ ] Automatically suggest departure time when useful.
- [ ] Calendar-aware reminders.
- [ ] Contextual preparation prompts before major events.

---

# Phase 5 — Gmail

**Status: V1 COMPLETE**

- [x] Separate read-only Gmail OAuth.
- [x] Retrieve recent emails.
- [x] Search email.
- [x] Read specific email.
- [x] Exact search followed by looser/broader search.
- [x] Constrained inbox-attention workflow.
- [x] Maximum focused email-read budget.
- [x] Inbox triage classifies:
  - ACTION NEEDED
  - FYI
  - IGNORE
- [x] Marketing/promotional noise suppressed.
- [x] Security notifications worded cautiously.
- [x] Inbox attention integrated into Morning Routine.
- [x] Private Gmail content never exposed to cloud AI.

### Ideas

- [ ] Draft email replies.
- [ ] Permission-gated email sending.
- [ ] Follow-up detection: “They still haven't replied.”
- [ ] Detect bills/invoices requiring action.
- [ ] Detect shipping/delivery updates.
- [ ] Automatically connect related email threads.
- [ ] Daily or weekly inbox cleanup summaries.
- [ ] Surface emails related to today's Calendar events.
- [ ] Learn which senders/categories the user normally ignores, with confirmation.

---

# Phase 6 — Routes and Travel Time

**Status: V1 COMPLETE**

## General routing

- [x] Google Routes API.
- [x] Driving routes.
- [x] Live traffic-aware driving estimates.
- [x] Public transport routes.
- [x] Park-and-ride workflow.
- [x] Parking/walking buffer before transit.
- [x] Private address aliases stored in `.env`.

## Preferred work commute

- [x] Private `work` location alias.
- [x] Preferred backroad work route.
- [x] Route defined using private intermediate coordinates.
- [x] Work route reverses correctly for return trip.
- [x] Diagnostic mode for preferred route waypoints.
- [x] Fallback to Google optimal route when preferred route fails.

## Conversational routing

- [x] Core recognises direct work travel-time questions.
- [x] Route workflow cannot accidentally become a routine query.
- [x] Successful route stored as temporary conversational context.
- [x] “What if I go through SUBURB instead?”
- [x] “What about my normal route again?”
- [x] Arbitrary destination route extraction.
- [x] Grounded deterministic route wording.
- [x] Failed via routes do not invent nonexistent roads/incidents.
- [x] Commute intentionally excluded from automatic Morning Routine.

### Ideas

- [ ] Compare two explicitly requested routes side-by-side.
- [ ] “What's the fastest way right now?”
- [ ] Automatically warn only when the normal work route is unusually bad.
- [ ] Estimate required departure time for Calendar events.
- [ ] Multi-stop trip planning.
- [ ] Remember commonly used destinations as local aliases.
- [ ] Optional route-history statistics.
- [ ] Detect unusual traffic only when it would materially affect behaviour.

---

# Phase 7 — Routine Engine

**Status: V1 COMPLETE**

## Weekly routine

- [x] Monday work.
- [x] Tuesday work.
- [x] Wednesday university.
- [x] Thursday work.
- [x] Friday work.
- [x] Work hours stored.
- [x] Variable home/office work location.
- [x] Routine preferences stored separately from daily state.

## Daily context

- [x] Daily work-location override.
- [x] Office wake preference.
- [x] WFH wake preference.
- [x] Resolver identifies missing work-location information.
- [x] Routine questions can request clarification.
- [x] Today/tomorrow context helpers.

### Ideas

- [ ] Holidays / annual leave overrides.
- [ ] Sick-day mode.
- [ ] University semester awareness.
- [ ] Exam-period overrides.
- [ ] Temporary routine changes.
- [ ] Gym-day rotation state.
- [ ] Travel mode that suspends normal home routine.
- [ ] Learn recurring patterns only after explicit confirmation.
- [ ] Weekend routine preferences.
- [ ] “Tomorrow is unusual” one-shot context notes.

---

# Phase 8 — Alarm System

**Status: STATE MANAGEMENT COMPLETE / PHYSICAL ALARM PENDING**

- [x] SQLite alarm store.
- [x] One wake alarm per date.
- [x] Routine-created alarms.
- [x] Manual alarms.
- [x] Manual alarm overrides routine recommendation.
- [x] Disabled alarms remain disabled.
- [x] Routine changes do not resurrect disabled alarms.
- [x] Retrieve alarm for a date.
- [x] List upcoming alarms.
- [x] Disable alarm.
- [x] Delete alarm.
- [x] Routine alarm synchronisation.
- [x] Manual override label bug fixed.
- [x] Relative date authority moved to Core.

## Still required

- [ ] Actual alarm scheduler/runner.
- [ ] Audible playback.
- [ ] Pi speaker integration.
- [ ] Snooze.
- [ ] Stop/dismiss.
- [ ] Alarm volume rules.
- [ ] Fail-safe behaviour if AI model is unavailable.
- [ ] Optional gradual wake behaviour.
- [ ] Alarm-triggered Morning Routine.
- [ ] Phone fallback notification if desired.

---

# Phase 9 — Day Overview

**Status: COMPLETE V1**

- [x] Detect “What am I doing today?”
- [x] Detect “What am I doing tomorrow?”
- [x] Core resolves actual local date.
- [x] Combines routine context.
- [x] Combines Calendar.
- [x] Combines actual alarm state.
- [x] Uses isolated final-generation context.
- [x] Prevents stale dates contaminating response.
- [x] Distinguishes recommended wake time from actual stored alarm.

### Ideas

- [ ] Add weather when relevant.
- [ ] Add preparation reminders.
- [ ] Add travel/departure information only when materially useful.
- [ ] Add important emails related to day's events.
- [ ] “What's the busiest part of my day?”
- [ ] “When am I actually free?”

---

# Phase 10 — Night Routine

**Status: V1 COMPLETE**

- [x] Detect explicit bedtime intent.
- [x] Resolve tomorrow.
- [x] Ask office/home when required.
- [x] Multi-turn pending routine state.
- [x] Sync routine wake alarm.
- [x] Preserve manual alarm.
- [x] Preserve disabled alarm.
- [x] Read tomorrow's Calendar.
- [x] Record bedtime as recent local context.
- [x] Expire bedtime context after a reasonable window.
- [x] Do not claim devices were controlled when they were not.
- [x] Do not promise physical alarm playback yet.

### Ideas

- [ ] Turn off bedroom lights.
- [ ] Check whether PC should be shut down.
- [ ] Detect active downloads/jobs before PC shutdown.
- [ ] Set phone/Pi quiet mode.
- [ ] Summarise tomorrow only when useful.
- [ ] Charge reminders for watch/headphones when battery data becomes available.
- [ ] Confirm doors/garage only if actual sensors exist.
- [ ] Trigger overnight maintenance jobs.

---

# Phase 11 — Morning Routine

**Status: V1 COMPLETE**

Current automatic Morning Routine contains:

- [x] Today's routine / daily context.
- [x] Actual stored wake alarm.
- [x] Matching bedtime record.
- [x] Sleep-opportunity calculation.
- [x] Google Calendar.
- [x] Weather.
- [x] Constrained Gmail attention brief.
- [x] Grounded response validation.
- [x] Commute deliberately omitted from automatic brief.

### Important distinction

`sleep_opportunity` is **not measured sleep**.

It currently means:

```text
recorded bedtime → scheduled alarm
```

It does not mean Mairon knows when the user actually fell asleep or woke.

### Ideas

- [ ] Automatically launch after alarm dismissal.
- [ ] Garmin actual sleep duration.
- [ ] Garmin sleep score.
- [ ] Overnight HRV.
- [ ] Resting heart rate.
- [ ] Body Battery / recovery information.
- [ ] Compare sleep opportunity vs measured sleep.
- [ ] Tailor workout suggestion to recovery.
- [ ] Morning music.
- [ ] Read brief aloud.
- [ ] Different brief verbosity for workdays, uni days and free days.
- [ ] Skip irrelevant categories automatically.
- [ ] “Anything unusual?” summary.

---

# Phase 12 — Voice MVP

**Status: CURRENT DEVELOPMENT PHASE**

## Goal

Prove this complete loop on the desktop:

```text
Microphone
    ↓
Local speech-to-text
    ↓
Existing Mairon Core
    ↓
Response text
    ↓
Local text-to-speech
    ↓
Speakers/headphones
```

## Development order

- [ ] Microphone capture.
- [ ] Local speech-to-text.
- [ ] Transcript displayed for debugging.
- [ ] Transcript passed into existing `route_message()` / Mairon Core.
- [ ] Local text-to-speech engine.
- [ ] Speak Mairon's response aloud.
- [ ] Test multi-turn voice conversation.
- [ ] Measure latency.
- [ ] Handle silence / failed transcription cleanly.

## Wake word

Only after the basic speech loop works:

- [ ] Local wake-word detector.
- [ ] Wake word is **“Mairon”**.
- [ ] Household conversation is ignored until wake word is detected.
- [ ] Wake-word detector runs locally.
- [ ] No continuous cloud audio.
- [ ] Optional activation chime.
- [ ] Begin STT only after activation.

## Follow-up mode

Target behaviour:

```text
Oliver: “Mairon.”
Mairon: [activation chime]

Oliver: “What am I doing today?”
Mairon: [answers]

Oliver: “And what about tomorrow?”
Mairon: [answers without requiring another wake word]

~10–20 seconds inactivity

Mairon returns to wake-word-only mode.
```

- [ ] Follow-up listening window.
- [ ] Reset timer after each valid exchange.
- [ ] End follow-up mode after inactivity.
- [ ] Explicit “thanks / stop / never mind” termination.
- [ ] Avoid triggering on Mairon's own TTS audio.

## Advanced voice behaviour

- [ ] Voice activity detection.
- [ ] End-of-speech detection.
- [ ] Barge-in / interrupt Mairon while speaking.
- [ ] Cancel TTS when user interrupts.
- [ ] Streamed TTS for faster perceived response.
- [ ] Earcons/chimes for states rather than unnecessary spoken confirmations.
- [ ] Volume adaptation.
- [ ] Multiple microphones / room positioning later if useful.

---

# Phase 13 — Raspberry Pi Core

**Status: PLANNED**

The Pi becomes Mairon's permanent always-on host.

- [ ] Raspberry Pi 5 setup.
- [ ] Linux service for Mairon.
- [ ] Start automatically at boot.
- [ ] Automatic crash recovery.
- [ ] Wake-word detector on Pi.
- [ ] Microphone hardware.
- [ ] Speaker hardware.
- [ ] STT on Pi where practical.
- [ ] TTS on Pi.
- [ ] Core orchestration moved to Pi.
- [ ] Local SQLite state moved safely.
- [ ] OAuth credentials moved safely.
- [ ] Environment configuration moved safely.
- [ ] Logging.
- [ ] Health/status endpoint.
- [ ] Graceful updates.

### Reliability ideas

- [ ] Watchdog service.
- [ ] Automatic database backups.
- [ ] Configuration backup.
- [ ] Safe rollback after failed update.
- [ ] “Mairon status” command.
- [ ] Offline degraded mode when internet is unavailable.

---

# Phase 14 — Desktop Compute Node

**Status: PLANNED**

The desktop becomes optional heavy compute rather than the permanent brain.

- [ ] Secure Pi → desktop communication.
- [ ] Wake-on-LAN.
- [ ] Detect whether desktop is already being used.
- [ ] Track whether Mairon woke the PC.
- [ ] Run heavy local model tasks remotely.
- [ ] Return result to Pi.
- [ ] Shut desktop down only when:
  - Mairon originally woke it.
  - no user session requires it.
  - no important jobs/downloads are running.
- [ ] Never blindly shut down an actively used PC.

### Ideas

- [ ] GPU image understanding.
- [ ] Larger local LLM.
- [ ] Local document indexing.
- [ ] Local transcription of long recordings.
- [ ] Background photo/video processing.
- [ ] Local coding/research jobs.

---

# Phase 15 — Smart Home / Device Control

**Status: PLANNED**

- [ ] Discover current smart-home ecosystem.
- [ ] Light control.
- [ ] Bedroom-specific controls.
- [ ] Scene support.
- [ ] Safe device allowlist.
- [ ] PS5 integration where technically possible.
- [ ] PC controls through controlled Core actions.
- [ ] Device-state reading before actions.
- [ ] Confirmation levels based on consequence.

### Example future Night Routine

```text
“Mairon, I'm going to bed.”

→ resolve tomorrow
→ confirm office/WFH if needed
→ synchronise alarm
→ check tomorrow's Calendar
→ record bedtime context
→ turn bedroom lights off
→ optionally shut down PC safely
→ enter quiet mode
```

### Example future Morning Routine

```text
Alarm fires
→ dismiss
→ lights gradually turn on
→ Mairon reads morning brief
→ weather
→ Calendar
→ important inbox
→ recovery/sleep metrics
```

---

# Phase 16 — General Permission / Action Framework

**Status: PARTIAL / PLANNED**

Current permission handling is capability-specific. Eventually this should become a reusable system.

- [x] Cloud escalation approval.
- [x] Calendar-create approval.
- [ ] Generic action request object.
- [ ] Consequence/risk classes.
- [ ] Auto-approved low-risk actions.
- [ ] Confirmation-required medium-risk actions.
- [ ] Strong confirmation for destructive actions.
- [ ] Reusable confirmation UI/voice dialogue.
- [ ] Action audit log.
- [ ] Ability to revoke previously granted standing permissions.
- [ ] Expiring permissions.

### Possible policy

#### Low risk / pre-approved

- Read weather.
- Read Calendar.
- Read Gmail.
- Read routines.
- Set routine-generated wake alarm.
- Update ordinary daily routine state.

#### Explicit confirmation

- Send email.
- Delete email.
- Create unusual Calendar event.
- Delete Calendar event.
- Shut down a computer not clearly owned by Mairon.
- Purchase anything.
- Modify important files.
- Unlock/open physical access controls.

---

# Phase 17 — Proactive Mairon

**Status: FUTURE**

Move from:

```text
User asks → Mairon answers
```

toward:

```text
Relevant event occurs → Core determines whether interruption is worthwhile
```

- [ ] Scheduled task engine.
- [ ] Conditional watches.
- [ ] Reminder engine.
- [ ] “Only bother me if it matters” logic.
- [ ] Calendar event preparation.
- [ ] Important email follow-up.
- [ ] Weather warnings.
- [ ] Travel disruption warnings.
- [ ] Alarm/routine anomalies.
- [ ] Device alerts.
- [ ] Package delivery notifications.
- [ ] University deadline reminders.
- [ ] GitHub/project reminders.

### Principle

Mairon should **not** become a notification spam machine.

The bar for proactive interruption should be:

> Is this information timely, useful, and likely to change what Oliver does?

---

# Phase 18 — Phone / Remote Mairon

**Status: FUTURE**

Goal: securely interact with the same Mairon instance while away from home.

- [ ] Phone application or secure web app.
- [ ] Authentication.
- [ ] Encrypted connection to Pi.
- [ ] No raw Windows exposure to the internet.
- [ ] Text chat.
- [ ] Voice input.
- [ ] Voice responses.
- [ ] Push notifications.
- [ ] Remote device/routine status.
- [ ] Secure approval prompts.
- [ ] Remote Calendar/Gmail queries.
- [ ] Remote wake-on-LAN where appropriate.

### Ideas

- [ ] Car mode.
- [ ] Travel mode.
- [ ] Location-aware features with explicit permission.
- [ ] Quick-action widgets.
- [ ] Apple Watch / Garmin notification bridge if practical.

---

# Phase 19 — Health / Garmin Integration

**Status: IDEA / RESEARCH REQUIRED**

Potentially valuable Morning Routine data:

- [ ] Actual sleep duration.
- [ ] Sleep score.
- [ ] Sleep stages if accessible.
- [ ] Overnight HRV.
- [ ] Resting heart rate.
- [ ] Body Battery.
- [ ] Training readiness / recovery metrics if accessible.
- [ ] Step count.
- [ ] Workout history.

Potential uses:

- Compare sleep opportunity to measured sleep.
- Change morning commentary based on actual recovery.
- Suggest easier/harder training days.
- Detect obvious poor-recovery mornings.
- Avoid pretending Mairon knows sleep quality when it does not.

### Research required

- [ ] Verify Garmin Health API personal-access options.
- [ ] Verify exact metrics available.
- [ ] Decide whether official API access is realistic for a personal project.
- [ ] Investigate safe alternatives only if necessary.

---

# Phase 20 — Personal Context and Lifestyle Features

**Status: IDEAS**

These are deliberately parked here so they do not derail the core build.

## Fitness

- [ ] Store workout split.
- [ ] Track current rotation/day.
- [ ] Ask “What am I training today?”
- [ ] Record completed sessions.
- [ ] Exercise substitutions.
- [ ] Personal-record tracking.
- [ ] Recovery-aware workout suggestion.
- [ ] Garmin integration.

## University

- [ ] University timetable integration.
- [ ] Assignment/deadline tracker.
- [ ] Exam timetable.
- [ ] Study-session planning.
- [ ] Reminder before assessments.
- [ ] Surface relevant assignment files.
- [ ] “What do I need to do for uni this week?”

## Work

- [ ] Office/WFH context.
- [ ] Workday reminders.
- [ ] Optional work commute query.
- [ ] Meeting preparation.
- [ ] Keep work/private data boundaries explicit.

## Travel

- [ ] Trip itinerary storage.
- [ ] Flight/train details.
- [ ] Packing lists.
- [ ] Weather before travel.
- [ ] Day-plan generation.
- [ ] Travel mode suspends home routine.
- [ ] Time-zone-aware routine changes.

## Reading / Entertainment

- [ ] Reading list.
- [ ] Current book/chapter tracking.
- [ ] Spoiler-safe discussion state.
- [ ] Watchlist.
- [ ] Recommendation history.

## Household

- [ ] Shopping-list support.
- [ ] Chores/reminders.
- [ ] Family-shared information only where explicitly permitted.
- [ ] Pet-related routine reminders if useful.

---

# Phase 21 — Engineering Quality

**Status: ONGOING**

## Testing

- [x] Standalone module testing during development.
- [x] Syntax checks before replacements.
- [ ] Unit tests for routine resolver.
- [ ] Unit tests for alarm priority.
- [ ] Unit tests for relative-date resolution.
- [ ] Unit tests for route follow-up parsing.
- [ ] Unit tests for permission boundaries.
- [ ] Regression tests for known failures.
- [ ] Simulated conversation tests.

### Known regression cases worth preserving

- [ ] “Tomorrow” must never become a stale 2023 date.
- [ ] “How long to work?” must not call routine context.
- [ ] Manual wake alarm must survive routine changes.
- [ ] Disabled alarm must not be resurrected.
- [ ] Morning brief must not invent physical state.
- [ ] Morning brief must not call commute automatically.
- [ ] Cloud must not access Gmail/Calendar/private memory.
- [ ] Route responses must not invent landmarks/incidents.
- [ ] Night Routine pending office/home question must resolve correctly.

## Database / migrations

- [ ] Formal schema migration system.
- [ ] Backup/restore utility.
- [ ] Database health check.
- [ ] Corrupt-database recovery plan.

## Logging

- [ ] Structured logs.
- [ ] Log levels.
- [ ] Privacy-safe logging.
- [ ] Tool latency metrics.
- [ ] Voice latency metrics.
- [ ] Error summaries.

## Configuration

- [ ] Validate required `.env` values at startup.
- [ ] Friendly missing-config diagnostics.
- [ ] Example `.env.example` with no secrets.
- [ ] Versioned configuration documentation.

---

# Phase 22 — Security Hardening

**Status: ONGOING / IMPORTANT BEFORE REMOTE ACCESS**

- [x] Secrets excluded from Git.
- [x] Private runtime database excluded from Git.
- [x] OAuth files excluded from Git.
- [x] No arbitrary shell tool.
- [x] Private tools excluded from cloud model.
- [ ] Principle-of-least-privilege review for every integration.
- [ ] Encrypt sensitive stored credentials where appropriate.
- [ ] Secure Pi ↔ desktop authentication.
- [ ] Secure phone ↔ Pi authentication.
- [ ] Request signing / replay protection where relevant.
- [ ] Rate limiting.
- [ ] Audit log for consequential actions.
- [ ] Threat model before internet-facing remote access.
- [ ] Network isolation where useful.
- [ ] Dependency vulnerability checks.
- [ ] Regular credential rotation plan.
- [ ] Recovery process if Pi or phone is lost.

---

# Ideas Parking Lot

Good ideas go here when they are **not important enough to interrupt the current milestone**.

## Conversation

- [ ] Mairon recognises when a question refers to the immediately previous tool result.
- [ ] Better conversational corrections: “No, I meant tomorrow.”
- [ ] Better pronoun/reference tracking.
- [ ] Adjustable response verbosity.
- [ ] Context-aware banter without factual invention.
- [ ] Conversation summaries for long sessions.

## Voice

- [ ] Different chimes for listening / success / error.
- [ ] Whispered/quiet responses late at night.
- [ ] Automatically lower speech volume during household quiet hours.
- [ ] Multiple voice choices.
- [ ] Emotional/prosodic TTS without becoming theatrical.
- [ ] Recognise user speaking from farther away.
- [ ] Optional room microphones.
- [ ] Speaker identification only if genuinely useful and privacy-safe.

## AI / models

- [ ] Automatic local-model selection by task.
- [ ] Small fast local model for classification.
- [ ] Larger desktop model for difficult private tasks.
- [ ] Cloud recommendation only when expected benefit is meaningful.
- [ ] Evaluate future local models as hardware/software improves.
- [ ] Local vision model.
- [ ] Local embeddings / semantic search.

## Memory

- [ ] Categories/types for memories.
- [ ] Confidence / provenance metadata.
- [ ] Memory expiry for information that goes stale.
- [ ] Detect conflicting memories.
- [ ] Ask before updating an important stored preference.
- [ ] “What do you remember about X?”
- [ ] Export/import memory.
- [ ] Memory backup.

## Visual interface

- [ ] Small local dashboard.
- [ ] Current Mairon status.
- [ ] Active alarm.
- [ ] Today's routine.
- [ ] Recent actions.
- [ ] Pi/desktop state.
- [ ] Connected services.
- [ ] Permission management.
- [ ] Logs and diagnostics.
- [ ] Optional animated avatar only if it adds value rather than becoming a side quest.

## Miscellaneous fun ideas

- [ ] “Where did I leave off?” state for books/shows/projects.
- [ ] PC game/session awareness where privacy-safe.
- [ ] Music playback control.
- [ ] Sports score brief.
- [ ] Package tracker.
- [ ] Household weather station integration.
- [ ] Power/internet outage awareness.
- [ ] Network diagnostics.
- [ ] Home-server monitoring.
- [ ] Personal knowledge-base search.
- [ ] Camera/photo organisation tools.
- [ ] Travel photo backup workflow.
- [ ] Local file/document assistant.

---

# Explicitly Not Doing Yet

These are intentionally postponed.

- [ ] Building the phone app before Pi architecture exists.
- [ ] Exposing Mairon directly to the public internet.
- [ ] Arbitrary shell access.
- [ ] Giving the model autonomous destructive permissions.
- [ ] Building smart-home automation before voice/Core reliability.
- [ ] Over-optimising personality prompts instead of functionality.
- [ ] Adding commute to Morning Routine when it does not change behaviour.
- [ ] Assuming Garmin integration works before API access is verified.
- [ ] Rebuilding already-working tools simply for aesthetics.

---

# Current Milestone

## Voice MVP — Desktop

**The next objective is not “build the final voice assistant.”**

It is only this:

```text
Speak
  ↓
Accurate local transcript
  ↓
Existing Mairon Core answers
  ↓
Mairon speaks the answer locally
```

### Definition of done

- [ ] User can press/start listening.
- [ ] Speak a normal Mairon request.
- [ ] Local STT produces an accurate transcript.
- [ ] Existing Mairon Core processes it without special-case duplication.
- [ ] Response text is produced normally.
- [ ] Local TTS reads that response aloud.
- [ ] Entire loop is reliable enough to repeat several times.
- [ ] Latency is measured.
- [ ] Errors fail cleanly.

Only then:

```text
Add “Mairon” wake word
        ↓
Add follow-up listening window
        ↓
Add interruption/barge-in
        ↓
Move voice stack to Pi
```

---

# Development Discipline

## Before a major change

- [ ] Confirm current known-good behaviour.
- [ ] Work from the actual latest file rather than reconstructing an old version.
- [ ] Keep private values in `.env`.
- [ ] Avoid changing unrelated working systems.

## After a milestone

- [ ] Run standalone tests where available.
- [ ] Run Mairon end-to-end.
- [ ] Test important regression cases.
- [ ] Check `git status`.
- [ ] Confirm `.env`, `data/` and OAuth secrets are not staged.
- [ ] Commit with a meaningful message.
- [ ] Push to GitHub.
- [ ] Update this roadmap.

---

# Suggested Version Milestones

These are informal project milestones rather than strict semantic versions.

### Mairon v0.1 — Brain

- Local/cloud AI architecture.
- Privacy boundary.
- Memory.
- Web/weather.
- Gmail.
- Calendar.
- Routine.
- Alarms.
- Morning/Night workflows.
- Routing.

**Status: essentially complete.**

### Mairon v0.2 — Voice

- Local STT.
- Local TTS.
- Wake word.
- Follow-up mode.
- Audible alarm.

### Mairon v0.3 — Physical Mairon

- Raspberry Pi always-on Core.
- Speakers/microphone.
- Desktop compute node.
- Safe Wake-on-LAN.

### Mairon v0.4 — Home Assistant

- Lights/devices.
- Proactive routine execution.
- General permission framework.

### Mairon v0.5 — Everywhere

- Secure phone access.
- Remote notifications.
- Travel/mobile context.

### Mairon v1.0

A reliable, private-first, always-available personal assistant that:

- knows the user's current routine and relevant context;
- can converse naturally by voice;
- can safely use private tools;
- can act through explicit permissions;
- can operate when the desktop is off;
- can access heavy local compute when required;
- works both at home and remotely;
- remains useful without becoming intrusive.

---

# Next Action

**Begin Phase 12: Voice MVP on the desktop.**

First implementation target:

> Microphone capture + local speech-to-text.

