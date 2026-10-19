# Project Mairon — Development Roadmap

**Last updated:** 19 October 2026  
**Document role:** Current project-state overview, development sequence, and handoff index.  
**Companion:** `MAIRON_Detailed_Vision_and_Requirements_2026-10-18.md` (product intent and future requirements).  
**Other authoritative inputs:** exact current repository, `personality.md` from that repository, test output, current technical handoff, and user-approved decisions.

> **Authority distinction:** This roadmap records *verified project progress* separately from *historical descriptions*, *future decisions*, and *unverified proposals*. The attached 18 October strategic vision establishes what Mairon should become, **not** what has already been built. Do not use this document to reconstruct or overwrite unknown production files.

---

## 1. Current status — authoritative for this chat

| Item | Status on 19 October 2026 | Basis / caveat |
|---|---|---|
| Active development | **Phase 11.6.6j.1 CLOSED as bounded engineering baseline** | Explicit user acceptance following independent human review; not the final product graduation |
| Real-repository regression | **302 passed / 0 failed / 302 discovered** | Oliver ran `python tests/run_all.py` after the final seven-file closure package installation |
| Final Oliver-style holdout | **56/56 automatic PASS, 0 automatic critical failures** | `oliver_style_20261019_120323.md`; passing assertions do not imply perfect human semantics |
| Final conversational holdout | **51/51 automatic PASS; 18 scenarios, 28 turns; 7.82 s mean** | `conversational_intelligence_20261019-120327_full.md` |
| Manual / live review | **Bounded acceptance approved with documented limitations** | Camera-battery physical-agency smoke test passed; full response-level review noted remaining trust/quality uncertainty and functional gaps |
| Closure production changes | `src/core/claim_grounding.py`; `src/core/acceptance_public.py` | Physical-contact/prior-event guard; source-attribution false-positive correction including qualified-document regression |
| Closure package | **7 installed files**; 3 new regression scripts, 93 new test methods | Exact final manifest: `MANIFEST(6).json` (package handoff; local repo artifact name may be `MANIFEST.json`) |
| Phase 11 Git milestone | **NOT YET COMMITTED (as of documentation preparation)** | Inspect real `git status`, stage only reviewed work, verify Git identity/remote, then commit; do not assume push |
| Phase 12 | **Authorized to begin after Phase 11 documentation + Git checkpoint** | R&D / architecture/code/personality audit first, no bulk feature implementation |
| Phase 13 | **Reserved** for functional Themes | No implementation begun or implied |
| Subsequent phase numbers | **Unassigned** pending Phase 12 dependency audit | Voice final large software phase; Pi only after graduation and voice validation |
| Generated-public common acceptance | **SHADOW ONLY** | No Gate C enforcement permission |
| Existing technical **Gate C** | **NOT authorized** | Separate from five future product-graduation capability gates |

**Evidence and decision record:** `docs/PHASE11_BASELINE_EXIT_CHECKLIST.md` (accepted checklist and dated decision), `docs/KNOWN_LIMITATIONS_PHASE11.md` (original closure limitations; supplement with final benchmark observations), and the final October 19 holdout reports. The original closure handoff and manifest document the exact seven-file package. Do not infer future capabilities from automated acceptance.

**Historical correction:** The 17 September roadmap reported **153/153** tests; the 18 October planning snapshot reported **299/299** and acceptance still pending. Those figures were accurate snapshots, but are superseded by the **19 October 302/302 real-repository** result and explicit bounded Phase 11 acceptance. Neither historical blocker lists nor old acceptance status should be revived without new evidence.

**Tavily budget:** About 80% of the monthly allowance had been consumed by mid-October; remaining quota is unknown. Final October 19 live benchmarks are complete. Phase 12 should prefer repository inspection, cached evidence and mock/replayed fixtures over repeating live public research.
---

## 2. Mairon's intended identity and scope

**Mairon is a private-first, stateful, Regis-inspired personal companion and practical home/PC assistant**, not an attempt to replace frontier models for difficult programming, university assignments, complex writing, or frontier-class reasoning.

Its five equally important pre-Pi capability groups are:

