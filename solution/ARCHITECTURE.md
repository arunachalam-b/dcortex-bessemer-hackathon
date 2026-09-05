# Crew Ops Advisor — Solution Architecture

**Hackathon:** dCortex "Agentic Crew Ops Advisor"
**Status:** Fully built and verified live. Deterministic engine passes
**41/41** answer-key checks; **124 pytest tests** green; the provider-agnostic
AI layer (`crew_ops/llm/` — Claude or Sarvam, switched via `.env`) runs the
full 44-item LLM eval end-to-end (best full run: 38 PASS + 3 MANUAL);
web UI with streaming chat, eval runner and voice input; SQLite-backed
dataset mirror and eval-run history. See [README.md](README.md) for how to run
everything.

---

## 1. The One Decision That Matters

The problem statement asks a single architectural question:

> *What should the language model do, what should deterministic code do, and how do you compose them into a system that is both conversational and correct?*

Our answer, stated as a hard rule the whole system enforces:

> **The LLM never computes a number. Deterministic code never interprets language.**
>
> - The LLM does three things only: **understand** the controller's question, **plan** which tools to call, and **narrate** the tool results back in plain language.
> - Every fact, hour, cost, legality verdict, and ranking is produced by a **deterministic Python engine** operating on the dataset — with a machine-generated reasoning trace.
> - The LLM's narration is **checked, not trusted**: a deterministic groundedness gate flags any dataset-shaped fact (crew/pairing/flight ids, registrations) not backed by a tool result, and a completeness check appends any tool-computed fact the narration dropped.

Why this boundary and not another:

| Alternative | Why we rejected it |
|---|---|
| **Stuff all JSON into the prompt, let the model answer** | Works for Tier 1, fails Tiers 2–3. Duty-hour arithmetic across rolling calendar windows is exactly what LLMs approximate wrong — fluently and confidently. An answer that is 1h20m wrong on RULE-DUTY-02 is a regulatory violation, not a rounding error. |
| **LLM writes SQL / code per question (text-to-SQL, code-interpreter)** | Better, but the legality logic (FDP sector reductions, calendar-day windows, reserve on-call semantics, deadhead repositioning) is subtle enough that freshly generated code will be wrong in unverifiable ways. Also slow and non-deterministic — the same question can get different answers on different runs. |
| **Pure rules engine with keyword/NLU front end** | Correct but brittle and not conversational. Fails the "natural language is the primary interface" mandate the moment a question is phrased unexpectedly. |
| **Ours: LLM tool-calling over a fixed deterministic engine** | The rules are written **once**, tested against the provided answer keys, and reused for every question. The LLM contributes what it is actually good at — language and planning — and nothing else. Same tool call → same answer, every time. |

---

## 2. System Overview (as built)

