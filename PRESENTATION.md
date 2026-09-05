# Crew Ops Advisor — Architecture & Results

**dCortex "Agentic Crew Ops Advisor" hackathon · Team submission overview**

A conversational advisor for airline Crew Control: a controller asks a question in
plain language; the system answers correctly, fast, with reasoning it can prove —
and says so when it can't.

---

## 1. The central question, and our answer

The problem statement asks one architectural question:

> *What should the language model do, what should deterministic code do, and how
> do you compose them into a system that is both conversational and correct?*

Our answer is a hard rule the whole system enforces:

> **The LLM never computes a number. Deterministic code never interprets language.**

- The LLM does three things: **understand** the question, **plan** tool calls,
  and **narrate** results in plain language.
- Every fact, hour, cost, legality verdict and ranking comes from a
  **deterministic Python engine** over the dataset — with a machine-generated
  arithmetic trace.
- A deterministic **groundedness gate** re-scans the LLM's final answer: any
  crew id, pairing, or flight number not present in the tool results is flagged
  as unverified. Invented facts are mechanically caught, not hoped away.

Why not the alternatives:

| Approach | Why it fails here |
|---|---|
| Put the JSON in the prompt, let the model answer | Works for Tier 1, fails Tiers 2–3. Rolling duty-window arithmetic is exactly what LLMs approximate wrong — fluently and confidently. A 1h20m error on RULE-DUTY-02 is a violation, not a rounding error. |
| LLM generates SQL/code per question | Freshly generated legality logic is wrong in unverifiable ways; same question can get different answers on different runs. |
| Rules engine + keyword NLU front end | Correct but brittle — fails "natural language is the primary interface" the moment phrasing varies. |
| **Ours: LLM tool-calling over a fixed, tested engine** | Rules written once, verified against the dataset's own answer keys, reused for every question. Same question → same numbers, every time. |

---

## 2. System architecture

```mermaid
flowchart TB
    C([Crew Controller]) -->|plain-language question| UI

    subgraph CONV["Conversational layer"]
        UI["Web chat (4 tabs) + CLI ask/chat<br/>answer prose · structured cards · live tool chips<br/>expandable 'Show reasoning' trace"]
    end

    subgraph LLML["AI layer — crew_ops/llm/ (provider-agnostic)"]
        AG["Advisor loop (agent.py)<br/>1 understand & resolve entities → canonical ids<br/>2 plan tool calls<br/>3 narrate results — grounded<br/>4 refuse honestly when no tool answers"]
        GG["Groundedness gate<br/>deterministic scan: every id in the answer<br/>must exist in the tool results"]
        PROV["providers.py — one neutral format<br/>Claude (anthropic SDK) ⇄ Sarvam (stdlib HTTP)<br/>switched by one .env line"]
        AG --- GG
        AG --- PROV
    end

    UI <--> AG

    AG <==>|"tool-call boundary — 19 typed tools, JSON in/out<br/>THE LLM ↔ DETERMINISTIC LINE"| T

    subgraph ENG["Deterministic engine — pure Python, zero LLM dependency"]
        T["tools.py — every response carries<br/>sources + trace; bad input → ok:false + hint"]
        Q["QUERY (Tier 1)<br/>crew · flights · duty clocks<br/>reserves · certs · risk · watchlist"]
        S["SIMULATION (Tier 2)<br/>sick crew · station closure · delay<br/>cert expiry · cancellation<br/>copy-on-write what-if overlays"]
        R["RECOMMENDER (Tier 3)<br/>enumerate → 7-rule filter → cost → rank<br/>joint plans · delay recovery · notifications"]
        RU["RULES ENGINE — rules.py<br/>7 pure functions, one per RULE-*<br/>every check emits verdict + arithmetic trace"]
        W["WORLD STATE — world.py<br/>10 JSON files loaded once → indexes<br/>28-day duty grids for rolling windows"]
        T --> Q & S & R
        S --> RU
        R --> RU
        Q --> W
        RU --> W
        S --> W
        R --> W
    end
```

**The LLM vs. deterministic boundary is the tool-call interface** — everything
above it is language, everything below it is arithmetic. This is the boundary
the evaluation criteria ask us to draw deliberately.

### What one question looks like end to end (Tier 3, the flagship scenario)