1. **Independent personality and social intelligence** — not constant roasting; grounded banter, sympathy, thoughtful disagreement, durable identity and interests.
2. **Deep, grounded conversational intelligence** — sustained insightful, accurate, spoiler-aware discussions, especially fiction and sports; no invented details.
3. **Long-term memory, identity and accurate knowledge** — separate USER and Mairon opinions, canonical sourced knowledge, revisions, callbacks, resumability.
4. **Research and secure automation** — high-quality durable research, incremental updating, bounded privileged jobs, verified outcomes.
5. **Monitoring and sensible proactive attention management** — actionable PC/router/fantasy/media monitoring, ranked alerts and conversation starters, natural-language DND.

**Character can shape delivery, but never decide external truth or grant capabilities.** A compelling personality without substance fails; an expert automation daemon with a generic voice also fails.

**Preferred future surfaces:** Pi voice as primary interaction, Windows desktop as control centre + text/uploads, dedicated Mairon email as controlled remote channel. All should share one trustworthy Core and persistent state, not three separate assistants. These are goals, not statements of current capability.

---

## 3. Existing engineering foundation — historical implementation inventory

The September roadmap described the following features as implemented or partly implemented. They are useful architectural starting points, **not fresh audits** of every current source file. Verify code, tests and live behaviour before calling a future requirement complete.

| Earlier phase / workstream | Previously reported foundation | October interpretation |
|---|---|---|
| Core, routing, Answer Contracts | Epistemic router, factual and USER-history controls, authoritative state, claim grounding, local/cloud routing, conversation/referent state | Reuse and audit rather than reinvent. Phase 11 continually calibrates existing trust guards. |
| Personal services | Gmail read/search/triage, Google Calendar/routines/alarms, web/weather/routes | Existing partial foundations; not the new *dedicated Mairon email* or full remote capability. |
| **Phase 8** desktop actions | Approved app open/close/focus, safe local file finding/opening, Steam, browser destinations | Good groundwork for later bounded PC job executor; does not imply arbitrary desktop control or file exfiltration. |
| **Phase 9** Desktop Agent | Authenticated localhost IPC, allowlisted commands, limited protocols, fail-closed handling | Good PC-side trust boundary; Pi-to-PC or remote authentication requires fresh R&D. |
| **Phase 10** desktop app | Persistent chats, desktop shell/launcher, title/history UX, selectable text, diagnostic drawer, existing basic GUI STT/TTS | Desktop remains crucial control centre. Existing basic voice != future production Pi voice milestone. |
| **Phase 10.5** arithmetic | Core-owned deterministic calculations and follow-ups | Preserve, expand only by real need. |
| **Phase 10.6** sessions | Chat persistence, Core state restore, explicit session operations | Does not by itself imply advanced cross-channel long-term episodic/semantic memory. |
| **Phase 10.7** public grounding | Source admission, factual verification, opinion grounding, spoiler/medium/source-scope checks | Strong foundation but still has live acceptance edge cases; common generated-public acceptance remains shadow-only. |
| **Phase 10.10** Pi preparation | Handshake/wake decision/presence+wake configuration groundwork | Hardware deployment intentionally on hold. |
| **Phase 11.2–11.4** | Referents, seriousness/consequential advice, debate/stance state | Trust mechanisms exist. Persistent independent opinion *engine* not yet demonstrated. |
| **Phase 11.5.1–11.5.3.1** research | Earlier documentation reports research permission, SQLite job store, leasing, incremental evidence collection, foreground isolation | **Partial research infrastructure**, not confirmed finished synthesis, canonical incremental franchise knowledge, indefinite reliable scheduling, or ready-to-talk memory. |
| **Phase 11.5.4–11.5.8** | Earlier roadmap listed synthesis, quality, topic knowledge, refresh, notifications as next/planned | Reassess in Phase 12 against actual code; do not blindly carry old milestone numbers or assume delivery. |
| **Phase 11.6 / M1–M3 acceptance** | Extensive trust calibration, bounded verifier/grounding integrations, source and identity/relationship authority, tests | Phase 11 bounded baseline accepted on 19 October; no Gate C expansion. |

Historically described local model: `qwen3.5:9b`; historical optional cloud: GPT-5.6 Luna; PC has RTX 5080. **Check configuration before citing the model or cloud path as today's active runtime.** Bigger models were not a substitute for missing Core authority or knowledge.