```
  Controller
      │  browser                                   ┌──────────────────────────┐
      ▼                                            │ cli.py — the same stack  │
┌─────────────────────────────────────────────┐    │ without the browser:     │
│  WEB UI  (web/index.html, single file)      │    │ ask / chat / demo /      │
│  • Chat — streamed answers, tool-call chips │    │ tools / call / repl      │
│    in plain language, expandable results    │    └───────────┬──────────────┘
│  • Questions / Scenarios browsers           │                │
│  • Eval tab — run/watch evals, run history  │                │
│  • 🎤 voice input (browser → 16k WAV)       │                │
└──────────────┬──────────────────────────────┘                │
               │ NDJSON stream + JSON REST                     │
┌──────────────▼──────────────────────────────┐                │
│  server.py  (stdlib ThreadingHTTPServer)    │                │
│  /api/chat /api/transcribe /api/eval/*      │                │
└──────────────┬──────────────────────┬───────┘                │
               │                      │ audio                  │
               │            ┌─────────▼──────────┐             │
               │            │ llm/stt.py         │             │
               │            │ Sarvam Saarika STT │             │
               │            └────────────────────┘             │
┌──────────────▼────────────────────────────────────────────── ▼───────┐
│           AI LAYER  (crew_ops/llm/ — provider-agnostic)              │
│  config.py    .env → LLM_PROVIDER=claude | sarvam                    │
│  providers.py one neutral conversation format; Claude via the        │
│               anthropic SDK, Sarvam via stdlib HTTP                  │
│  agent.py     advisor loop: plan → call tools → narrate, plus        │
│               • groundedness gate (ids not in tool results flagged)  │
│               • completeness rounds (dropped tool facts re-added)    │
│               • continuation stitching on max-token cut-offs         │
│               • history compaction under provider context budgets    │
╞══════════ tool-call boundary — 19 typed tools, JSON in/out ══════════╡
│               DETERMINISTIC ENGINE  (crew_ops/, pure Python)         │
│                                                                      │
│   ┌────────────┐  ┌────────────┐  ┌─────────────────────────┐        │
│   │  QUERY     │  │ SIMULATION │  │ RECOMMENDER             │        │
│   │  query.py  │  │ engine     │  │ recommender.py          │        │
│   │  (Tier 1)  │  │ (Tier 2)   │  │ (Tier 3: enumerate →    │        │
│   └─────┬──────┘  └─────┬──────┘  │  filter → cost → rank)  │        │
│         │               │        └──────┬──────────────────┘         │
│         │         ┌─────▼───────────────▼──────┐                     │
│         │         │  RULES ENGINE (rules.py)   │                     │
│         │         │  7 pure functions, one per │                     │
│         │         │  RULE-*; every check emits │                     │
│         │         │  verdict + arithmetic trace│                     │
│         │         └─────────────┬──────────────┘                     │
│   ┌─────▼───────────────────────▼─────────────────────────┐          │
│   │  WORLD STATE (world.py — in-memory indexes,           │          │
│   │  copy-on-write overlays for what-if simulation)       │          │
│   └───────────────────────┬───────────────────────────────┘          │
└───────────────────────────┼──────────────────────────────────────────┘
                            │
              ┌─────────────▼──────────────────────────────┐
              │  STORAGE (db.py → crew_ops.db, SQLite)     │
              │  • dataset mirrored in verbatim once;      │
              │    JSON files remain the fallback          │
              │  • full eval-run history (runs + graded    │
              │    per-item results + transcripts)         │
              └────────────────────────────────────────────┘
```

The **LLM vs. deterministic boundary is the tool-call interface**: everything
above it is language, everything below it is arithmetic. This is the diagram we
present to judges.

---

## 3. Deterministic Engine (the source of truth)

### 3.1 World State & Storage

All 10 JSON files load once at startup into an in-memory, indexed object graph
(dataset is ~150 crew / 147 flights — small enough that all reasoning happens
in memory).

Indexes built at load:
- `crew_by_id`, `flight_by_id`, `flights_by(date, dep_station)`, `flights_by_aircraft_rotation`
- `pairing_by_id`, `pairings_by_crew`, `pairings_by_aircraft`, `crew_of_flight` (derived: flight → pairing → complement)
- `duty_history_by_crew` (28-day daily grid — this is what makes rolling windows computable on any date)
- `reserves_by(base, date)`, `certs_by_crew`, `risk_by_crew`

**SQLite sits under, not instead of, the object graph** (`crew_ops/db.py` →
`crew_ops.db`, override with `CREW_OPS_DB`). The frozen dataset is mirrored in
verbatim once (rows keyed by file + sequence; the DB refuses to serve if it was
seeded from a different data directory); `load_world` and the server read from
SQLite and fall back to the JSON files on any DB error. The same database keeps
the **full eval-run history** (every run's provider, per-item status and
transcript), which is what the web UI's run-history dropdown serves. The
reasoning still runs on the in-memory indexes — SQLite buys durability and
history, not query power, at this scale.

**Copy-on-write overlays** implement what-if: a simulation clones nothing, it
layers a `Disruption` delta (crew removed, flight delayed, station closed, cert
invalidated) over the base snapshot. This gives us scenario independence for
free (S2's sick call never leaks into S6's world) and makes chained disruptions
(an optional enhancement) a stack of overlays.

