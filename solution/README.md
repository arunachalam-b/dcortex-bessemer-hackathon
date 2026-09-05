# Crew Ops Advisor — Deterministic Engine

Implementation of the architecture in [ARCHITECTURE.md](ARCHITECTURE.md):
everything **below** the LLM boundary is built and verified. The LLM adapter is
deliberately not wired yet (provider TBD at the venue) — it plugs into one
file, `crew_ops/tools.py`, with zero changes elsewhere.

## Status

- **41/41** automated checks against the dataset's own answer keys pass:
  all 16 Tier-1, all 14 Tier-2 minus 1 open-ended, all 8 Tier-3 minus 2
  open-ended questions, and all 6 scenarios (S1–S6). The 3 open-ended prose
  questions (Q30/Q36/Q38) are flagged for human judging, never auto-passed.
- **107 pytest tests** green (`python3 -m pytest tests/`), runtime < 1 s.
- No dependencies beyond Python 3.9+ stdlib (pytest for the test suite only).

## Run it

```bash
cd solution
python3 run_regression.py           # scoreboard vs questions.json + scenarios.json
python3 -m pytest tests/ -q         # full test suite
python3 cli.py demo                 # walk the flagship S2 sick-captain disruption
python3 cli.py tools                # list the LLM-facing tools
python3 cli.py call recommend_cover \
    '{"pairing_id": "P-2291", "role": "Captain", "sick_crew_id": "C-1042"}'
python3 cli.py repl                 # interactive tool shell
```

The dataset directory is auto-discovered (any `**/data/flights.json` under the
repo); override with `CREW_OPS_DATA=/path/to/data`.

## Layout

| File | What it is |
|---|---|
| `crew_ops/world.py` | Dataset loader, indexes, calendar-window sums, duty conventions |
| `crew_ops/rules.py` | The 7 rules as pure checks; `evaluate_cover` = full legality with per-rule verdicts + arithmetic trace |
| `crew_ops/query.py` | Tier 1 — lookups (crew, flights, clocks, reserves, certs, risk, pairings, watchlist) |
| `crew_ops/simulation.py` | Tier 2 — sick crew, station closure, delay, cert expiry, rest, cancellation; never mutates the world |
| `crew_ops/recommender.py` | Tier 3 — enumerate → 7-rule filter → cost → rank; joint plans; delay recovery; notification facts |
| `crew_ops/tools.py` | **The LLM boundary**: 19 typed tools, JSON in/out, every response carries `sources` + `trace`; bad input → honest refusal, not an exception |
| `crew_ops/regression.py` | Maps all 38 questions + 6 scenarios to engine calls and diffs against the answer keys |
| `cli.py` | Demo / tool shell (no LLM needed) |
| `run_regression.py` | Scoreboard |
| `tests/` | Unit tests pinned to the engineered facts + full answer-key regression |

## Where the LLM plugs in

An adapter for any provider needs only:

1. `tools.tool_schemas()` → hand to the model as its tool definitions
   (already JSON-schema shaped).
2. On every tool call: `tools.dispatch(world, name, args)` → return the JSON
   to the model.
3. System prompt: snapshot "now" is `2026-09-14T18:00:00Z`; instruct the model
   to resolve names/dates to ids, call tools for **every** fact, narrate only
   values present in tool results, and refuse when no tool answers.
4. Optional groundedness gate: scan the drafted answer for crew ids, flight
   numbers, hours and ₹ amounts; verify each appears in the collected tool
   results before showing it.

Until then, `cli.py` exercises the identical boundary by hand.

## Domain subtleties the engine encodes (found in dataset archaeology)

- **Window sums** = `daily_history` (actuals through 14 Sep) **plus** rostered
  duties in the window — the stored `duty_hours_7d` is only valid as-of the
  snapshot; legality on any later date must be recomputed (this is what
  `validate.py` checks, and what Q26 requires).
- **A whole-duty shift** (deadhead positioning, late start) moves report *and*
  release → FDP length unchanged; a **pre-duty delay** with fixed report
  extends the duty → FDP-01 breach territory (S4). Two different simulations.
- **Reserve windows** gate the *required report time* (after any deadhead),
  not the callout time; once activated a reserve is line crew — so a multi-day
  cover is checked on every day (the C-3305 day-2 trap).
- **Deadhead DEL→BLR** rides DX589 (even dates, arr 07:45Z) or DX402 (odd
  dates, arr 08:45Z); new report = arrival + 15 min; the induced departure
  delay is costed per hour.
- **Cancellation is always priced as an option**, never assumed — the ranking
  shows it losing on cost, which is exactly the explanation a controller needs.

## Known limitations (honest-failure section)

1. **Rest before the first cover duty** is only checkable via
   `last_rest_ended` (daily history has no report/release times). For crew
   whose own rostered duty precedes the cover this is self-referential, so the
   check applies only when the cover starts the sequence. A dataset with
   per-duty timestamps in history would make this exact.
2. **RULE-FLT-03 on covers**: we count the cover's block hours into the 28-day
   window (stricter than the answer keys, which only guard the base roster).
   On this dataset the two never diverge; on tighter data ours is the safer
   reading of the rule.
3. **Joint plans** are exhaustive over per-pairing legal options — fine at 2–3
   simultaneous events; at real scale this becomes CP/MIP behind the same tool.
4. **Open-ended questions** (Q30/Q36/Q38) produce grounded drafts but are
   flagged `MANUAL` — the engine does not pretend prose can be auto-verified.
5. **Entity resolution** ("the VT-DXE captain", "tomorrow") is the LLM
   adapter's job and its main risk; the tools accept only canonical ids/dates
   so a bad resolution fails loudly (`ok: false` + hint), never silently.