Known repository paths, subject to confirmation:

```text
C:\Projects\Mairon\
  src/ai/ollama_provider.py
  src/core/claim_grounding.py
  src/core/user_history_obligations.py
  src/core/diagnostic_obligations.py
  src/research/public_explanation_targets.py
  src/research/public_factual_grounding.py
  src/research/research_jobs.py
  src/research/research_worker.py
  src/research/deep_research.py
  src/research/public_factual_research.py
  src/desktop_agent.py
  src/desktop_app.py
  tests/run_all.py
  personality.md              # locate and inspect current copy before changing persona
```

---

## 4. Phase 11 — BOUNDED BASELINE COMPLETED (19 October 2026)

### 4.1 Verified installation and final acceptance

Oliver installed the bounded closure package and ran the real `python tests/run_all.py`: **302/302 scripts PASS**, with zero reported failures. The same final installation produced **56/56 Oliver-style** and **51/51 Conversational Intelligence** automatic PASS results. Both final holdouts were run on `qwen3.5:9b` and manually reviewed; the conversational report covers 18 scenarios and 28 turns, averaging **7.82 s**. The battery-location/paws-off live smoke test did not publish unsupported future physical contact or invented past touching.

The final closure comprises two narrowly reviewed production replacements (`claim_grounding.py` and `acceptance_public.py`), three new regression scripts (31 + 10 + 52 = 93 methods), and two new documents (known limitations and exit checklist). No existing test or benchmark was deliberately weakened; the isolated delivery passed 302/302 before installation, and the real repository independently passed 302/302 afterward. Full-package SHA-256 data are in the final Codex manifest. Review and follow-up records should not claim any later Git commit until one has actually been made.

### 4.2 Explicit accepted limitations and human qualifications

**Baseline acceptance is not product graduation and not a claim of ≥8/10 human-conversation quality.** The user accepted the finite baseline despite known functionality and quality weaknesses, documented in the closure limitations and final human review:

- **TCP handshake-purpose explanation** still fails safely after two readable sources; actual selected witness/verifier payload was not retained. No fifth speculative binding patch or weakening of source roles is authorised.
- **Public retrieval and grounded current queries** can yield irrelevant/zero admitted evidence or truthful nonanswers (e.g. recent NVIDIA driver, media episode). **Public source provenance** still needs observability/annotation calibration; the official Python docs response claimed a page read but the shadow validator rejected source/read bindings, with incomplete evidence to adjudicate a lie versus annotation failure.
- **Ordinary local factual reliability** is imperfect. The final data-leakage explanation incorrectly treats ordinary house-price features as leakage; follow-up scaler explanation is correct. General trade-off questions sometimes fail closed unnecessarily.
- **Social depth and response quality** remain inconsistent: bland `Right, got you`, limited confident but grounded fandom opinions, awkward micro-acts, rejection retries and response latency. Figurative `watching you suffer` / `usual hiding spots` language is an embodiment **wording concern**, not independently proven sensor or physical-action history.
- **Positive trust controls remain**: corrections override earlier state; injected assistant-only location claims cannot replace USER evidence; spoilers respected; dangerous Git commands handled safely; calendar writes require approval; relevant Wi-Fi/VRR diagnostics are qualified; consequential transfer advice avoids unsupported recovery promises.

Future work should investigate causes with real provenance before implementation, while preserving honest refusal and strict authority. Serious newly discovered trust regressions still warrant normal bug triage; they do not retroactively negate the documented bounded acceptance without evidence.

### 4.3 Phase closure vs future work

Phase 11 ended by **explicit user decision on 19 October 2026** after final live post-patch benchmark review. The final exit documentation and Git milestone commit are administrative follow-through. Generated-public common acceptance is **SHADOW ONLY**; **Gate C remains unauthorized**. All five pre-voice graduation capabilities (G1–G5) still require a **separate, much broader evaluation**. The next engineering stage is **Phase 12 R&D**: inspect exact current source, current `personality.md`, schemas, supported integrations, trust boundaries, memory/research maturity and dependency architecture. Do not turn the known-limitations list into another open-ended Phase 11 implementation cycle.
---