### 3.2 Rules Engine

One pure function per rule, signature `check(world, crew_id, proposed_duty) -> Verdict`:

```
Verdict = { rule_id, pass: bool, computed: {…}, limit: {…}, margin, detail }
e.g. RULE-DUTY-02 →
  { rule_id: "RULE-DUTY-02", pass: false,
    computed: { window: "2026-09-09..09-15", duty_hours: 61.33 },
    limit:    { max: 60 },
    margin: -1.33,
    detail: "48.50h (Sep 9–14 history) + 12.83h (proposed duty Sep 15) = 61.33h > 60h — exceeds by 1h20m" }
```

Domain conventions are encoded exactly as `rules.json` and the dataset README define them — these are the correctness traps the dataset is engineered around:

- **Duty period** = report (first dep −60 min) → release (last arr +30 min).
- **FDP-01**: max FDP = 13h − 0.5h × (sectors − 2).
- **DUTY-02 / FLT-03**: **calendar-day** rolling windows (7 / 28 UTC dates, inclusive of duty date), summed from `daily_history` **plus the proposed duty** — not the pre-baked `duty_hours_7d` summary, which is only valid as-of the snapshot.
- **REST-04**: ≥12h from last release to next report.
- **Reserve semantics**: the **required report time** (after any deadhead positioning) must fall inside the on-call window; once activated, a reserve is line crew — the window no longer constrains later days. (This is precisely the `C-3305` teaching trap: legal for day 1 of P-2291 in isolation, breaches DUTY-02 on day 2 — a per-day check that forgets multi-day pairings gets this wrong.)
- **Deadhead (BASE-07)**: positioning uses the real schedule (DEL→BLR via DX402 odd dates / DX589 even dates), new report = arrival +15 min, cost = callout + positioning + delay-hours × `delay_cost_per_duty_hour`. `check_assignment_legality` surfaces the positioning flight, induced delay and RULE-BASE-07 explicitly for out-of-base covers.

**`evaluate_cover` always runs all 7 rules** and returns all 7 verdicts, pass
or fail. The trace therefore shows not just *why* an option is illegal but
*what was checked* on a legal one — which is what `rules_checked` in the
expected Tier-3 output shape asks for.

### 3.3 Simulation Engine (Tier 2)

Input: a typed `Disruption` — the same event vocabulary as `scenarios.json` (`SICK_CREW`, `STATION_CLOSURE`, `DELAY`, `CERT_EXPIRY`, `MULTI_SICK`) so the provided answer keys directly test this layer.

Pipeline: **event → affected pairings → uncovered/affected flights (all remaining legs of the pairing, both days) → downstream cascade** (aircraft rotation knock-ons for delays; re-run rules on the rostered crew under the shifted times to detect induced FDP/rest breaches) **→ impact summary** (flights, pairings broken, passengers = Σ seats, rule risks).

Output matches the problem statement's Tier-2 shape (`uncrewed_flights`, `pairing_broken`, `downstream_risks`, `passengers_affected`) plus the trace. The simulator never mutates the world.

### 3.4 Recommender (Tier 3)

Deliberately a **transparent enumerate-filter-rank**, not an optimizer (explicitly not required, and explainability is weighted higher):

1. **Enumerate candidates** for each uncovered role: reserves at base → day-off line crew at base → deadhead candidates from other bases → (last resort) delay or cancel.
2. **Filter** each through the full 7-rule legality check against the overlay world.
3. **Cost** each from `costs.json` (callout / day-off / deadhead + delay hours / cancellation / hotel).
4. **Rank** lexicographically: coverage (full pairing first) → legal → total cost → delay → reachability. Equal-cost options share a rank tier (the S6 answer key treats mirror assignments as equally correct).
5. For `MULTI_SICK`: `recommend_joint` resolves simultaneous disruptions jointly — exhaustive over per-pairing legal options with a conflict check so one reserve is never recommended twice. At this scale exhaustive pairing is cheap.
6. `recommend_delay_recovery` handles the FDP-breaching-delay case: split the duty at the longest legal prefix, re-crew or cancel the tail, ranked by cost.