```mermaid
sequenceDiagram
    actor Ctrl as Controller
    participant LLM as LLM (Claude / Sarvam)
    participant T as Tool boundary
    participant E as Engine

    Ctrl->>LLM: "Captain C-1042 just called in sick — what should I do?"
    LLM->>T: simulate_sick_crew(crew_id=C-1042, date=2026-09-15)
    T->>E: overlay world − C-1042
    E-->>LLM: uncrewed DX412/413/588, P-2291 broken, 486 pax + trace
    LLM->>T: recommend_cover(pairing=P-2291, role=Captain)
    T->>E: enumerate → 7-rule check each → cost → rank
    E-->>LLM: #1 reserve C-3310 ₹18,500 legal · #2 deadhead C-2210 ₹41,200 · … + all 7 verdicts each + trace
    LLM->>LLM: draft answer from tool JSON only
    LLM->>T: groundedness gate (deterministic)
    T-->>Ctrl: ranked options + legality badges + costs + "Show reasoning" trace
```

---

## 3. Requirements coverage — what was asked vs. what the repo has

### The three tiers

| Tier | Asked | Status in repo |
|---|---|---|
| **Tier 1 — Lookup & Retrieval** (mandatory) | Reserves, duty hours, departures, expiring licences | ✅ 8 query tools (`crew_ops/query.py`) — all 16 Tier-1 answer keys pass, LLM eval 16/16 PASS |
| **Tier 2 — Consequence & Simulation** (strongly expected) | Sick calls, move-crew legality, station closures | ✅ Simulation engine + overlays (`crew_ops/simulation.py`), matches the spec's exact Tier-2 output shape |
| **Tier 3 — Recommendation & Action** (stretch) | Ranked, legal, costed options + reasoning; bonus: draft the crew notification | ✅ Recommender (`crew_ops/recommender.py`) incl. joint multi-sick plans, delay recovery, and `draft_notification` (bonus done) |

### Mandatory constraints

| Constraint | How it's met |
|---|---|
| Provided synthetic dataset only | World state loads exclusively from `data/*.json` |
| Natural language as primary interface | Web chat + CLI `ask`/`chat`; multi-turn with context retention |
| Non-trivial answers explainable | Trace is a **data structure generated by the computing code** — rule-by-rule arithmetic with source files, rendered under "Show reasoning". It cannot drift from the answer. |
| Answers grounded — invented facts are failures | Deterministic groundedness gate over every final answer |

### Optional enhancements delivered

Multi-turn conversation ✅ · drafting crew notifications ✅ · chained/simultaneous
disruptions ✅ (`recommend_joint`, overlay stacking) · proactive alerting ✅
(`get_duty_watchlist` early-warning list) · confidence signalling ✅ (sources +
rules-checked strip; unverified-id flags).

### Deliverables checklist

| Deliverable | Where |
|---|---|
| Source code repository | this repo, `solution/` |
| Architecture diagram incl. the LLM/deterministic boundary | this file + `solution/ARCHITECTURE.md` |
| README with setup, approach, trade-offs | `solution/README.md` |
| Sample inputs/outputs incl. a failure case with analysis | README "Known limitations" + eval transcripts in `solution/llm_eval_out/` |
| Presentation deck + live demo | this doc is the deck source; demo = `python3 server.py` |

---

## 4. The deterministic engine — why the numbers are right