## 5. Sequencing after the Phase 11 baseline

### Phase 12 — R&D, codebase audit, architecture and roadmap expansion (**reserved, next**)

First obtain the **exact current repo** and the actual current `personality.md`. Build a capability matrix marked **implemented / partial / absent / blocked / needs R&D**, rather than projecting aspirations into implementation status. Review:

- existing code for memories, conversation state, opinion/debate, research jobs/evidence, scheduling, source admission, Gmail, app uploads, alerts and Desktop Agent;
- `personality.md` line by line: translate relationship/banter/ego/greetings/opinions/research hooks/annoyance budgets into typed state, policies and acceptance criteria; preserve the authored document;
- one canonical knowledge/state strategy: research jobs vs factual topic knowledge vs USER memory vs Mairon opinions; durable checkpoints, provenance, deduplication, revision and context retrieval;
- securely authenticated jobs/actions and remote ingress; per-action threat models, provenance of requests, approval levels, audit and recovery;
- external-feasibility spikes: ASUS API/logs, ESPN fantasy data, StreamingFinder schema, screenshot/OCR/vision, email provider/auth, Windows Defender interfaces, WOL, sensors, solar-inverter options;
- resource-aware background scheduler: PC-on/off, gaming preemption, Pi light compute vs PC heavy compute/cloud, Tavily and token budgets;
- voice stack constraints **only at feasibility level** so early architecture supports later low-latency/barging/DND, without building full voice now;
- security/privacy retention, backup encryption and recovery.

**Deliverables:** audited capability matrix, architecture decision records, dependency map, explicit phase numbering for later work, priority/risk/effort/acceptance criteria, test fixtures, a versioned roadmap and a reviewed plan with the user. No broad refactor silently starts just because the roadmap is updated.

### Phase 13 — Themes (**reserved; already committed direction**)

Make the existing nonfunctional Themes section real: preset themes, custom saved themes, HEX/RGB editing, persistent preferences, live preview/application where practical without restart. Preserve the current charcoal/pink appearance as a selectable preset or sensible default. Test persistence, invalid colours, component coverage and UI regressions. No voice in this phase.

### Later implementation — numbered **after Phase 12**, not today

Workstreams below are **dependency-shaped proposals, not numbered mandates**. Some must proceed in parallel; especially personality and security must not be left until the end.

| Proposed workstream | Core outcome and dependencies | Test focus |
|---|---|---|
| **Shared durable intelligence foundation** | canonical topic/entity/source claims; revisions and conflict status; separate USER, assistant opinion and research jobs; retrieval; restart-safe storage | duplicate merges, conflicting versions, provenance, recoverability, selective recall |
| **Research quality and jobs maturity** | finish/verify evidence-to-synthesis, partial result handling, budgets, durable resumable jobs, deadlines/checkpoints, selective incremental refresh | interruption/power loss, unchanged data, source honesty, no repeated full franchise crawl |
| **Regis personality + independent opinion engine** | implement `personality.md` via persistent state/policies; autonomous but reasoned likes, nuanced banter, empathy, durable sports allegiance, recommendations/callbacks | sessions/months, disagreement, legitimate opinion updates, no fake experience/advice |
| **High-quality conversation/knowledge use** | coherent deep multi-turn literary/technical discussions and user progress/medium/spoiler constraints; research-later/resume | TBATE Alacrya extended discussion, COTE, One Piece, grounded pushback, concise spoken turns |
| **Security-first capability/jobs layer** | allowed typed actions, approval tiers, state machine, logs, idempotency, cancel/retry/verify/safe-fail; PC node | forged requests, risky shutdown, failed scan, safe file transfer, no raw shell |
| **Private channels and shared ingestion** | email identity, desktop attachments, trusted destination/sender policy, shared screenshot/media/fantasy pipeline | duplicate email/desktop screenshot updates one record; prompt injection & spoofing |
| **Useful integrations** | StreamingFinder ratings separated from Mairon's opinions; fantasy weekly matchup research; PC file actions; Defender; ASUS monitoring | verified data, scope, cross-channel recall, permission and fallback when API missing |
| **Selective proactivity + attention** | ranked topic queue, cooloffs, natural-language DND, read/unread spoilers, interest recency, notifications and quiet background jobs | router vs fantasy vs chapter priority, no info dump, quiet hours and configurable critical overrides |
| **Cross-device durability** | backup/restore, Pi/PC orchestration feasibility, secure remote operation, policy for PC offline/cloud | outage recovery, encrypted backups, bounded storage, credential lifecycle |