Every option carries `legal`, `rules_checked` (all 7 verdicts), `cost_inr` (itemized), `coverage`, `delay_hours`, the rejected candidates **with the rule that killed each one**, and the reasoning trace.

### 3.5 Reasoning Trace (explainability as a data structure, not prose)

Every engine response includes `sources` and a `trace`: an ordered list of steps `{step, source_file, inputs, computation, result}`. The trace is **generated by the code that did the computation** — it cannot drift from the answer. The LLM summarizes it; the UI shows it verbatim under each tool-call chip. A controller can challenge any line and see exactly which file and which numbers produced it. This is our answer to "no reasoning trail".

---

## 4. AI Layer (as built — `crew_ops/llm/`)

### 4.1 Provider abstraction

The advisor speaks one **neutral conversation format**; each provider
translates to its wire format (`providers.py`):

- **Claude** — via the `anthropic` SDK (`claude-opus-5` by default), thinking
  and tool_use blocks echoed back verbatim, server-side refusal fallbacks on
  by default.
- **Sarvam** — via stdlib `urllib` to `api.sarvam.ai` chat completions
  (`sarvam-105b` by default), OpenAI-style tools. No third-party dependency.

`LLM_PROVIDER=claude|sarvam` in `.env` is the whole switch (real env vars
override the file). Adding a third provider is one subclass with two
translation functions; the agent loop, grounding, CLI, server and evals are
untouched.

### 4.2 The advisor loop (`agent.py`)