- **7 rules, 7 pure functions** (`rules.py`), each returning
  `{rule_id, pass, computed, limit, margin, detail}`. `evaluate_cover` always
  runs **all 7** — so a legal option shows *what was checked*, not just an
  illegal one showing *why it failed* (exactly the `rules_checked` field the
  spec's Tier-3 output shape requires).
- **Calendar-window sums recomputed from the 28-day daily grid plus the proposed
  duty** — never the pre-baked `duty_hours_7d` snapshot, which is stale for any
  future date. This is the dataset's main correctness trap and it's encoded once.
- **Copy-on-write overlays** for what-ifs: a simulation layers a disruption delta
  over the base world — scenarios never contaminate each other, and chained
  disruptions are just a stack of overlays.
- Domain subtleties found by dataset archaeology and encoded: reserve on-call
  windows gate the *required report time* (the C-3305 day-2 trap), whole-duty
  shift vs. pre-duty delay are different FDP situations (S4), deadhead
  DEL→BLR rides real schedule legs with +15 min report, cancellation is always
  priced as an option so the ranking *shows* it losing.

---

## 5. Verification — how we know it's right

Two independent layers of evidence:

```mermaid
flowchart LR
    subgraph L1["Layer 1 — Engine correctness (no LLM)"]
        RG["run_regression.py<br/>all 38 questions + 6 scenarios<br/>diffed vs the dataset's own answer keys"]
        PT["121 pytest tests<br/>incl. the engineered traps:<br/>C-2087 breach = exactly 1h20m<br/>C-3310 = ₹18,500 · C-2210 = ₹41,200"]
    end
    subgraph L2["Layer 2 — Live LLM eval (end to end)"]
        EV["run_llm_eval.py / web Eval tab<br/>real model answers auto-graded<br/>against answer-key fact atoms"]
    end
    RG --> V["41/41 answer-key checks PASS"]
    PT --> V
    EV --> V2["29 PASS · 12 PARTIAL · 3 MANUAL<br/>0 wrong answers, 0 errors"]
```

### Engine regression: **41/41**

Every auto-checkable answer key passes: all 16 Tier-1, 13/14 Tier-2, 6/8 Tier-3
(the 3 open-ended prose questions Q30/Q36/Q38 are flagged for human judging,
never auto-passed), and all 6 scenarios S1–S6. Because held-out scenarios reuse
the same event vocabulary, passing via a **general engine** — not answer-key
lookup — is the generalisation story.

### Live LLM eval (provider: `sarvam-105b`, full 44-item run)

| | PASS | PARTIAL | MANUAL | Wrong / Error |
|---|---|---|---|---|
| Tier 1 (16) | **16** | – | – | 0 |
| Tier 2 (14) | 10 | 3 | 1 | 0 |
| Tier 3 (8) | 3 | 3 | 2 | 0 |
| Scenarios (6) | – | 6 | – | 0 |
| **Total (44)** | **29** | **12** | **3** | **0** |

**How to read PARTIAL — this matters for the jury.** Grading is strict
atom-matching: the answer text must literally contain every fact atom of the
answer key. The PARTIALs are answers that are *correct but less exhaustive than
the key* — e.g. Q17 named all uncrewed flights but didn't restate "486
passengers"; the scenario keys list every ranked option's cost, while a good
conversational answer leads with the winner. The engine returned all those
numbers (verifiable in the saved transcripts); the narration just didn't recite
all of them. **No answer contained a wrong number and no invented facts got
through the gate** — which is the failure mode the scoring principles actually
penalise ("correctness outweighs coverage").

**Performance:** median **14 s** per answer, average 21 s, worst case 92 s on the
heaviest multi-tool scenario (engine time is <50 ms — the latency is model
round-trips). Well inside "usable on a live shift"; the worst case is our
documented tail, not the norm.

MANUAL = the three open-ended prose questions — the system produces grounded
drafts but refuses to pretend prose can be auto-verified.

Full transcripts: `solution/llm_eval_out/results.json` (also browsable in the
web UI's **Eval** tab, which can re-run the whole eval live).

### The Eval tab, live

![Eval tab mid-run: progress bar, PASS/PARTIAL/MANUAL/ERROR counters and atom coverage, with Tier-1 rows passing](screenshots/image_1.png)

*A full eval re-running live inside the web UI — per-item status, atoms
found, tool-call count, response time, and a transcript behind every
`answer` button.*

![Eval tab bottom rows: Tier-3 questions and scenarios, including MANUAL and ERROR rows](screenshots/image_2.png)

*The strict grading in action on a live re-run: MANUAL rows (0/0 atoms) are
the open-ended prose questions deliberately flagged for human judging, and
ERROR means the provider API call itself failed mid-run — no answer was
produced, so the grader refuses to score it. (The result table above quotes
the saved full run in `llm_eval_out/results.json`, which completed with zero
errors; live re-runs vary with the provider's API.)*

---

## 6. Honest failure analysis (asked for explicitly — and rewarded)

1. **Entity resolution is the soft spot.** "The VT-DXE captain", "tomorrow" —
   resolution is the LLM's job. Mitigations: tools accept only canonical
   ids/dates so a bad resolution fails loudly (`ok: false` + hint), and resolved
   entities are echoed back ("Assuming you mean C-1042…") for the controller to
   catch. This is our documented failure case.
2. **Narration under-reports** (the PARTIALs above): correct but not exhaustive.
   Fixable with a "recite all ranked options" instruction at the cost of
   verbosity — a deliberate UX trade-off we can defend.
3. **Rest before a first cover duty** is only checkable via `last_rest_ended`
   (the daily history has no per-duty timestamps) — documented, with the dataset
   change that would make it exact.
4. **RULE-FLT-03 on covers** is checked *stricter* than the answer keys require
   (we count the cover's block hours into the 28-day window). On this dataset
   they never diverge; ours is the safer regulatory reading.
5. **Joint plans are exhaustive, not optimal** — fine at 2–3 simultaneous
   events; at real scale this becomes CP/MIP behind the same tool interface.
6. **Claude vs. Sarvam:** the full live eval ran on Sarvam; the Claude path is
   implemented and unit-tested (fake provider, both wire formats) but the graded
   run shown above is Sarvam's.

---

## 7. Scale & production notes (commentary, per the brief)

- **Scale:** at real-airline size (10⁴ crew, 10³ daily legs) the in-memory world
  moves to Postgres + an incremental legality cache keyed by (crew, date); the
  rules engine, trace format and tool boundary are unchanged — **the boundary is
  the durable design, not the storage**. The recommender graduates to CP/MIP
  behind the same tool.
- **PII:** the boundary helps here too — sensitive fields (phone-level
  reachability, medical data) simply never enter the prompt; the LLM sees crew
  ids. Tool calls are the audit log; the trace doubles as the audit record.

---

## 8. Demo script (5 minutes)

1. `python3 server.py` → **Chat** tab: a Tier-1 warm-up ("Who's on reserve at
   BLR tomorrow?") — instant, sourced.
2. The flagship: *"Captain C-1042 just called in sick for tomorrow — what should
   I do?"* — watch tool chips stream, ranked options with legality badges and
   itemized costs appear, expand **Show reasoning** and challenge one line of
   arithmetic.
3. Follow-up in the same thread: *"What about C-2210 instead?"* — multi-turn
   context + the deadhead cost story.
4. An out-of-scope question → honest refusal, live.
5. **Eval** tab: show the scoreboard the judges just read, being re-computed.

---

*The LLM is the interface, the engine is the authority, the trace is the
contract between them — and when the system isn't sure, it says so.*


---

## Final Pitch to Jury

CREW OPS ADVISOR — 5-8 MINUTE PITCH SCRIPT
(~900 words. Speak normally, that's about 7 minutes. Sections marked so you
can cut [OPTIONAL] parts if running out of time.)

------------------------------------------------------------
1. THE PROBLEM  (~45 seconds)
------------------------------------------------------------

When a disruption hits an airline — a captain calls in sick at 5 a.m. — a
crew controller has to work out, in minutes: which flights are now
uncovered, which reserve crew can legally take them, and what each option
costs. Today that means cross-referencing rosters, duty clocks, reserve
lists, and a regulatory rulebook across several screens. Only senior
controllers can do it fluently, and there is no reasoning trail behind
their decisions.

We built the Crew Ops Advisor: you ask a question in plain English, and it
answers correctly, fast, with reasoning you can inspect — and when it
can't answer reliably, it says so.

------------------------------------------------------------
2. THE CORE DECISION  (~1 minute)
------------------------------------------------------------

The problem statement asks one architectural question: what should the
language model do, and what should deterministic code do?

Our answer is one hard rule:

  The LLM never computes a number. Deterministic code never interprets
  language.

The LLM does exactly three things: it understands the question, it plans
which tools to call, and it explains the results in plain language.

Every number — every duty hour, every cost, every legality verdict — comes
from a deterministic Python engine. Why? Because legality is exact
arithmetic. If an LLM estimates a duty-hour total and is off by one hour
twenty minutes, that's not a rounding error — that's a regulatory
violation. So we never let it estimate. The same question gives the same
answer, every single time.

------------------------------------------------------------
3. HOW IT WORKS  (~1.5 minutes)
------------------------------------------------------------

The system has two halves, joined by a tool-call boundary.

Above the boundary: the AI layer. A chat interface — web and CLI — and an
LLM that has 19 typed tools. The layer is provider-agnostic: we run Claude
or Sarvam, switched by one line in a config file.

Below the boundary: the deterministic engine, pure Python, covering all
three tiers of the challenge.

Tier 1 — lookups: crew, flights, duty clocks, reserves, certifications.

Tier 2 — simulation: a crew member drops out, a station closes, a flight
is delayed. We use copy-on-write overlays — a what-if scenario is layered
over the real world state without touching it, so scenarios never
contaminate each other, and chained disruptions just stack.

Tier 3 — recommendations: enumerate every candidate — reserves, day-off
crew, deadheads, even cancellation — run every one through all seven
legality rules, cost each from the cost tables, and rank them. Every
option comes back with its legality verdict, itemized cost, and reasoning.
We also do the bonus: it drafts the notification message to the crew.

At the heart is the rules engine: seven pure functions, one per rule.
Every check returns not just pass or fail, but the actual arithmetic — the
window, the hours, the limit, the margin.

------------------------------------------------------------
4. EXPLAINABILITY AND TRUST  (~1 minute)
------------------------------------------------------------

Explainability is mandatory in this challenge, so we made it a data
structure, not prose. Every engine response carries a trace: step by step,
which source file, which numbers, which computation. The trace is
generated by the same code that did the calculation — so it can never
drift from the answer. In the UI, every answer has a "Show reasoning"
expander; a controller can challenge any line.

And we guard against hallucination mechanically. A deterministic
groundedness gate scans the LLM's final answer: any crew ID, flight
number, or pairing that doesn't appear in the tool results gets flagged as
unverified. Invented facts are caught by code, not by hope.

If no tool can answer the question, the system refuses honestly: "I can't
answer that reliably from this data" — because the scoring principle says
correctness outweighs coverage, and we agree.

------------------------------------------------------------
5. HOW WE KNOW IT'S RIGHT  (~1.5 minutes)
------------------------------------------------------------

Two layers of proof.

First, the engine alone. The dataset ships its own answer keys — we made
them our test suite. All 41 auto-checkable answer keys pass: every Tier 1
question, the Tier 2 and Tier 3 questions, and all six disruption
scenarios. Plus 121 unit tests pinned to the dataset's engineered traps —
for example, C-2087 breaching the 7-day duty limit by exactly one hour
twenty minutes. And because it's a general engine, not answer-key lookup,
held-out scenarios using the same event types should work too.

Second, the full live end-to-end eval — real model, real questions, all 44
items, auto-graded. Results: 29 full passes, 12 partials, 3 manual, and —
the number that matters — zero wrong answers and zero errors. Tier 1 was a
perfect 16 out of 16.

What does "partial" mean? The grading is strict: the answer text must
contain every fact from the answer key. Our partials were answers that
were correct but not exhaustive — for example, naming all the uncovered
flights but not restating the passenger count. The engine had every
number; the narration just didn't recite them all. Not one answer
contained a wrong number.

Performance: median 14 seconds per answer. The engine itself computes in
under 50 milliseconds — the latency is model round-trips. Usable on a live
shift.

------------------------------------------------------------
6. HONEST LIMITATIONS  (~45 seconds)
------------------------------------------------------------

Three things we'll say before you ask.

One — entity resolution is the soft spot. If you say "the captain on that
Delhi flight", the LLM resolves it, and it can get that wrong. Our
mitigation: tools only accept canonical IDs, so a bad resolution fails
loudly, and the answer echoes back who it assumed you meant.

Two — the recommender is a transparent ranker, not an optimizer. At this
scale we can check everything exhaustively; at real airline scale this
becomes a solver behind the same tool interface.

Three — our full graded eval ran on Sarvam; the Claude path is built and
unit-tested, but the numbers I quoted are Sarvam's.

------------------------------------------------------------
7. CLOSE  (~30 seconds)
------------------------------------------------------------

At real scale, the storage changes — the boundary doesn't. That's the
durable design. And the boundary helps with privacy too: sensitive crew
data simply never enters the prompt.

One sentence to remember: the LLM is the interface, the engine is the
authority, and the trace is the contract between them. And when the system
isn't sure — it says so.

Thank you. Happy to show it live.

------------------------------------------------------------
[OPTIONAL] IF YOU HAVE TIME FOR A LIVE DEMO (2 minutes)
------------------------------------------------------------

Say: "Let me show you the bad-day scenario."

Type: "Captain C-1042 just called in sick for tomorrow — what should I do?"

Point out, in order:
  1. Tool calls streaming in live as chips.
  2. Ranked options: reserve C-3310 at 18,500 rupees, fully legal, versus
     a deadhead at 41,200 — with legality badges and itemized costs.
  3. Expand "Show reasoning" — the actual arithmetic, rule by rule.
  4. Ask a follow-up: "What about C-2210 instead?" — multi-turn context.