**Security is concurrent with every privileged feature**, not a final-stage checklist. Avoid building optional TV/PS5/media gimmicks before the high-value flows are dependable.

---

## 6. Full-system graduation — required **before voice**

This is an independent final evaluation of all five equally mandatory capabilities, not the narrow Phase 11 trust benchmark. To avoid confusion with the existing technical "Gate C", label these **graduation capabilities G1–G5**:

- **G1 Personality and social intelligence:** consistent independent identity, researched tastes, sports loyalty, serious/empathic judgement, earned banter, accurate long-horizon callbacks and the restraint to stay quiet.
- **G2 Conversational intelligence:** deep multi-turn, source-grounded discussions (e.g. TBATE Alacrya, other favourite fiction, fantasy), meaningful independent interpretations, no sycophancy or invented canon.
- **G3 Memory, identity and knowledge:** canonical factual research, USER vs Mairon separation, revisions, recommendation proof, spoiler progress, survive weeks/restarts.
- **G4 Research and secure automation:** incremental research, checkpoint/resume/delivery, verified authorised PC and remote jobs, safe failures and audits.
- **G5 Monitoring and attention management:** evidence-based router/PC/fantasy/release monitoring, sensible ranked/cooldown prompts, DND, appropriate notification channels.

**ALL five must pass.** Include simulated adversarial/failure scenarios plus genuine sustained conversations. The standard is a compelling and useful Mairon—not benchmark equivalence to a frontier model. The user makes the explicit graduation decision. Re-read the detailed vision's scenario matrix before finalising the rubric.

---

## 7. Voice and Raspberry Pi — deliberately late

**Voice:** final substantial *software* phase after G1–G5 graduate. Prototype feasibility earlier only. Validate on existing PC where practical: wake word, STT Australian English/slang/names, TTS character and pace, conversational short-turn design, interrupts/barge-in, follow-up listening, DND/privacy, tool/permission parity with text/email, latency/reliability and fallback. Existing desktop GUI STT/TTS is a foundation, **not** proof of this production voice phase.

**Pi:** only after the voice milestone is satisfactory, acquire and integrate Raspberry Pi + likely **512 GB or 1 TB SSD** (selection R&D closer to purchase). Pi should provide always-on orchestration, voice, storage and appropriate lightweight work. Heavy Qwen inference may still require Windows RTX 5080/cloud; define PC-off behaviour explicitly. User PC has approximately **5 TB total storage**, with HDD for **encrypted, incremental, restore-tested** Pi backups when reachable. Consider an independent backup copy for irreplaceable identity/knowledge. Real hardware brings a *further* final end-to-end acceptance, not a guaranteed intelligence upgrade.

No artificial release deadline and no hardware purchase before readiness.

---

## 8. Non-negotiable product/engineering boundaries

- User fact, model guess, public evidence, research inference and Mairon opinion are different authorities.
- A humorous 'I told you so' requires **logged actual prior advice** plus verified outcome; no invented sports score, read/watch experience or room observation.
- Independent opinions may change with evidence and reasons; **chosen sports allegiance remains committed** across losing seasons. No hardcoded pizza/team/film quirks.
- Honour user interests even when Mairon independently disagrees. Tease, then engage substantively.
- One Piece research is *incremental*: confirm new release, delta-update canonical topics, maintain spoiler limits. No automatic weekly full crawl.
- Research may take minutes/hours/days **only when actual durable orchestration is working**. Persist findings if the user defers discussion for weeks. Do not pretend offline work happened.
- Proactivity is one ranked, spaced item at a time; urgent security/router issues may outrank fantasy; close fantasy may outrank a routine manga notification. Explicit natural-language DND overrides unsolicited delivery subject to user-set critical rules.
- Fantasy screenshot ingestion **email OR desktop**, same validated pipeline/record. Old roster data never masquerades as current; double submissions deduplicate.
- Dedicated email account is a **future** controlled channel, not existing Gmail-read access. `From` allowlist/SPF/DKIM/DMARC alone cannot authorise high-risk actions. Approval, replay protection, trusted destinations and audit are required.
- Defender scan must verify signatures, job completion and new detections; shutdown only under preapproved safe conditions. Daytime solar scheduling is preference, **not** inferred measured surplus.
- ASUS monitoring should distinguish WAN, Wi-Fi and Ethernet backhaul through actual data; initial interface should be read-only.
- No arbitrary generated PowerShell/shell execution, no unrestricted filesystem/network action, no implicit sensitive-file transfer.
- Avoid Tavily waste and overfitting to benchmarks; preserve tests, deterministic fixtures and exact source lineage.
- Meaningful clean milestones should be committed, using repo-local Git identity, excluding secrets and user data.

