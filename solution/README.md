# Crew Ops Advisor

Implementation of the architecture in [ARCHITECTURE.md](ARCHITECTURE.md):
a deterministic engine below the tool boundary, and a provider-agnostic AI
layer above it. The LLM provider (**Claude** or **Sarvam**) is a `.env`
switch, not a code change.

## Status

- **41/41** automated checks against the dataset's own answer keys pass:
  all 16 Tier-1, all 14 Tier-2 minus 1 open-ended, all 8 Tier-3 minus 2
  open-ended questions, and all 6 scenarios (S1–S6). The 3 open-ended prose
  questions (Q30/Q36/Q38) are flagged for human judging, never auto-passed.
- **121 pytest tests** green (`python3 -m pytest tests/`), runtime < 1 s —
  including the AI layer (config, both wire formats, advisor loop,
  groundedness gate), all offline via a fake provider.
- Engine + Sarvam path: Python 3.9+ stdlib only. Claude path additionally
  needs `pip install anthropic`. (pytest for the test suite only.)

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

### The AI advisor

```bash
cp .env.example .env                # then fill in one API key
python3 cli.py ask "Captain C-1042 just called in sick — who covers P-2291?"
python3 cli.py chat                 # multi-turn session (follow-ups keep context)
```

Switch providers by editing one line in `.env` — `LLM_PROVIDER=claude` or
`LLM_PROVIDER=sarvam` — or per run, since real env vars override the file:

```bash
LLM_PROVIDER=sarvam python3 cli.py ask "Which reserves are on call at BLR tomorrow?"
```

| `.env` key | Meaning | Default |
|---|---|---|
| `LLM_PROVIDER` | `claude` or `sarvam` | `claude` |
| `ANTHROPIC_API_KEY` / `SARVAM_API_KEY` | key for the chosen provider | — |
| `CLAUDE_MODEL` / `SARVAM_MODEL` | model override | `claude-opus-5` / `sarvam-105b` |
| `CLAUDE_FALLBACKS` | server-side refusal fallback (`0` to disable) | `1` |
| `SARVAM_REASONING_EFFORT` | `low` / `medium` / `high` | provider default |
| `LLM_MAX_TOKENS`, `LLM_MAX_STEPS` | response cap, tool-call budget per question | 16000/4096, 16 |

Troubleshooting: a Claude "cannot reach the Claude API … Decompressor.decompress()
… output_buffer_limit" error means the environment ships an old `brotlicffi`
(Anaconda base does) — fix with `pip install -U brotlicffi`.

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
| `crew_ops/llm/` | **The AI layer**: `config.py` (.env + provider selection), `providers.py` (Claude via the `anthropic` SDK, Sarvam via stdlib HTTP, one neutral format), `agent.py` (advisor loop + groundedness gate) |
| `crew_ops/regression.py` | Maps all 38 questions + 6 scenarios to engine calls and diffs against the answer keys |
| `cli.py` | Demo / tool shell (no LLM needed) + `ask`/`chat` advisor commands |
| `run_regression.py` | Scoreboard |
| `tests/` | Unit tests pinned to the engineered facts + full answer-key regression |

## How the AI layer works

`crew_ops/llm/agent.py` implements the adapter recipe end to end, once, for
any provider:

1. `tools.tool_schemas()` are handed to the model as its tool definitions;
   every tool call the model makes is routed through
   `tools.dispatch(world, name, args)` and the JSON returned verbatim.
2. The system prompt pins snapshot "now" = `2026-09-14T18:00:00Z`, requires
   entity resolution to canonical ids (echoed back for the controller to
   verify), forbids the model computing any number itself, and mandates
   honest refusal when no tool answers.
3. A deterministic **groundedness gate** scans the final answer for crew ids,
   pairing ids, flight numbers and registrations; any id absent from the
   collected tool results (and the controller's own question) is flagged as
   unverified in the shown answer.

Providers plug in behind one interface (`crew_ops/llm/providers.py`): the
advisor speaks a neutral conversation format, and each provider translates
to its wire format — Anthropic content blocks for Claude (thinking/tool_use
blocks echoed back verbatim), OpenAI-style chat completions for Sarvam.
Adding a third provider is one subclass with two translation functions;
the agent loop, grounding and CLI are untouched.

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