Single agent with the **19 typed tools** from `crew_ops/tools.py` (JSON-schema'd thin wrappers over the engine):

| Tier | Tools |
|---|---|
| 1 | `lookup_crew`, `lookup_flights`, `get_duty_clock`, `get_reserves`, `get_certifications`, `get_risk_signals`, `get_pairing`, `get_duty_watchlist` |
| 2 | `simulate_sick_crew`, `simulate_station_closure`, `simulate_delay`, `check_certification_validity`, `check_assignment_legality`, `compute_rest_requirement`, `cancellation_impact` |
| 3 | `recommend_cover`, `recommend_joint`, `recommend_delay_recovery`, `draft_notification` * |

\* `draft_notification` is the one place generation is the point — but its facts (report time, flights, pairing) are injected from the engine; the LLM only words the message.

The system prompt pins snapshot "now" = `2026-09-14T18:00:00Z`, requires
entity resolution to canonical ids (echoed back so the controller can verify),
forbids the model computing any number itself, demands full rule ids and every
table row in answers, and mandates honest refusal when no tool answers.
`tools.dispatch` normalizes arguments at the boundary (rank aliases like
"captain"/"FO", case-insensitive stations/aircraft/ids) so a
casually-phrased call can't silently return zero candidates, and converts
**every** engine exception into an `ok: false` refusal with a hint — the model
gets a correctable error, never a crash.

### 4.3 Robustness machinery (what live eval runs forced us to build)

These were all added in response to observed live failures, not speculation:

- **Groundedness gate** — deterministic scan of the final answer for crew ids,
  pairing ids, flight numbers and registrations (patterns widened to catch
  garbled ids); anything absent from the collected tool results and the
  question itself triggers a one-shot correction round, and residual
  violations are flagged in the shown answer. Mechanically enforces "invented
  facts are treated as failures".
- **Completeness rounds** — `assessment_gaps()` diffs the drafted answer
  against the tool results (per-flight assessment rows, excluded candidates
  and the pairing ids in their reasons, per-day passenger counts); up to 3
  correction rounds, then a deterministic **"[completeness check]" addendum**
  appends any still-missing tool facts, mirroring the groundedness footnote.
- **Continuation stitching** — a `max_tokens` cut-off is detected and the
  answer continued across up to 4 turns, invisible to the caller.
- **Context compaction** — history is kept under a per-provider character
  budget (Sarvam 220k, Claude 600k) by eliding the oldest tool results first,
  then truncating oversized recent results (a parallel tool-call burst can
  blow the context in one step); a context-overflow provider error triggers
  one compact-and-retry.

### 4.4 Voice input (STT)

Mic button in the chat → browser `MediaRecorder` → re-encoded in-browser to
16 kHz mono PCM WAV → `POST /api/transcribe` → `llm/stt.py` → **Sarvam Saarika**
(`saarika:v2.5`, auto language detection) → transcript dropped into the chat
input for the controller to review before sending. STT always uses Sarvam
regardless of `LLM_PROVIDER`. Speech never bypasses the text pipeline — the
transcript is editable before it becomes a question.

### 4.5 Latency

Tier-1 questions: one plan round-trip + tool execution (pure Python, <50 ms) +
narration ≈ 4–15 s observed. Tier-3 scenario answers with dozens of tool calls
run 1–2.5 min at the worst (see the eval tab's per-item timings) — inside the
"usable on a live shift" bar for a decision aid, and the tool-call chips stream
in live so the controller watches the reasoning assemble instead of a spinner.

---

## 5. Conversational UI (as built)

Deliberately dependency-free: `server.py` is a stdlib `ThreadingHTTPServer`,
the whole front end is one file (`web/index.html`). Four tabs:

- **Chat** — multi-turn advisor (per-session context server-side). Answers
  stream as NDJSON events; every tool call appears live as a **plain-language
  chip** ("checking who can cover P-2291…"), expandable to the full engine
  JSON including trace and sources. Failed calls show "didn't work,
  adjusting…" with the error in the tooltip — the self-correction is visible,
  not hidden.
- **Questions / Scenarios** — every item from `questions.json` (filterable by
  tier) and `scenarios.json` with expected answers expandable, and one-click
  **Test in chat**.
- **Eval** — run the full LLM eval (all 44, per-tier, scenarios-only, or a
  custom id list) from the browser; live PASS/PARTIAL/MANUAL/ERROR counts,
  atom coverage, per-item missing atoms and transcripts; a **run-history
  dropdown** over every past run (served from SQLite); status legend behind
  an ⓘ popover.

The same AI layer drives `cli.py ask` / `cli.py chat` for a terminal-only demo,
and `cli.py demo | tools | call | repl` exercise the engine with no LLM at all.

---

## 6. Correctness Harness (how we know it's right)

Two harnesses over the same 44 items (38 questions + 6 scenarios) — full
catalog in [EVALS.md](EVALS.md):

1. **Deterministic regression** (`run_regression.py`): every question and
   scenario replayed straight against the engine and diffed structurally
   against the shipped answer keys. **41/41 pass** (the 3 open-ended prose
   questions Q30/Q36/Q38 are flagged for human judging, never auto-passed).
   This is the ceiling: if the LLM plans the right tool calls, the answer is
   right.
2. **Live LLM eval** (`run_llm_eval.py`, also runnable from the web UI):
   the real natural-language prompt through the real advisor, graded by
   **atoms** — every id, timestamp and non-zero number in the answer key must
   literally appear in the prose answer. Every run is recorded in SQLite.
   Results: **best full 44-item run 38 PASS + 3 MANUAL + 2 PARTIAL + 1
   ERROR** (Sarvam `sarvam-105b`); every auto-graded item has passed in at
   least one recorded run; run-to-run variance remains (the final full run
   scored 33 PASS) — see §7.
3. **Unit tests** (124, `python3 -m pytest tests/`, <1 s, fully offline —
   the AI layer is tested against a fake provider): pinned to the engineered
   facts — C-2087 breaches DUTY-02 by exactly 1h20m, C-3310 covers P-2291 at
   ₹18,500, C-2210 deadhead totals ₹41,200, C-3305 fails day 2, C-2091 fails
   QUAL-05.

Because held-out scenarios reuse the same event types, passing the visible
keys via a **general engine** (not answer-key lookup) is our generalisation
story.

---

## 7. Known Limits & Failure Modes (reported honestly)

1. **LLM narration is not deterministic.** The engine gives the same answer
   every time; the advisor does not. The same eval item can PASS on one run
   and go PARTIAL on the next when the model drops a table row or rounds a
   number in prose (typical flaps: long numeric tables like Q35's duty
   watchlist, and the biggest scenario answers). The correction machinery in
   §4.3 recovered most of this — full-run scores went from 31 to 38 PASS —
   but it is a mitigation, not a proof. This is our documented failure case.
2. **Entity resolution is the soft spot.** "The VT-DXE captain", "tomorrow" →
   canonical ids/dates is the LLM's job and its main risk. Mitigations:
   resolved entities are echoed back in the answer; the tools accept only
   canonical ids so a bad resolution fails loudly (`ok: false` + hint), never
   silently.
3. **Questions outside the tool vocabulary** get an honest refusal, not an
   attempt. Open-ended questions (Q30/Q36/Q38) produce grounded drafts but
   are flagged `MANUAL` — we don't pretend prose can be auto-verified.
4. **Rest before the first cover duty** is only checkable via
   `last_rest_ended` (daily history has no report/release times), so the
   check applies only when the cover starts the sequence.
5. **RULE-FLT-03 on covers**: we count the cover's block hours into the
   28-day window — stricter than the answer keys. On this dataset the two
   never diverge; ours is the safer reading.
6. **Recommender is heuristic**, exhaustive at 2–3 simultaneous events; at
   real scale this becomes CP/MIP behind the same tool interface.
7. **Live-tested asymmetrically**: the Sarvam path (LLM + STT) is verified
   live end-to-end; the Claude path is fully built and unit-tested against
   recorded wire formats but was not exercised against the live API during
   the hackathon (no key at hand).

## 8. Scalability & Production Notes (commentary, not build scope)

- **Scale**: at real-airline scale (10⁴ crew, 10³ daily legs) the in-memory
  world state moves to Postgres + an incremental legality cache keyed by
  (crew, date); the rules engine and trace format are unchanged — the boundary
  is the durable design, not the storage. (The SQLite mirror already
  establishes the load-from-DB path.) Candidate enumeration gets pruned by
  base/rating indexes before rule-checking, and the recommender graduates to a
  CP/MIP solver behind the same tool interface.
- **PII**: crew names/reachability are personal data in production —
  engine-side role-based redaction (the LLM sees crew ids, never phone-level
  data), audit-logged tool calls (the SQLite run history already stores full
  transcripts — the trace doubles as an audit record), and data residency with
  the airline. The LLM boundary helps here: sensitive fields simply never
  enter the prompt.

## 9. What Got Built (the 24h plan, executed)

| Phase | Deliverable | Status |
|---|---|---|
| 1 | World state loader + indexes; rules engine + unit tests pinned to engineered facts | ✅ |
| 2 | Query service (Tier 1) + LLM advisor with tools + CLI chat | ✅ *(minimum viable)* |
| 3 | Simulation engine + overlays; deterministic regression 41/41 | ✅ *(strong)* |
| 4 | Recommender + ranked options; web chat with streamed tool traces | ✅ *(exceptional)* |
| 5 | Notification drafting, multi-turn what-ifs, failure-case writeup, deck | ✅ |
| + | Live LLM eval harness with atom grading + web eval runner + run history (SQLite) | ✅ |
| + | Provider switchability (Claude/Sarvam) behind one interface | ✅ |
| + | Voice input (Sarvam Saarika STT) | ✅ |

The engine was built and tested with zero LLM dependency; the two workstreams
(engine vs. AI layer/UI) met at the tool schema, which was frozen first.

---

*Summary for the judges: the LLM is the interface, the engine is the authority, the trace is the contract between them — and the eval history is the receipt.*