---

## 9. Practical repo workflow and next-chat handoff

### Run/diagnose

```powershell
cd C:\Projects\Mairon
python tests\run_all.py
python benchmarks\run_oliver_style_benchmark.py
python benchmarks\run_conversational_intelligence.py --full
# Only when safe targeted structural public-binding diagnostics are needed:
$env:MAIRON_DEBUG_PUBLIC_BINDING = "1"
# Then remove it again after targeted run:
Remove-Item Env:\MAIRON_DEBUG_PUBLIC_BINDING
```

**Do not launch full live benchmarks automatically from documentation changes.** Use mock data for ordinary regression. The tests/scripts above reflect current discussion; confirm paths and CLI against actual repo if renamed.

### Source and handoff priority

1. Exact current repo/source and actual test/benchmark output; latest user acceptance decision.
2. Latest technical Phase 11 handoff / installed-file manifest; current `personality.md`.
3. **This** dated roadmap for phase/state sequence.
4. `MAIRON_Detailed_Vision_and_Requirements_2026-10-18.md` for detailed product acceptance targets, examples and open R&D.
5. Historical 18 October brainstorming handoff and September roadmap for provenance, not for superseding current code.

### When a new Mairon development chat begins

State explicitly:

> As of 19 Oct 2026, **Phase 11.6.6j.1 was explicitly accepted as a bounded engineering baseline** after **302/302 real regression**, **56/56 final Oliver-style** and **51/51 final conversational** automatic checks plus human response-level review. This does **not** establish final G1–G5 graduation or Gate C permission. Phase 11's known limitations, including TCP and public-provenance uncertainty, remain open. The **Git checkpoint has not been confirmed committed** in this document; verify repository status before assuming it. Next: finish the milestone commit, then begin Phase 12 R&D audit of exact current code and personality, not a wholesale rewrite.

Use individual full replacement files, not ZIP, when proposing code patches; verify exact current files; compile, run focused tests and full regression; perform live acceptance only when justified. The bounded baseline has now been accepted; commit its documented milestone before beginning Phase 12 R&D. Assign later phase numbers only after Phase 12 audit.

---

## 10. Open audit questions (not promises)

- What is the current exact `personality.md` and how much is already executed by Core vs merely prompt text? The project-file copy located for planning is dated 30 August 2026; this is **not proof it matches the live repo**.
- What parts of 11.5.4–11.5.8 have actually been implemented since September? How stable is background research under days of interruption and PC power-off?
- Is there already any attachment ingestion in the desktop UI? If so, its precise formats/security limitations and how to reuse it.
- Which of email, screenshots, StreamingFinder export, ESPN fantasy, ASUS API, Defender scan and WOL integrations are supported by current code vs design only?
- What are the real model settings and cost/performance trade-offs when the PC is busy/off? How should cloud escalation work?
- What canonical storage, knowledge merging, long-term recommendation history, persona opinion ledger and scheduler architecture best fits the actual repo?
- Which cross-cutting permissions and tests must be in place before remote email commands or file delivery?
- How should voice privacy, hands-free interruptions and critical DND exceptions be configured?
- What is the remaining Tavily quota at the time live integration tests are requested?

**This roadmap is a planning document. Updating it is not an implementation step, and none of the future features should be marked complete without code and test evidence.**
