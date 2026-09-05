# Eval Catalog — Crew Ops Advisor

> Auto-generated from `questions.json`, `scenarios.json`, `crew_ops/regression.py`, `crew_ops/tools.py`, `run_llm_eval.py` and the recorded run in `llm_eval_out/results_run1.json`. Dataset: `DCortex - Synthetic dataset/data/`.

## How the evals work

The repo has **two eval harnesses** over the same 44 items (38 questions Q01–Q38 + 6 scenarios S1–S6):

| Harness | What it tests | Grading | Command |
|---|---|---|---|
| `run_regression.py` | The deterministic engine (`crew_ops/query.py`, `simulation.py`, `recommender.py`) replayed against the shipped answer keys | Structural diff (`crew_ops/regression.py:compare`) — every expected fact must match; numbers within ±0.011; lists match ordered then as multisets; prose keys (`note`, `explanation`, `narrative`, `consequence`) ignored | `python3 run_regression.py [-v]` |
| `run_llm_eval.py` | The live LLM advisor end-to-end (natural-language prompt → tool-calling agent → prose answer) | **Atom grading** — the answer key is reduced to its essential atoms (ids, rule ids, timestamps, non-zero numbers) and each must literally appear in the prose answer (commas stripped) | `python3 run_llm_eval.py [Q01 Q05 S2 ...]` |

### Atom grading (`run_llm_eval.py`)

- An **atom** is: any id matching `C-\d{3,5} | P-\d{3,5} | DX\d{2,4} | VT-[A-Z]{3} | RULE-[A-Z]+-\d{2}`, the date and hh:mm parts of any ISO timestamp, or any **non-zero** number in the answer key.
- Keys skipped when extracting atoms: `rules_checked`, `explanation`, `note`, `rank`, `rules_ref`, `action`, `reasoning`, `must_include`, `suggested` (boilerplate/prose the LLM words differently). Booleans and zero values are not graded.
- Statuses: **PASS** (all atoms found), **PARTIAL** (some missing), **MANUAL** (Q30, Q36, Q38 — open-ended, human-judged), **ERROR** (provider failure).
- Each item runs with a **fresh advisor context**; results stream to `llm_eval_out/progress.log` + `llm_eval_out/results.json` and are also recorded in the SQLite run history (`crew_ops.db`) shared with the web UI.
- A scenario prompt is the event `narrative` plus a fixed instruction asking for ranked options with INR costs and delay hours, a recommended choice, rule reasons for excluded candidates, and per-flight assessments.

### Tools available to the LLM advisor

The advisor (`crew_ops/llm/agent.py`) answers **only** through these tools (`crew_ops/tools.py`); a groundedness gate flags any dataset-shaped fact not backed by a tool result:

| Tool | Description |
|---|---|
| `lookup_crew` | Find crew by id/name/rank/base/status/rating. |
| `lookup_flights` | Filter the flight schedule. |
| `get_duty_clock` | Rolling 7d duty / 28d flight-hour windows for a crew member ending a given date (daily history + rostered duties), with headroom. |
| `get_reserves` | Reserve pool with on-call windows, filtered by base/date. |
| `get_certifications` | Certifications, optionally for one crew member or expiring in a window. |
| `get_risk_signals` | Pre-computed disruption-risk scores (provided input). |
| `get_pairing` | Pairings with days, flights, report/release and crew. |
| `get_duty_watchlist` | Crew at/above a 7-day duty-hour threshold (early-warning list). |
| `simulate_sick_crew` | Impact of a crew member dropping out: uncovered flights (all remaining days of the pairing), passengers, broken pairing. |
| `simulate_station_closure` | Flights hit by a station closure window plus per-flight delay/FDP assessment. |
| `simulate_delay` | A pre-duty delay shifts all legs: does the rostered crew's FDP hold, and how many legs can they legally fly? |
| `check_certification_validity` | Is a crew member legal to operate on a date (RULE-CERT-06)? |
| `check_assignment_legality` | Full 7-rule check: can this crew member cover this pairing (optionally from a date, with a delay)? Returns verdicts, issues and arithmetic trace. |
| `compute_rest_requirement` | Earliest legal next report after a release (RULE-REST-04). |
| `cancellation_impact` | Passengers affected and direct cost of cancelling a leg. |
| `recommend_cover` | Ranked, rule-checked, costed options to cover a role on a pairing, with every rejected candidate and the rule that killed them. |
| `recommend_joint` | Optimal joint plan for simultaneous disruptions (no crew member used twice; total cost minimised). |
| `recommend_delay_recovery` | Recovery for a delay that breaches FDP: split the duty at the longest legal prefix, re-crew or cancel the tail, ranked by cost. |
| `draft_notification` | Structured callout facts + plain-text message for a chosen cover. |

### Recorded reference run

The per-item "Last recorded LLM run" lines below come from `llm_eval_out/results_run1.json`: provider **sarvam** (model `sarvam-105b`), all 44 items. Summary: 29 PASS, 12 PARTIAL, 3 MANUAL, 55.9% atom coverage on auto-graded items (`llm_eval_out/final_summary.txt`).

---

## Questions (Q01–Q38)

### Tier 1 — direct lookups

#### Q01

**Prompt:** Who is on reserve at BLR on 2026-09-15, and what are their on-call windows?

**Description:** Read directly from reserve_pool.json filtered to base BLR (all reserves are active all week).

**Engine mapping** (`crew_ops/regression.py`):

```python
lambda w: [_project(r, ["crew_id", "rank", "window"])
    for r in Q.reserves(w, base="BLR", on=date(2026, 9, 15))]
```

**Graded atoms (12):** `C-1329`, `C-2111`, `C-2248`, `C-3305`, `C-3310`, `C-3311`, `C-3312`, `C-3315`, `C-3316`, `C-3677`, `C-4809`, `C-5418`

<details><summary>Expected answer (answer key)</summary>

```json
[
 {
  "crew_id": "C-3305",
  "rank": "Captain",
  "window": {
   "start": "00:00",
   "end": "05:30"
  }
 },
 {
  "crew_id": "C-3310",
  "rank": "Captain",
  "window": {
   "start": "06:00",
   "end": "18:00"
  }
 },
 {
  "crew_id": "C-3311",
  "rank": "First Officer",
  "window": {
   "start": "06:00",
   "end": "18:00"
  }
 },
 {
  "crew_id": "C-3312",
  "rank": "First Officer",
  "window": {
   "start": "00:00",
   "end": "12:00"
  }
 },
 {
  "crew_id": "C-3315",
  "rank": "Captain",
  "window": {
   "start": "03:00",
   "end": "15:00"
  }
 },
 {
  "crew_id": "C-3316",
  "rank": "First Officer",
  "window": {
   "start": "03:00",
   "end": "15:00"
  }
 },
 {
  "crew_id": "C-2111",
  "rank": "Senior Cabin Crew",
  "window": {
   "start": "04:00",
   "end": "16:00"
  }
 },
 {
  "crew_id": "C-3677",
  "rank": "Senior Cabin Crew",
  "window": {
   "start": "04:00",
   "end": "16:00"
  }
 },
 {
  "crew_id": "C-5418",
  "rank": "Cabin Crew",
  "window": {
   "start": "04:00",
   "end": "16:00"
  }
 },
 {
  "crew_id": "C-1329",
  "rank": "Cabin Crew",
  "window": {
   "start": "04:00",
   "end": "16:00"
  }
 },
 {
  "crew_id": "C-2248",
  "rank": "Cabin Crew",
  "window": {
   "start": "04:00",
   "end": "16:00"
  }
 },
 {
  "crew_id": "C-4809",
  "rank": "Cabin Crew",
  "window": {
   "start": "00:00",
   "end": "12:00"
  }
 }
]
```

</details>

**Last recorded LLM run:** **PASS** — 12/12 atoms, 1 tool call(s), 12.2s

#### Q02

**Prompt:** As of the snapshot, how many duty hours has C-1042 accrued in the 7 calendar days ending 2026-09-14, and how much headroom does that leave under RULE-DUTY-02?

**Description:** Sum daily_history for Sep 8–14 (duty_clocks.json); headroom = 60 − that sum.

**Rules referenced:** `RULE-DUTY-02`

**Engine mapping** (`crew_ops/regression.py`):

```python
lambda w: (lambda c: {"duty_hours_7d": c["duty_hours_7d"],
                             "headroom_hours": c["duty_headroom_7d"]})(
    Q.duty_clock(w, "C-1042", date(2026, 9, 14)))
```

**Graded atoms (2):** `20.93`, `39.07`

<details><summary>Expected answer (answer key)</summary>

```json
{
 "duty_hours_7d": 20.93,
 "headroom_hours": 39.07
}
```

</details>

**Last recorded LLM run:** **PASS** — 2/2 atoms, 1 tool call(s), 4.9s

#### Q03

**Prompt:** Which flights depart DEL on 2026-09-15?

**Description:** Filter flights.json by date and dep_station. (DX589 runs only on VT-DXC's DEL-start days: 14/16/18/20 Sep.)

**Engine mapping** (`crew_ops/regression.py`):

```python
lambda w: [f["flight_no"] for f in
    Q.lookup_flights(w, on=date(2026, 9, 15), dep_station="DEL")]
```

**Graded atoms (1):** `DX402`

<details><summary>Expected answer (answer key)</summary>

```json
[
 "DX402"
]
```

</details>

**Last recorded LLM run:** **PASS** — 1/1 atoms, 1 tool call(s), 3.7s

#### Q04

**Prompt:** List all certifications expiring within 30 days of 2026-09-15.

**Description:** Filter certifications.json on valid_to between 2026-09-15 and 2026-10-15.

**Rules referenced:** `RULE-CERT-06`

**Engine mapping** (`crew_ops/regression.py`):

```python
lambda w: Q.certifications(w, expiring_from=date(2026, 9, 15),
    expiring_to=date(2026, 10, 15))
```

**Graded atoms (6):** `C-2087`, `C-2091`, `C-2993`, `C-3116`, `C-5020`, `C-5417`

<details><summary>Expected answer (answer key)</summary>

```json
[
 {
  "crew_id": "C-2087",
  "cert_type": "licence",
  "valid_to": "2026-09-18"
 },
 {
  "crew_id": "C-2091",
  "cert_type": "medical_class1",
  "valid_to": "2026-09-23"
 },
 {
  "crew_id": "C-5417",
  "cert_type": "recurrent_training",
  "valid_to": "2026-09-17"
 },
 {
  "crew_id": "C-3116",
  "cert_type": "dangerous_goods",
  "valid_to": "2026-09-28"
 },
 {
  "crew_id": "C-5020",
  "cert_type": "recurrent_training",
  "valid_to": "2026-10-03"
 },
 {
  "crew_id": "C-2993",
  "cert_type": "medical_class1",
  "valid_to": "2026-10-08"
 }
]
```

</details>

**Last recorded LLM run:** **PASS** — 6/6 atoms, 1 tool call(s), 4.5s

#### Q05

**Prompt:** Which aircraft operates DX412 on 2026-09-15, and how many seats does it have?

**Description:** Lookup in flights.json.

**Engine mapping** (`crew_ops/regression.py`):

```python
lambda w: _project(Q.lookup_flights(w, on=date(2026, 9, 15),
                     flight_no="DX412")[0],
    ["aircraft", "aircraft_type", "seats"])
```

**Graded atoms (2):** `VT-DXC`, `162`

<details><summary>Expected answer (answer key)</summary>

```json
{
 "aircraft": "VT-DXC",
 "aircraft_type": "A320",
 "seats": 162
}
```

</details>

**Last recorded LLM run:** **PASS** — 2/2 atoms, 1 tool call(s), 3.6s

#### Q06

**Prompt:** What is C-3310's reserve on-call window and reachability?

**Description:** Join reserve_pool.json with crew.json.

**Engine mapping** (`crew_ops/regression.py`):

```python
lambda w: (lambda r: {"window": r["window"],
                             "reachability_minutes": r["reachability_minutes"]})(
    next(x for x in Q.reserves(w) if x["crew_id"] == "C-3310"))
```

**Graded atoms (1):** `45`

<details><summary>Expected answer (answer key)</summary>

```json
{
 "window": {
  "start": "06:00",
  "end": "18:00"
 },
 "reachability_minutes": 45
}
```

</details>

**Last recorded LLM run:** **PASS** — 1/1 atoms, 2 tool call(s), 10.8s

#### Q07

**Prompt:** What is C-2210's base and rating?

**Description:** Lookup in crew.json.

**Engine mapping** (`crew_ops/regression.py`):

```python
lambda w: _project(Q.lookup_crew(w, crew_id="C-2210")[0],
    ["base", "ratings"])
```

**Graded atoms:** none (answer key holds only booleans/zero/prose — auto-PASS for the LLM eval; regression still diffs the full structure).

<details><summary>Expected answer (answer key)</summary>

```json
{
 "base": "DEL",
 "ratings": [
  "A320"
 ]
}
```

</details>

**Last recorded LLM run:** **PASS** — 0/0 atoms, 1 tool call(s), 2.1s

#### Q08

**Prompt:** Which crew are assigned to pairing P-2291, and in what roles?

**Description:** Read rosters.json, pairing P-2291.

**Engine mapping** (`crew_ops/regression.py`):

```python
lambda w: Q.pairing_info(w, pairing_id="P-2291")[0]["crew"]
```

**Graded atoms (6):** `C-1042`, `C-1694`, `C-1873`, `C-3005`, `C-4273`, `C-4395`

<details><summary>Expected answer (answer key)</summary>

```json
[
 {
  "crew_id": "C-1042",
  "role": "Captain"
 },
 {
  "crew_id": "C-1694",
  "role": "First Officer"
 },
 {
  "crew_id": "C-3005",
  "role": "Senior Cabin Crew"
 },
 {
  "crew_id": "C-4395",
  "role": "Cabin Crew"
 },
 {
  "crew_id": "C-4273",
  "role": "Cabin Crew"
 },
 {
  "crew_id": "C-1873",
  "role": "Cabin Crew"
 }
]
```

</details>

**Last recorded LLM run:** **PASS** — 6/6 atoms, 1 tool call(s), 4.8s

#### Q09

**Prompt:** Which flights fly BLR→BOM on 2026-09-17?

**Description:** Filter flights.json.

**Engine mapping** (`crew_ops/regression.py`):

```python
lambda w: [f["flight_no"] for f in
    Q.lookup_flights(w, on=date(2026, 9, 17),
                     dep_station="BLR", arr_station="BOM")]
```

**Graded atoms (2):** `DX412`, `DX431`

<details><summary>Expected answer (answer key)</summary>

```json
[
 "DX431",
 "DX412"
]
```

</details>

**Last recorded LLM run:** **PASS** — 2/2 atoms, 1 tool call(s), 3.7s

#### Q10

**Prompt:** How many flights operate on 2026-09-16 in total?

**Description:** Count flights.json rows for the date.

**Engine mapping** (`crew_ops/regression.py`):

```python
lambda w: len(Q.lookup_flights(w, on=date(2026, 9, 16)))
```

**Graded atoms (1):** `21`

<details><summary>Expected answer (answer key)</summary>

```json
21
```

</details>

**Last recorded LLM run:** **PASS** — 1/1 atoms, 1 tool call(s), 10.2s

#### Q11

**Prompt:** How many captains are based at DEL, and who are they?

**Description:** Filter crew.json by rank and base.

**Engine mapping** (`crew_ops/regression.py`):

```python
lambda w: [c["crew_id"] for c in
    Q.lookup_crew(w, rank="Captain", base="DEL")]
```

**Graded atoms (1):** `C-2210`

<details><summary>Expected answer (answer key)</summary>

```json
[
 "C-2210"
]
```

</details>

**Last recorded LLM run:** **PASS** — 1/1 atoms, 2 tool call(s), 5.9s

#### Q12

**Prompt:** What is the longest block time in the schedule, and which flights have it?

**Description:** Max block_hours in flights.json.

**Engine mapping** (`crew_ops/regression.py`):

```python
lambda w: (lambda mx: {
    "block_hours": mx,
    "flights": sorted({f.flight_no for f in w.flights_list
                       if abs(f.block_hours - mx) < 1e-6})})(
    max(f.block_hours for f in w.flights_list))
```

**Graded atoms (5):** `DX401`, `DX402`, `DX588`, `DX589`, `2.75`

<details><summary>Expected answer (answer key)</summary>

```json
{
 "block_hours": 2.75,
 "flights": [
  "DX401",
  "DX402",
  "DX588",
  "DX589"
 ]
}
```

</details>

**Last recorded LLM run:** **PASS** — 5/5 atoms, 1 tool call(s), 17.4s

#### Q13

**Prompt:** What is C-2087's rank, and total flight hours over the 28 days ending 2026-09-14?

**Description:** crew.json + duty_clocks.json. Note: C-2087 is a Captain.

**Engine mapping** (`crew_ops/regression.py`):

```python
lambda w: {"rank": w.crew["C-2087"].rank,
    "flight_hours_28d": Q.duty_clock(
        w, "C-2087", date(2026, 9, 14))["flight_hours_28d"]}
```

**Graded atoms (1):** `23.5`

<details><summary>Expected answer (answer key)</summary>

```json
{
 "rank": "Captain",
 "flight_hours_28d": 23.5
}
```

</details>

**Last recorded LLM run:** **PASS** — 1/1 atoms, 2 tool call(s), 5.6s

#### Q14

**Prompt:** Which stations does the network serve nonstop from BLR?

**Description:** Distinct arr_station where dep_station=BLR.

**Engine mapping** (`crew_ops/regression.py`):

```python
lambda w: sorted({f.arr_station for f in w.flights_list
    if f.dep_station == "BLR"})
```

**Graded atoms:** none (answer key holds only booleans/zero/prose — auto-PASS for the LLM eval; regression still diffs the full structure).

<details><summary>Expected answer (answer key)</summary>

```json
[
 "BOM",
 "CCU",
 "COK",
 "DEL",
 "GOI",
 "HYD",
 "MAA"
]
```

</details>

**Last recorded LLM run:** **PASS** — 0/0 atoms, 1 tool call(s), 26.5s

#### Q15

**Prompt:** Who is the Senior Cabin Crew on VT-DXB's pairing on 2026-09-16?

**Description:** rosters.json for the date/aircraft.

**Engine mapping** (`crew_ops/regression.py`):

```python
lambda w: next(m["crew_id"] for m in Q.pairing_info(
    w, aircraft="VT-DXB", on=date(2026, 9, 16))[0]["crew"]
    if m["role"] == "Senior Cabin Crew")
```

**Graded atoms (1):** `C-3171`

<details><summary>Expected answer (answer key)</summary>

```json
"C-3171"
```

</details>

**Last recorded LLM run:** **PASS** — 1/1 atoms, 1 tool call(s), 27.9s

#### Q16

**Prompt:** What is the disruption-risk score for C-1042 and what drives it?

**Description:** risk_signals.json — provided, not computed.

**Engine mapping** (`crew_ops/regression.py`):

```python
lambda w: _project(Q.risk_signals(w, crew_id="C-1042")[0],
    ["score", "drivers"])
```

**Graded atoms (1):** `0.78`

<details><summary>Expected answer (answer key)</summary>

```json
{
 "score": 0.78,
 "drivers": [
  "short-rest pattern over last 14 days",
  "two fatigue reports this month"
 ]
}
```

</details>

**Last recorded LLM run:** **PASS** — 1/1 atoms, 1 tool call(s), 2.7s

### Tier 2 — simulation & legality

#### Q17

**Prompt:** Captain C-1042 calls in sick at 05:00Z on 15 Sep for pairing P-2291. Which flights are immediately uncrewed?

**Description:** P-2291 is a 2-day pairing; day 1 legs lose their captain immediately and day 2 is at risk because the pairing overnights at DEL.

**Rules referenced:** `RULE-QUAL-05`

**Engine mapping** (`crew_ops/regression.py`):

```python
lambda w: (lambda i: {"day1": i["per_day"][0]["flights"],
                             "day2_also_at_risk": i["per_day"][1]["flights"],
                             "passengers_day1": i["per_day"][0]["passengers"]})(
    S.sick_crew_impact(w, "C-1042", "P-2291",
                       parse_utc("2026-09-15T05:00:00Z")))
```

**Graded atoms (7):** `DX412`, `DX413`, `DX588`, `DX589`, `DX590`, `DX591`, `486`

<details><summary>Expected answer (answer key)</summary>

```json
{
 "day1": [
  "DX412-2026-09-15",
  "DX413-2026-09-15",
  "DX588-2026-09-15"
 ],
 "day2_also_at_risk": [
  "DX589-2026-09-16",
  "DX590-2026-09-16",
  "DX591-2026-09-16"
 ],
 "passengers_day1": 486
}
```

</details>

**Last recorded LLM run:** **PARTIAL** — 6/7 atoms, 2 tool call(s), 20.4s — missing: `486`

#### Q18

**Prompt:** If Captain C-2087 is assigned to cover P-2291 from 15 Sep, does any rule breach? Give the detail.

**Description:** Simulate C-2087's 7-day duty window including the new duty; RULE-DUTY-02 is exceeded on day 1.

**Rules referenced:** `RULE-DUTY-02`

**Engine mapping** (`crew_ops/regression.py`):

```python
lambda w: _project(S.check_assignment(w, "C-2087", "P-2291"),
    ["legal", "issues"])
```

**Graded atoms (1):** `RULE-DUTY-02`

<details><summary>Expected answer (answer key)</summary>

```json
{
 "legal": false,
 "issues": [
  "RULE-DUTY-02: would exceed 60h/7d by 1h20m on 2026-09-15 (total 61.33h)",
  "RULE-DUTY-02: would exceed 60h/7d by 1h05m on 2026-09-16 (total 61.08h)"
 ]
}
```

</details>

**Last recorded LLM run:** **PASS** — 1/1 atoms, 1 tool call(s), 20.5s

#### Q19

**Prompt:** BLR is closed 08:00–14:00Z on 17 Sep. Which flights are affected?

**Description:** Any flight departing or arriving BLR inside the window. See scenario S3 for per-flight assessment.

**Engine mapping** (`crew_ops/regression.py`):

```python
lambda w: S.station_closure_impact(
    w, "BLR", parse_utc("2026-09-17T08:00:00Z"),
    parse_utc("2026-09-17T14:00:00Z"))["affected_flights"]
```

**Graded atoms (13):** `DX402`, `DX403`, `DX404`, `DX413`, `DX422`, `DX423`, `DX424`, `DX433`, `DX434`, `DX453`, `DX454`, `DX462`, `DX588`

<details><summary>Expected answer (answer key)</summary>

```json
[
 "DX402-2026-09-17",
 "DX422-2026-09-17",
 "DX462-2026-09-17",
 "DX453-2026-09-17",
 "DX433-2026-09-17",
 "DX403-2026-09-17",
 "DX413-2026-09-17",
 "DX423-2026-09-17",
 "DX454-2026-09-17",
 "DX434-2026-09-17",
 "DX404-2026-09-17",
 "DX424-2026-09-17",
 "DX588-2026-09-17"
]
```

</details>

**Last recorded LLM run:** **PASS** — 13/13 atoms, 1 tool call(s), 16.0s

#### Q20

**Prompt:** VT-DXA is delayed 90 minutes before DX401 on 16 Sep. Does the rostered crew breach any limit if they fly all four legs?

**Description:** FDP extends beyond the 4-sector limit of 12.0h.

**Rules referenced:** `RULE-FDP-01`

**Engine mapping** (`crew_ops/regression.py`):

```python
lambda w: _project(S.delay_impact(w, "VT-DXA", date(2026, 9, 16), 1.5),
    ["breach", "fdp_after_delay", "fdp_limit"])
```

**Graded atoms (2):** `12.0`, `12.75`

<details><summary>Expected answer (answer key)</summary>

```json
{
 "breach": true,
 "fdp_after_delay": 12.75,
 "fdp_limit": 12.0
}
```

</details>

**Last recorded LLM run:** **PASS** — 2/2 atoms, 2 tool call(s), 28.4s

#### Q21

**Prompt:** Can C-2210 (DEL base) legally cover P-2291 if positioned to BLR on the morning of 15 Sep? What is the operational consequence?

**Description:** Legal on all duty/rest/qualification checks; the cost is positioning plus duty-start delay.

**Rules referenced:** `RULE-BASE-07`, `RULE-REST-04`

**Engine mapping** (`crew_ops/regression.py`):

```python
lambda w: {"legal": S.check_assignment(
    w, "C-2210", "P-2291", delay_hours=3.25)["legal"],
    "consequence": "Deadhead positioning on DX402 (arr 08:45Z) delays the "
                   "first departure by ~3h; RULE-BASE-07 deadhead cost applies."}
```

**Graded atoms (2):** `DX402`, `RULE-BASE-07`

<details><summary>Expected answer (answer key)</summary>

```json
{
 "legal": true,
 "consequence": "Deadhead positioning on DX402 (arr 08:45Z) delays the first departure by ~3h; RULE-BASE-07 deadhead cost applies."
}
```

</details>

**Last recorded LLM run:** **PARTIAL** — 0/2 atoms, 12 tool call(s), 91.6s — missing: `DX402`, `RULE-BASE-07`

#### Q22

**Prompt:** Can C-5417 legally operate their rostered VT-DXB duty on 19 Sep?

**Description:** certifications.json vs duty date.

**Rules referenced:** `RULE-CERT-06`

**Engine mapping** (`crew_ops/regression.py`):

```python
lambda w: _project(S.cert_expiry_impact(w, "C-5417", date(2026, 9, 19)),
    ["legal", "rule", "detail"])
```

**Graded atoms (1):** `RULE-CERT-06`

<details><summary>Expected answer (answer key)</summary>

```json
{
 "legal": false,
 "rule": "RULE-CERT-06",
 "detail": "recurrent_training expired 2026-09-17"
}
```

</details>

**Last recorded LLM run:** **PASS** — 1/1 atoms, 3 tool call(s), 14.3s

#### Q23

**Prompt:** A crew is released at 15:30Z on 16 Sep. What is the earliest they may report next?

**Description:** RULE-REST-04: release + 12h.

**Rules referenced:** `RULE-REST-04`

**Engine mapping** (`crew_ops/regression.py`):

```python
lambda w: S.rest_requirement(
    w, parse_utc("2026-09-16T15:30:00Z"))["earliest_next_report_utc"]
```

**Graded atoms (2):** `03:30`, `2026-09-17`

<details><summary>Expected answer (answer key)</summary>

```json
"2026-09-17T03:30:00Z"
```

</details>

**Last recorded LLM run:** **PASS** — 2/2 atoms, 1 tool call(s), 8.8s

#### Q24

**Prompt:** Can reserve C-3305 cover the FULL pairing P-2291 (both days)? Why or why not?

**Description:** Day 1 fits, but the rolling 7-day duty window breaches on day 2 — a candidate must be legal for every day of the cover.

**Rules referenced:** `RULE-DUTY-02`

**Engine mapping** (`crew_ops/regression.py`):

```python
lambda w: _project(S.check_assignment(w, "C-3305", "P-2291"),
    ["legal", "issues"])
```

**Graded atoms (1):** `RULE-DUTY-02`

<details><summary>Expected answer (answer key)</summary>

```json
{
 "legal": false,
 "issues": [
  "RULE-DUTY-02: would exceed 60h/7d by 8h15m on 2026-09-16 (total 68.25h)"
 ]
}
```

</details>

**Last recorded LLM run:** **PASS** — 1/1 atoms, 2 tool call(s), 10.6s

#### Q25

**Prompt:** If DX404 on 16 Sep is cancelled, how many passengers are affected and what is the direct cancellation cost?

**Description:** flights.json seats + costs.json.

**Engine mapping** (`crew_ops/regression.py`):

```python
lambda w: _project(S.cancellation_impact(w, "DX404-2026-09-16"),
    ["passengers", "cost_inr"])
```

**Graded atoms (2):** `162`, `250000`

<details><summary>Expected answer (answer key)</summary>

```json
{
 "passengers": 162,
 "cost_inr": 250000
}
```

</details>

**Last recorded LLM run:** **PASS** — 2/2 atoms, 2 tool call(s), 7.9s

#### Q26

**Prompt:** Which crew have 45 or more duty hours in the 7 days ending 2026-09-15 (including any planned duty that day)?

**Description:** Rolling window over daily_history plus the current-week roster.

**Rules referenced:** `RULE-DUTY-02`

**Engine mapping** (`crew_ops/regression.py`):

```python
lambda w: [{"crew_id": x["crew_id"],
     "duty_hours_7d_incl_15sep_plan": x["duty_hours_7d"]}
    for x in Q.crew_over_duty_threshold(w, date(2026, 9, 15), 45)]
```

**Graded atoms (4):** `C-2087`, `C-3305`, `50.0`, `51.83`

<details><summary>Expected answer (answer key)</summary>

```json
[
 {
  "crew_id": "C-2087",
  "duty_hours_7d_incl_15sep_plan": 51.83
 },
 {
  "crew_id": "C-3305",
  "duty_hours_7d_incl_15sep_plan": 50.0
 }
]
```

</details>

**Last recorded LLM run:** **PASS** — 4/4 atoms, 1 tool call(s), 5.0s

#### Q27

**Prompt:** The VT-DXE captain is sick on 16 Sep (called 01:30Z). Which reserve captains' on-call windows cover the callout, and are they qualified?

**Description:** Callout must fall in the window; ATR rating required (RULE-QUAL-05). C-3315 qualifies; A320-only reserves are excluded.

**Rules referenced:** `RULE-QUAL-05`, `RULE-BASE-07`

**Engine mapping** (`crew_ops/regression.py`):

```python
lambda w: (lambda r: {
    "eligible": [o["crew_id"] for o in r["options"]
                 if o["crew_id"] and o["crew_id"] in w.reserves],
    "excluded_examples": [e for e in r["excluded_candidates"]
                          if e["crew_id"] in ("C-3310", "C-3305")][:2]})(
    _s1_cover(w))
```

**Graded atoms (4):** `C-3305`, `C-3310`, `C-3315`, `RULE-QUAL-05`

<details><summary>Expected answer (answer key)</summary>

```json
{
 "eligible": [
  "C-3315"
 ],
 "excluded_examples": [
  {
   "crew_id": "C-3305",
   "reason": "RULE-QUAL-05: no ATR72 rating"
  },
  {
   "crew_id": "C-3310",
   "reason": "reserve on-call window 06:00-18:00Z does not cover required report 03:00Z"
  }
 ]
}
```

</details>

**Last recorded LLM run:** **PARTIAL** — 0/4 atoms, 4 tool call(s), 14.6s — missing: `C-3305`, `C-3310`, `C-3315`, `RULE-QUAL-05`

#### Q28

**Prompt:** Captain C-5837 (VT-DXA line, works 14/17/20 Sep) is proposed to cover P-2291. Legal?

**Description:** Covering the pairing collides with his own 17 Sep duty — a downstream rest/overlap conflict, not a same-day one.

**Rules referenced:** `RULE-REST-04`

**Engine mapping** (`crew_ops/regression.py`):

```python
lambda w: _project(S.check_assignment(w, "C-5837", "P-2291",
                       exclude_pairing=None),
    ["legal", "issues"])
```

**Graded atoms (2):** `P-2204`, `RULE-REST-04`

<details><summary>Expected answer (answer key)</summary>

```json
{
 "legal": false,
 "issues": [
  "RULE-REST-04: only 10.75h rest before P-2204 on 2026-09-17 (downstream conflict)"
 ]
}
```

</details>

**Last recorded LLM run:** **PASS** — 2/2 atoms, 1 tool call(s), 13.2s

#### Q29

**Prompt:** Station HYD is closed 05:00–09:00Z on 19 Sep. Which flights are affected?

**Description:** Same window logic as S3 applied to HYD.

**Engine mapping** (`crew_ops/regression.py`):

```python
lambda w: S.station_closure_impact(
    w, "HYD", parse_utc("2026-09-19T05:00:00Z"),
    parse_utc("2026-09-19T09:00:00Z"))["affected_flights"]
```

**Graded atoms (2):** `DX461`, `DX462`

<details><summary>Expected answer (answer key)</summary>

```json
[
 "DX461-2026-09-19",
 "DX462-2026-09-19"
]
```

</details>

**Last recorded LLM run:** **PASS** — 2/2 atoms, 1 tool call(s), 22.3s

#### Q30 *(MANUAL — human-judged)*

**Prompt:** Which single flight leg has the most seats at risk if cancelled, and why?

**Description:** Seats come from aircraft_type; A320 legs dominate.

**Engine mapping** (`crew_ops/regression.py`):

```python
lambda w: {"answer": "Any A320 leg risks the most seats: A320 legs "
              "carry 162 seats vs 72 on ATR72 legs.",
    "max_seats": max(f.seats for f in w.flights_list)}
```

**Graded atoms:** none — graded manually.

<details><summary>Expected answer (answer key)</summary>

```json
{
 "flights": "any A320 leg (162 seats)",
 "vs": "ATR72 legs (72 seats)"
}
```

</details>

**Last recorded LLM run:** **MANUAL** — 0/0 atoms, 22 tool call(s), 21.3s

### Tier 3 — recommendations & planning

#### Q31

**Prompt:** Captain C-1042 is out for pairing P-2291 (15–16 Sep). Produce ranked resolution options with costs and reasoning.

**Description:** See scenario S2: reserve C-3310 is cheapest and clean; C-2210 requires deadhead + ~3h delay; C-2087 and C-3305 are excluded on RULE-DUTY-02; cancellation is last resort.

**Rules referenced:** `RULE-DUTY-02`, `RULE-BASE-07`

**Engine mapping** (`crew_ops/regression.py`):

```python
lambda w: REC.cover_options(
    w, "P-2291", "Captain", sick_crew_id="C-1042")["options"]
```

**Graded atoms (10):** `C-1526`, `C-2210`, `C-3310`, `C-3983`, `C-5566`, `1500000`, `18500`, `24000`, `3.0`, `41200`

<details><summary>Expected answer (answer key)</summary>

```json
[
 {
  "action": "Assign Captain C-3310 (reserve callout)",
  "crew_id": "C-3310",
  "legal": true,
  "rules_checked": [
   "RULE-FDP-01",
   "RULE-DUTY-02",
   "RULE-FLT-03",
   "RULE-REST-04",
   "RULE-QUAL-05",
   "RULE-CERT-06",
   "RULE-BASE-07"
  ],
  "cost_inr": 18500,
  "delay_hours": 0.0,
  "rank": 1
 },
 {
  "action": "Assign Captain C-1526 (day-off callout)",
  "crew_id": "C-1526",
  "legal": true,
  "rules_checked": [
   "RULE-FDP-01",
   "RULE-DUTY-02",
   "RULE-FLT-03",
   "RULE-REST-04",
   "RULE-QUAL-05",
   "RULE-CERT-06",
   "RULE-BASE-07"
  ],
  "cost_inr": 24000,
  "delay_hours": 0.0,
  "rank": 2
 },
 {
  "action": "Assign Captain C-3983 (day-off callout)",
  "crew_id": "C-3983",
  "legal": true,
  "rules_checked": [
   "RULE-FDP-01",
   "RULE-DUTY-02",
   "RULE-FLT-03",
   "RULE-REST-04",
   "RULE-QUAL-05",
   "RULE-CERT-06",
   "RULE-BASE-07"
  ],
  "cost_inr": 24000,
  "delay_hours": 0.0,
  "rank": 3
 },
 {
  "action": "Assign Captain C-5566 (day-off callout)",
  "crew_id": "C-5566",
  "legal": true,
  "rules_checked": [
   "RULE-FDP-01",
   "RULE-DUTY-02",
   "RULE-FLT-03",
   "RULE-REST-04",
   "RULE-QUAL-05",
   "RULE-CERT-06",
   "RULE-BASE-07"
  ],
  "cost_inr": 24000,
  "delay_hours": 0.0,
  "rank": 4
 },
 {
  "action": "Assign Captain C-2210 (reserve callout + deadhead from DEL (first departure delayed ~3.0h))",
  "crew_id": "C-2210",
  "legal": true,
  "rules_checked": [
   "RULE-FDP-01",
   "RULE-DUTY-02",
   "RULE-FLT-03",
   "RULE-REST-04",
   "RULE-QUAL-05",
   "RULE-CERT-06",
   "RULE-BASE-07"
  ],
  "cost_inr": 41200,
  "delay_hours": 3.0,
  "rank": 5
 },
 {
  "action": "Cancel all 6 flights of the pairing",
  "crew_id": null,
  "legal": true,
  "rules_checked": [],
  "cost_inr": 1500000,
  "delay_hours": 0.0,
  "rank": 6
 }
]
```

</details>

**Last recorded LLM run:** **PASS** — 10/10 atoms, 1 tool call(s), 28.9s

#### Q32

**Prompt:** Both A320 captains (VT-DXA and VT-DXB) are sick at 00:30Z on 18 Sep. Give the optimal joint crewing plan.

**Description:** Enumerate legal candidates per pairing, forbid double-assignment, minimise total cost. See scenario S6.

**Rules referenced:** `RULE-BASE-07`, `RULE-DUTY-02`

**Engine mapping** (`crew_ops/regression.py`):

```python
lambda w: (lambda j: {"total_cost_inr": j["total_cost_inr"],
                             "assign_dxa": j["assignments"][0],
                             "assign_dxb": j["assignments"][1]})(
    _s6_joint(w))
```

**Graded atoms (5):** `C-1017`, `C-3305`, `18500`, `24000`, `42500`

<details><summary>Expected answer (answer key)</summary>

```json
{
 "total_cost_inr": 42500,
 "assign_dxa": {
  "action": "Assign Captain C-3305 (reserve callout)",
  "crew_id": "C-3305",
  "legal": true,
  "rules_checked": [
   "RULE-FDP-01",
   "RULE-DUTY-02",
   "RULE-FLT-03",
   "RULE-REST-04",
   "RULE-QUAL-05",
   "RULE-CERT-06",
   "RULE-BASE-07"
  ],
  "cost_inr": 18500,
  "delay_hours": 0.0,
  "rank": 1
 },
 "assign_dxb": {
  "action": "Assign Captain C-1017 (day-off callout)",
  "crew_id": "C-1017",
  "legal": true,
  "rules_checked": [
   "RULE-FDP-01",
   "RULE-DUTY-02",
   "RULE-FLT-03",
   "RULE-REST-04",
   "RULE-QUAL-05",
   "RULE-CERT-06",
   "RULE-BASE-07"
  ],
  "cost_inr": 24000,
  "delay_hours": 0.0,
  "rank": 2
 }
}
```

</details>

**Last recorded LLM run:** **PARTIAL** — 0/5 atoms, 4 tool call(s), 35.3s — missing: `18500`, `24000`, `42500`, `C-1017`, `C-3305`

#### Q33

**Prompt:** After the 90-minute delay to VT-DXA on 16 Sep, what should Crew Control do about the FDP breach?

**Description:** Original crew legally completes 3 legs; a reserve set takes DX404. Cancellation is legal but ~3x the cost. See scenario S4.

**Rules referenced:** `RULE-FDP-01`

**Engine mapping** (`crew_ops/regression.py`):

```python
lambda w: REC.delay_recovery(w, "VT-DXA", date(2026, 9, 16), 1.5)["options"]
```

**Graded atoms (2):** `250000`, `75000`

<details><summary>Expected answer (answer key)</summary>

```json
[
 {
  "rank": 1,
  "action": "Original crew operates DX401\u2013DX403 (delayed); full reserve set (CPT, FO, SCC, 3 CC) operates DX404",
  "legal": true,
  "cost_inr": 75000,
  "reasoning": "Delayed 3-leg duty FDP 9.5h vs 12.5h limit \u2014 legal. Reserve set covers the last sector (callout window and 12h-rest all satisfied)."
 },
 {
  "rank": 2,
  "action": "Cancel DX404",
  "legal": true,
  "cost_inr": 250000,
  "reasoning": "Legal but ~3.3x more expensive than re-crewing one leg; 162 passengers stranded."
 }
]
```

</details>

**Last recorded LLM run:** **PASS** — 2/2 atoms, 1 tool call(s), 11.1s

#### Q34

**Prompt:** C-5417's recurrent training lapsed. Resolve their 19 Sep assignment.

**Description:** Cabin reserve callout is the clean fix; see scenario S5.

**Rules referenced:** `RULE-CERT-06`

**Engine mapping** (`crew_ops/regression.py`):

```python
lambda w: _s5_cover(w)["options"][:3]
```

**Graded atoms (5):** `C-1021`, `C-1385`, `C-4809`, `12500`, `9500`

<details><summary>Expected answer (answer key)</summary>

```json
[
 {
  "action": "Assign Cabin Crew C-4809 (reserve callout)",
  "crew_id": "C-4809",
  "legal": true,
  "rules_checked": [
   "RULE-FDP-01",
   "RULE-DUTY-02",
   "RULE-FLT-03",
   "RULE-REST-04",
   "RULE-QUAL-05",
   "RULE-CERT-06",
   "RULE-BASE-07"
  ],
  "cost_inr": 9500,
  "delay_hours": 0.0,
  "rank": 1
 },
 {
  "action": "Assign Cabin Crew C-1021 (day-off callout)",
  "crew_id": "C-1021",
  "legal": true,
  "rules_checked": [
   "RULE-FDP-01",
   "RULE-DUTY-02",
   "RULE-FLT-03",
   "RULE-REST-04",
   "RULE-QUAL-05",
   "RULE-CERT-06",
   "RULE-BASE-07"
  ],
  "cost_inr": 12500,
  "delay_hours": 0.0,
  "rank": 2
 },
 {
  "action": "Assign Cabin Crew C-1385 (day-off callout)",
  "crew_id": "C-1385",
  "legal": true,
  "rules_checked": [
   "RULE-FDP-01",
   "RULE-DUTY-02",
   "RULE-FLT-03",
   "RULE-REST-04",
   "RULE-QUAL-05",
   "RULE-CERT-06",
   "RULE-BASE-07"
  ],
  "cost_inr": 12500,
  "delay_hours": 0.0,
  "rank": 3
 }
]
```

</details>

**Last recorded LLM run:** **PARTIAL** — 2/5 atoms, 5 tool call(s), 26.5s — missing: `12500`, `C-1021`, `C-1385`

#### Q35

**Prompt:** BLR closes 08:00–14:00Z on 17 Sep. Outline the recovery plan across affected pairings.

**Description:** Delay-to-reopen where crew FDP holds; re-crew or cancel tail legs where it doesn't. See scenario S3.

**Rules referenced:** `RULE-FDP-01`

**Engine mapping** (`crew_ops/regression.py`):

```python
lambda w: S.station_closure_impact(
    w, "BLR", parse_utc("2026-09-17T08:00:00Z"),
    parse_utc("2026-09-17T14:00:00Z"))["per_flight_assessment"]
```

**Graded atoms (39):** `DX402`, `DX403`, `DX404`, `DX413`, `DX422`, `DX423`, `DX424`, `DX433`, `DX434`, `DX453`, `DX454`, `DX462`, `DX588`, `P-2204`, `P-2211`, `P-2218`, `P-2225`, `P-2232`, `P-2293`, `1.75`, `11.0`, `11.75`, `12.0`, `12.5`, `12.75`, `13.0`, `13.5`, `14.75`, `15.75`, `16.25`, `17.0`, `2.25`, `2.75`, `3.25`, `3.75`, `5.0`, `5.75`, `6.0`, `6.5`

<details><summary>Expected answer (answer key)</summary>

```json
[
 {
  "flight_id": "DX402-2026-09-17",
  "pairing_id": "P-2204",
  "min_delay_hours": 5.75,
  "crew_fdp_after_delay": 17.0,
  "fdp_limit": 12.0,
  "action": "delay exceeds crew FDP \u2014 re-crew tail legs from reserves or cancel"
 },
 {
  "flight_id": "DX422-2026-09-17",
  "pairing_id": "P-2211",
  "min_delay_hours": 5.75,
  "crew_fdp_after_delay": 17.0,
  "fdp_limit": 12.0,
  "action": "delay exceeds crew FDP \u2014 re-crew tail legs from reserves or cancel"
 },
 {
  "flight_id": "DX462-2026-09-17",
  "pairing_id": "P-2232",
  "min_delay_hours": 5.75,
  "crew_fdp_after_delay": 11.0,
  "fdp_limit": 13.0,
  "action": "delay (crew legal)"
 },
 {
  "flight_id": "DX453-2026-09-17",
  "pairing_id": "P-2225",
  "min_delay_hours": 6.5,
  "crew_fdp_after_delay": 14.75,
  "fdp_limit": 12.0,
  "action": "delay exceeds crew FDP \u2014 re-crew tail legs from reserves or cancel"
 },
 {
  "flight_id": "DX433-2026-09-17",
  "pairing_id": "P-2218",
  "min_delay_hours": 6.0,
  "crew_fdp_after_delay": 15.75,
  "fdp_limit": 12.0,
  "action": "delay exceeds crew FDP \u2014 re-crew tail legs from reserves or cancel"
 },
 {
  "flight_id": "DX403-2026-09-17",
  "pairing_id": "P-2204",
  "min_delay_hours": 5.0,
  "crew_fdp_after_delay": 16.25,
  "fdp_limit": 12.0,
  "action": "delay exceeds crew FDP \u2014 re-crew tail legs from reserves or cancel"
 },
 {
  "flight_id": "DX413-2026-09-17",
  "pairing_id": "P-2293",
  "min_delay_hours": 3.25,
  "crew_fdp_after_delay": 12.75,
  "fdp_limit": 12.5,
  "action": "delay exceeds crew FDP \u2014 re-crew tail legs from reserves or cancel"
 },
 {
  "flight_id": "DX423-2026-09-17",
  "pairing_id": "P-2211",
  "min_delay_hours": 5.0,
  "crew_fdp_after_delay": 16.25,
  "fdp_limit": 12.0,
  "action": "delay exceeds crew FDP \u2014 re-crew tail legs from reserves or cancel"
 },
 {
  "flight_id": "DX454-2026-09-17",
  "pairing_id": "P-2225",
  "min_delay_hours": 3.75,
  "crew_fdp_after_delay": 12.0,
  "fdp_limit": 12.0,
  "action": "delay (crew legal)"
 },
 {
  "flight_id": "DX434-2026-09-17",
  "pairing_id": "P-2218",
  "min_delay_hours": 2.75,
  "crew_fdp_after_delay": 12.5,
  "fdp_limit": 12.0,
  "action": "delay exceeds crew FDP \u2014 re-crew tail legs from reserves or cancel"
 },
 {
  "flight_id": "DX404-2026-09-17",
  "pairing_id": "P-2204",
  "min_delay_hours": 2.25,
  "crew_fdp_after_delay": 13.5,
  "fdp_limit": 12.0,
  "action": "delay exceeds crew FDP \u2014 re-crew tail legs from reserves or cancel"
 },
 {
  "flight_id": "DX424-2026-09-17",
  "pairing_id": "P-2211",
  "min_delay_hours": 1.75,
  "crew_fdp_after_delay": 13.0,
  "fdp_limit": 12.0,
  "action": "delay exceeds crew FDP \u2014 re-crew tail legs from reserves or cancel"
 },
 {
  "flight_id": "DX588-2026-09-17",
  "pairing_id": "P-2293",
  "min_delay_hours": 2.25,
  "crew_fdp_after_delay": 11.75,
  "fdp_limit": 12.5,
  "action": "delay (crew legal)"
 }
]
```

</details>

**Last recorded LLM run:** **PARTIAL** — 33/39 atoms, 34 tool call(s), 47.3s — missing: `13.5`, `16.25`, `3.25`, `3.75`, `6.0`, `6.5`

#### Q36 *(MANUAL — human-judged)*

**Prompt:** Draft the callout notification to C-3310 for covering P-2291.

**Description:** Judged on completeness, correctness of times from rosters.json, and clarity — not template wording.

**Engine mapping** (`crew_ops/regression.py`):

```python
lambda w: REC.draft_notification(w, "C-3310", "P-2291")
```

**Graded atoms:** none — graded manually.

<details><summary>Expected answer (answer key)</summary>

```json
{
 "must_include": [
  "crew_id and pairing_id",
  "report time/place: 06:00Z 15 Sep, BLR crew room",
  "flights day 1: DX412/DX413/DX588; overnight DEL (hotel arranged)",
  "flights day 2: DX589/DX590/DX591, report 04:00Z at DEL",
  "acknowledgement request with deadline",
  "contact for questions"
 ]
}
```

</details>

**Last recorded LLM run:** **MANUAL** — 0/0 atoms, 1 tool call(s), 9.4s

#### Q37

**Prompt:** What is the cheapest legal way to cover the VT-DXF First Officer on 20 Sep if they call sick at 03:30Z?

**Description:** ATR-rated FO reserve C-3316 (window 03:00–15:00) is the clean cover.

**Rules referenced:** `RULE-QUAL-05`

**Engine mapping** (`crew_ops/regression.py`):

```python
lambda w: _s_vtdxf_fo(w)["options"][0]
```

**Graded atoms (2):** `C-3316`, `18500`

<details><summary>Expected answer (answer key)</summary>

```json
{
 "action": "Assign First Officer C-3316 (reserve callout)",
 "crew_id": "C-3316",
 "legal": true,
 "rules_checked": [
  "RULE-FDP-01",
  "RULE-DUTY-02",
  "RULE-FLT-03",
  "RULE-REST-04",
  "RULE-QUAL-05",
  "RULE-CERT-06",
  "RULE-BASE-07"
 ],
 "cost_inr": 18500,
 "delay_hours": 0.0,
 "rank": 1
}
```

</details>

**Last recorded LLM run:** **PASS** — 2/2 atoms, 4 tool call(s), 48.8s

#### Q38 *(MANUAL — human-judged)*

**Prompt:** If the desk wants a standing morning briefing, which three data points per aircraft line should it surface and why?

**Description:** Tier-3 open question — grading rubric style.

**Engine mapping** (`crew_ops/regression.py`):

```python
lambda w: {"suggested": [
    "crew legality headroom (7d duty window) for today's rostered crew",
    "reserve availability by on-call window and rating for the day",
    "disruption-risk signals for today's rostered crew (provided input)"]}
```

**Graded atoms:** none — graded manually.

<details><summary>Expected answer (answer key)</summary>

```json
{
 "suggested": [
  "crew legality headroom (7d duty) for today's rostered crew",
  "reserve availability by window and rating for the day",
  "risk_signals for today's rostered crew (provided input)"
 ],
 "note": "Open-ended; judged on operational reasoning, not exact match."
}
```

</details>

**Last recorded LLM run:** **MANUAL** — 0/0 atoms, 0 tool call(s), 14.0s

---

## Scenarios (S1–S6)

Each scenario feeds the event `narrative` (plus the fixed assessment instruction above) to the LLM; the regression harness dispatches on the event `type` (`SICK_CREW`, `CERT_EXPIRY`, `STATION_CLOSURE`, `DELAY`, `MULTI_SICK`) via `crew_ops/regression.py:answer_scenario`.

#### S1 — ATR captain sick call

**Difficulty:** easy  |  **Event type:** `SICK_CREW`

**Narrative (LLM prompt):** Captain C-3231 calls in sick at 01:30Z on 16 Sep for pairing P-2224 (VT-DXE, 4 legs).

**Event parameters:** `{"crew_id": "C-3231", "pairing_id": "P-2224", "reported_utc": "2026-09-16T01:30:00Z"}`

**Graded atoms (34):** `C-1017`, `C-1042`, `C-1443`, `C-1526`, `C-1600`, `C-1671`, `C-1938`, `C-2087`, `C-2091`, `C-2143`, `C-2210`, `C-2221`, `C-3187`, `C-3305`, `C-3310`, `C-3315`, `C-3721`, `C-3940`, `C-3983`, `C-5392`, `C-5566`, `C-5647`, `C-5820`, `C-5837`, `DX451`, `DX452`, `DX453`, `DX454`, `P-2231`, `RULE-QUAL-05`, `RULE-REST-04`, `1000000`, `18500`, `24000`

<details><summary>Answer key</summary>

```json
{
 "uncovered_flights": [
  "DX451-2026-09-16",
  "DX452-2026-09-16",
  "DX453-2026-09-16",
  "DX454-2026-09-16"
 ],
 "options": [
  {
   "action": "Assign Captain C-3315 (reserve callout)",
   "crew_id": "C-3315",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 18500,
   "delay_hours": 0.0,
   "rank": 1
  },
  {
   "action": "Assign Captain C-1600 (day-off callout)",
   "crew_id": "C-1600",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 24000,
   "delay_hours": 0.0,
   "rank": 2
  },
  {
   "action": "Assign Captain C-1671 (day-off callout)",
   "crew_id": "C-1671",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 24000,
   "delay_hours": 0.0,
   "rank": 3
  },
  {
   "action": "Assign Captain C-2091 (day-off callout)",
   "crew_id": "C-2091",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 24000,
   "delay_hours": 0.0,
   "rank": 4
  },
  {
   "action": "Assign Captain C-2221 (day-off callout)",
   "crew_id": "C-2221",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 24000,
   "delay_hours": 0.0,
   "rank": 5
  },
  {
   "action": "Assign Captain C-3721 (day-off callout)",
   "crew_id": "C-3721",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 24000,
   "delay_hours": 0.0,
   "rank": 6
  },
  {
   "action": "Cancel all 4 flights of the pairing",
   "crew_id": null,
   "legal": true,
   "rules_checked": [],
   "cost_inr": 1000000,
   "delay_hours": 0.0,
   "rank": 7
  }
 ],
 "excluded_candidates": [
  {
   "crew_id": "C-1042",
   "reason": "RULE-QUAL-05: no ATR72 rating"
  },
  {
   "crew_id": "C-2087",
   "reason": "RULE-QUAL-05: no ATR72 rating"
  },
  {
   "crew_id": "C-2210",
   "reason": "RULE-QUAL-05: no ATR72 rating"
  },
  {
   "crew_id": "C-3305",
   "reason": "RULE-QUAL-05: no ATR72 rating"
  },
  {
   "crew_id": "C-3310",
   "reason": "reserve on-call window 06:00-18:00Z does not cover required report 03:00Z"
  },
  {
   "crew_id": "C-5837",
   "reason": "RULE-QUAL-05: no ATR72 rating"
  },
  {
   "crew_id": "C-3940",
   "reason": "RULE-QUAL-05: no ATR72 rating"
  },
  {
   "crew_id": "C-3187",
   "reason": "RULE-QUAL-05: no ATR72 rating"
  },
  {
   "crew_id": "C-2143",
   "reason": "RULE-QUAL-05: no ATR72 rating"
  },
  {
   "crew_id": "C-1938",
   "reason": "RULE-QUAL-05: no ATR72 rating"
  },
  {
   "crew_id": "C-5647",
   "reason": "RULE-QUAL-05: no ATR72 rating"
  },
  {
   "crew_id": "C-5820",
   "reason": "RULE-QUAL-05: no ATR72 rating"
  },
  {
   "crew_id": "C-1443",
   "reason": "RULE-QUAL-05: no ATR72 rating"
  },
  {
   "crew_id": "C-1017",
   "reason": "RULE-QUAL-05: no ATR72 rating"
  },
  {
   "crew_id": "C-5392",
   "reason": "RULE-REST-04: only -7.25h rest before P-2231 on 2026-09-16 (downstream conflict); double-booked: COVER overlaps P-2231 on 2026-09-16"
  },
  {
   "crew_id": "C-3983",
   "reason": "RULE-QUAL-05: no ATR72 rating"
  },
  {
   "crew_id": "C-5566",
   "reason": "RULE-QUAL-05: no ATR72 rating"
  },
  {
   "crew_id": "C-1526",
   "reason": "RULE-QUAL-05: no ATR72 rating"
  }
 ],
 "expected_choice": {
  "action": "Assign Captain C-3315 (reserve callout)",
  "crew_id": "C-3315",
  "legal": true,
  "rules_checked": [
   "RULE-FDP-01",
   "RULE-DUTY-02",
   "RULE-FLT-03",
   "RULE-REST-04",
   "RULE-QUAL-05",
   "RULE-CERT-06",
   "RULE-BASE-07"
  ],
  "cost_inr": 18500,
  "delay_hours": 0.0,
  "rank": 1
 }
}
```

</details>

**Last recorded LLM run:** **PARTIAL** — 4/34 atoms, 2 tool call(s), 13.7s — missing: `1000000`, `18500`, `24000`, `C-1017`, `C-1042`, `C-1443`, `C-1526`, `C-1600`, `C-1671`, `C-1938`, `C-2087`, `C-2091`, `C-2143`, `C-2210`, `C-2221`, `C-3187`, `C-3305`, `C-3310`, `C-3315`, `C-3721`, `C-3940`, `C-3983`, `C-5392`, `C-5566`, `C-5647`, `C-5820`, `C-5837`, `P-2231`, `RULE-QUAL-05`, `RULE-REST-04`

#### S2 — Flagship: Captain C-1042 sick — 2-day pairing

**Difficulty:** medium  |  **Event type:** `SICK_CREW`

**Narrative (LLM prompt):** Captain C-1042 calls in sick at 05:00Z on 15 Sep for his 2-day pairing P-2291 (day 1: DX412/DX413/DX588; day 2: DX589/DX590/DX591). The cover must take the full remaining pairing (the aircraft overnights at DEL).

**Event parameters:** `{"crew_id": "C-1042", "pairing_id": "P-2291", "reported_utc": "2026-09-15T05:00:00Z"}`

**Graded atoms (48):** `C-1017`, `C-1443`, `C-1526`, `C-1600`, `C-1671`, `C-1938`, `C-2087`, `C-2091`, `C-2143`, `C-2210`, `C-2221`, `C-3187`, `C-3231`, `C-3305`, `C-3310`, `C-3315`, `C-3721`, `C-3940`, `C-3983`, `C-5392`, `C-5566`, `C-5647`, `C-5820`, `C-5837`, `DX412`, `DX413`, `DX588`, `DX589`, `DX590`, `DX591`, `P-2202`, `P-2203`, `P-2204`, `P-2209`, `P-2210`, `P-2211`, `P-2216`, `P-2217`, `P-2218`, `RULE-DUTY-02`, `RULE-QUAL-05`, `RULE-REST-04`, `1500000`, `18500`, `24000`, `3.0`, `41200`, `486`

<details><summary>Answer key</summary>

```json
{
 "uncovered_flights_day1": [
  "DX412-2026-09-15",
  "DX413-2026-09-15",
  "DX588-2026-09-15"
 ],
 "uncovered_flights_day2": [
  "DX589-2026-09-16",
  "DX590-2026-09-16",
  "DX591-2026-09-16"
 ],
 "passengers_at_risk_day1": 486,
 "options": [
  {
   "action": "Assign Captain C-3310 (reserve callout)",
   "crew_id": "C-3310",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 18500,
   "delay_hours": 0.0,
   "rank": 1
  },
  {
   "action": "Assign Captain C-1526 (day-off callout)",
   "crew_id": "C-1526",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 24000,
   "delay_hours": 0.0,
   "rank": 2
  },
  {
   "action": "Assign Captain C-3983 (day-off callout)",
   "crew_id": "C-3983",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 24000,
   "delay_hours": 0.0,
   "rank": 3
  },
  {
   "action": "Assign Captain C-5566 (day-off callout)",
   "crew_id": "C-5566",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 24000,
   "delay_hours": 0.0,
   "rank": 4
  },
  {
   "action": "Assign Captain C-2210 (reserve callout + deadhead from DEL (first departure delayed ~3.0h))",
   "crew_id": "C-2210",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 41200,
   "delay_hours": 3.0,
   "rank": 5
  },
  {
   "action": "Cancel all 6 flights of the pairing",
   "crew_id": null,
   "legal": true,
   "rules_checked": [],
   "cost_inr": 1500000,
   "delay_hours": 0.0,
   "rank": 6
  }
 ],
 "excluded_candidates": [
  {
   "crew_id": "C-2087",
   "reason": "RULE-DUTY-02: would exceed 60h/7d by 1h20m on 2026-09-15 (total 61.33h); RULE-DUTY-02: would exceed 60h/7d by 1h05m on 2026-09-16 (total 61.08h)"
  },
  {
   "crew_id": "C-3305",
   "reason": "reserve on-call window 00:00-05:30Z does not cover required report 06:00Z"
  },
  {
   "crew_id": "C-3315",
   "reason": "RULE-QUAL-05: no A320 rating"
  },
  {
   "crew_id": "C-2091",
   "reason": "RULE-QUAL-05: no A320 rating"
  },
  {
   "crew_id": "C-5837",
   "reason": "RULE-REST-04: only 10.75h rest before P-2204 on 2026-09-17 (downstream conflict)"
  },
  {
   "crew_id": "C-3940",
   "reason": "RULE-REST-04: only -6.75h rest before COVER on 2026-09-15 (rest conflict); double-booked: P-2202 overlaps COVER on 2026-09-15"
  },
  {
   "crew_id": "C-3187",
   "reason": "RULE-REST-04: only 10.0h rest before P-2203 on 2026-09-16 (downstream conflict); RULE-REST-04: only -8.75h rest before COVER on 2026-09-16 (rest conflict); double-booked: P-2203 overlaps COVER on 2026-09-16"
  },
  {
   "crew_id": "C-2143",
   "reason": "RULE-REST-04: only 11.25h rest before P-2211 on 2026-09-17 (downstream conflict)"
  },
  {
   "crew_id": "C-1938",
   "reason": "RULE-REST-04: only -7.25h rest before COVER on 2026-09-15 (rest conflict); double-booked: P-2209 overlaps COVER on 2026-09-15"
  },
  {
   "crew_id": "C-5647",
   "reason": "RULE-REST-04: only 10.5h rest before P-2210 on 2026-09-16 (downstream conflict); RULE-REST-04: only -9.25h rest before COVER on 2026-09-16 (rest conflict); double-booked: P-2210 overlaps COVER on 2026-09-16"
  },
  {
   "crew_id": "C-5820",
   "reason": "RULE-REST-04: only 11.75h rest before P-2218 on 2026-09-17 (downstream conflict)"
  },
  {
   "crew_id": "C-1443",
   "reason": "RULE-REST-04: only -6.25h rest before COVER on 2026-09-15 (rest conflict); double-booked: P-2216 overlaps COVER on 2026-09-15"
  },
  {
   "crew_id": "C-1017",
   "reason": "RULE-REST-04: only 11.0h rest before P-2217 on 2026-09-16 (downstream conflict); RULE-REST-04: only -8.25h rest before COVER on 2026-09-16 (rest conflict); double-booked: P-2217 overlaps COVER on 2026-09-16"
  },
  {
   "crew_id": "C-1671",
   "reason": "RULE-QUAL-05: no A320 rating"
  },
  {
   "crew_id": "C-1600",
   "reason": "RULE-QUAL-05: no A320 rating"
  },
  {
   "crew_id": "C-3231",
   "reason": "RULE-QUAL-05: no A320 rating"
  },
  {
   "crew_id": "C-2221",
   "reason": "RULE-QUAL-05: no A320 rating"
  },
  {
   "crew_id": "C-3721",
   "reason": "RULE-QUAL-05: no A320 rating"
  },
  {
   "crew_id": "C-5392",
   "reason": "RULE-QUAL-05: no A320 rating"
  }
 ],
 "expected_choice": {
  "action": "Assign Captain C-3310 (reserve callout)",
  "crew_id": "C-3310",
  "legal": true,
  "rules_checked": [
   "RULE-FDP-01",
   "RULE-DUTY-02",
   "RULE-FLT-03",
   "RULE-REST-04",
   "RULE-QUAL-05",
   "RULE-CERT-06",
   "RULE-BASE-07"
  ],
  "cost_inr": 18500,
  "delay_hours": 0.0,
  "rank": 1
 }
}
```

</details>

**Last recorded LLM run:** **PARTIAL** — 11/48 atoms, 17 tool call(s), 74.5s — missing: `18500`, `24000`, `41200`, `486`, `C-1017`, `C-1443`, `C-1526`, `C-1600`, `C-1671`, `C-1938`, `C-2087`, `C-2091`, `C-2143`, `C-2210`, `C-2221`, `C-3187`, `C-3231`, `C-3721`, `C-3940`, `C-3983`, `C-5392`, `C-5566`, `C-5647`, `C-5820`, `C-5837`, `P-2202`, `P-2203`, `P-2204`, `P-2209`, `P-2210`, `P-2211`, `P-2216`, `P-2217`, `P-2218`, `RULE-DUTY-02`, `RULE-QUAL-05`, `RULE-REST-04`

#### S3 — BLR station closure 08:00–14:00Z, 17 Sep

**Difficulty:** medium  |  **Event type:** `STATION_CLOSURE`

**Narrative (LLM prompt):** BLR is closed to all departures and arrivals 08:00–14:00Z on 17 Sep (fuel-farm incident). Flights airborne may not land at BLR in the window.

**Event parameters:** `{"station": "BLR", "window_utc": {"start": "2026-09-17T08:00:00Z", "end": "2026-09-17T14:00:00Z"}}`

**Graded atoms (39):** `DX402`, `DX403`, `DX404`, `DX413`, `DX422`, `DX423`, `DX424`, `DX433`, `DX434`, `DX453`, `DX454`, `DX462`, `DX588`, `P-2204`, `P-2211`, `P-2218`, `P-2225`, `P-2232`, `P-2293`, `1.75`, `11.0`, `11.75`, `12.0`, `12.5`, `12.75`, `13.0`, `13.5`, `14.75`, `15.75`, `16.25`, `17.0`, `2.25`, `2.75`, `3.25`, `3.75`, `5.0`, `5.75`, `6.0`, `6.5`

<details><summary>Answer key</summary>

```json
{
 "affected_flights": [
  "DX402-2026-09-17",
  "DX422-2026-09-17",
  "DX462-2026-09-17",
  "DX453-2026-09-17",
  "DX433-2026-09-17",
  "DX403-2026-09-17",
  "DX413-2026-09-17",
  "DX423-2026-09-17",
  "DX454-2026-09-17",
  "DX434-2026-09-17",
  "DX404-2026-09-17",
  "DX424-2026-09-17",
  "DX588-2026-09-17"
 ],
 "per_flight_assessment": [
  {
   "flight_id": "DX402-2026-09-17",
   "pairing_id": "P-2204",
   "min_delay_hours": 5.75,
   "crew_fdp_after_delay": 17.0,
   "fdp_limit": 12.0,
   "action": "delay exceeds crew FDP \u2014 re-crew tail legs from reserves or cancel"
  },
  {
   "flight_id": "DX422-2026-09-17",
   "pairing_id": "P-2211",
   "min_delay_hours": 5.75,
   "crew_fdp_after_delay": 17.0,
   "fdp_limit": 12.0,
   "action": "delay exceeds crew FDP \u2014 re-crew tail legs from reserves or cancel"
  },
  {
   "flight_id": "DX462-2026-09-17",
   "pairing_id": "P-2232",
   "min_delay_hours": 5.75,
   "crew_fdp_after_delay": 11.0,
   "fdp_limit": 13.0,
   "action": "delay (crew legal)"
  },
  {
   "flight_id": "DX453-2026-09-17",
   "pairing_id": "P-2225",
   "min_delay_hours": 6.5,
   "crew_fdp_after_delay": 14.75,
   "fdp_limit": 12.0,
   "action": "delay exceeds crew FDP \u2014 re-crew tail legs from reserves or cancel"
  },
  {
   "flight_id": "DX433-2026-09-17",
   "pairing_id": "P-2218",
   "min_delay_hours": 6.0,
   "crew_fdp_after_delay": 15.75,
   "fdp_limit": 12.0,
   "action": "delay exceeds crew FDP \u2014 re-crew tail legs from reserves or cancel"
  },
  {
   "flight_id": "DX403-2026-09-17",
   "pairing_id": "P-2204",
   "min_delay_hours": 5.0,
   "crew_fdp_after_delay": 16.25,
   "fdp_limit": 12.0,
   "action": "delay exceeds crew FDP \u2014 re-crew tail legs from reserves or cancel"
  },
  {
   "flight_id": "DX413-2026-09-17",
   "pairing_id": "P-2293",
   "min_delay_hours": 3.25,
   "crew_fdp_after_delay": 12.75,
   "fdp_limit": 12.5,
   "action": "delay exceeds crew FDP \u2014 re-crew tail legs from reserves or cancel"
  },
  {
   "flight_id": "DX423-2026-09-17",
   "pairing_id": "P-2211",
   "min_delay_hours": 5.0,
   "crew_fdp_after_delay": 16.25,
   "fdp_limit": 12.0,
   "action": "delay exceeds crew FDP \u2014 re-crew tail legs from reserves or cancel"
  },
  {
   "flight_id": "DX454-2026-09-17",
   "pairing_id": "P-2225",
   "min_delay_hours": 3.75,
   "crew_fdp_after_delay": 12.0,
   "fdp_limit": 12.0,
   "action": "delay (crew legal)"
  },
  {
   "flight_id": "DX434-2026-09-17",
   "pairing_id": "P-2218",
   "min_delay_hours": 2.75,
   "crew_fdp_after_delay": 12.5,
   "fdp_limit": 12.0,
   "action": "delay exceeds crew FDP \u2014 re-crew tail legs from reserves or cancel"
  },
  {
   "flight_id": "DX404-2026-09-17",
   "pairing_id": "P-2204",
   "min_delay_hours": 2.25,
   "crew_fdp_after_delay": 13.5,
   "fdp_limit": 12.0,
   "action": "delay exceeds crew FDP \u2014 re-crew tail legs from reserves or cancel"
  },
  {
   "flight_id": "DX424-2026-09-17",
   "pairing_id": "P-2211",
   "min_delay_hours": 1.75,
   "crew_fdp_after_delay": 13.0,
   "fdp_limit": 12.0,
   "action": "delay exceeds crew FDP \u2014 re-crew tail legs from reserves or cancel"
  },
  {
   "flight_id": "DX588-2026-09-17",
   "pairing_id": "P-2293",
   "min_delay_hours": 2.25,
   "crew_fdp_after_delay": 11.75,
   "fdp_limit": 12.5,
   "action": "delay (crew legal)"
  }
 ],
 "note": "Delays are measured to reopen +30min turnaround. Where the extended duty exceeds RULE-FDP-01, tail legs need reserve re-crew or cancellation."
}
```

</details>

**Last recorded LLM run:** **PARTIAL** — 38/39 atoms, 34 tool call(s), 46.6s — missing: `P-2232`

#### S4 — Tech delay cascades into an FDP breach

**Difficulty:** medium-hard  |  **Event type:** `DELAY`

**Narrative (LLM prompt):** VT-DXA has a 90-minute technical delay before DX401 on 16 Sep. All four legs shift by 90 minutes.

**Event parameters:** `{"aircraft": "VT-DXA", "date": "2026-09-16", "delay_hours": 1.5}`

**Graded atoms (6):** `DX404`, `RULE-FDP-01`, `12.0`, `12.75`, `250000`, `75000`

<details><summary>Answer key</summary>

```json
{
 "fdp_after_delay": 12.75,
 "fdp_limit": 12.0,
 "breach": true,
 "breach_detail": "RULE-FDP-01: delayed duty runs 12.75h vs 12.0h limit (4 sectors) \u2014 the rostered crew cannot legally complete DX404.",
 "options": [
  {
   "rank": 1,
   "action": "Original crew operates DX401\u2013DX403 (delayed); full reserve set (CPT, FO, SCC, 3 CC) operates DX404",
   "legal": true,
   "cost_inr": 75000,
   "reasoning": "Delayed 3-leg duty FDP 9.5h vs 12.5h limit \u2014 legal. Reserve set covers the last sector (callout window and 12h-rest all satisfied)."
  },
  {
   "rank": 2,
   "action": "Cancel DX404",
   "legal": true,
   "cost_inr": 250000,
   "reasoning": "Legal but ~3.3x more expensive than re-crewing one leg; 162 passengers stranded."
  }
 ],
 "expected_choice": {
  "rank": 1,
  "action": "Original crew operates DX401\u2013DX403 (delayed); full reserve set (CPT, FO, SCC, 3 CC) operates DX404",
  "legal": true,
  "cost_inr": 75000,
  "reasoning": "Delayed 3-leg duty FDP 9.5h vs 12.5h limit \u2014 legal. Reserve set covers the last sector (callout window and 12h-rest all satisfied)."
 }
}
```

</details>

**Last recorded LLM run:** **PARTIAL** — 0/6 atoms, 6 tool call(s), 45.5s — missing: `12.0`, `12.75`, `250000`, `75000`, `DX404`, `RULE-FDP-01`

#### S5 — Certification lapse discovered pre-flight

**Difficulty:** medium  |  **Event type:** `CERT_EXPIRY`

**Narrative (LLM prompt):** Compliance flags at 10:00Z on 18 Sep that C-5417's recurrent_training expired on 17 Sep. Their rostered duty on 19 Sep (VT-DXB) is now illegal under RULE-CERT-06.

**Event parameters:** `{"crew_id": "C-5417", "pairing_id": "P-2213", "reported_utc": "2026-09-18T10:00:00Z"}`

**Graded atoms (76):** `C-1021`, `C-1329`, `C-1385`, `C-1414`, `C-1542`, `C-1568`, `C-1569`, `C-1594`, `C-1622`, `C-1748`, `C-1873`, `C-1970`, `C-2083`, `C-2100`, `C-2165`, `C-2248`, `C-2252`, `C-2286`, `C-2352`, `C-2435`, `C-2751`, `C-2840`, `C-2876`, `C-2907`, `C-3046`, `C-3145`, `C-3167`, `C-3249`, `C-3271`, `C-3545`, `C-3569`, `C-3619`, `C-3757`, `C-3897`, `C-3973`, `C-3988`, `C-4273`, `C-4280`, `C-4326`, `C-4395`, `C-4458`, `C-4462`, `C-4531`, `C-4588`, `C-4622`, `C-4679`, `C-4809`, `C-4839`, `C-4874`, `C-4999`, `C-5089`, `C-5119`, `C-5168`, `C-5417`, `C-5418`, `C-5444`, `C-5666`, `C-5723`, `C-5751`, `C-5795`, `C-5848`, `C-5881`, `C-5906`, `C-5994`, `P-2206`, `P-2220`, `P-2295`, `RULE-CERT-06`, `RULE-QUAL-05`, `RULE-REST-04`, `1000000`, `12500`, `53800`, `56800`, `7.0`, `9500`

<details><summary>Answer key</summary>

```json
{
 "illegal_assignment": {
  "crew_id": "C-5417",
  "date": "2026-09-19",
  "rule": "RULE-CERT-06"
 },
 "options": [
  {
   "action": "Assign Cabin Crew C-4809 (reserve callout)",
   "crew_id": "C-4809",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 9500,
   "delay_hours": 0.0,
   "rank": 1
  },
  {
   "action": "Assign Cabin Crew C-1021 (day-off callout)",
   "crew_id": "C-1021",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 12500,
   "delay_hours": 0.0,
   "rank": 2
  },
  {
   "action": "Assign Cabin Crew C-1385 (day-off callout)",
   "crew_id": "C-1385",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 12500,
   "delay_hours": 0.0,
   "rank": 3
  },
  {
   "action": "Assign Cabin Crew C-1414 (day-off callout)",
   "crew_id": "C-1414",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 12500,
   "delay_hours": 0.0,
   "rank": 4
  },
  {
   "action": "Assign Cabin Crew C-1569 (day-off callout)",
   "crew_id": "C-1569",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 12500,
   "delay_hours": 0.0,
   "rank": 5
  },
  {
   "action": "Assign Cabin Crew C-1748 (day-off callout)",
   "crew_id": "C-1748",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 12500,
   "delay_hours": 0.0,
   "rank": 6
  },
  {
   "action": "Assign Cabin Crew C-1873 (day-off callout)",
   "crew_id": "C-1873",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 12500,
   "delay_hours": 0.0,
   "rank": 7
  },
  {
   "action": "Assign Cabin Crew C-1970 (day-off callout)",
   "crew_id": "C-1970",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 12500,
   "delay_hours": 0.0,
   "rank": 8
  },
  {
   "action": "Assign Cabin Crew C-2083 (day-off callout)",
   "crew_id": "C-2083",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 12500,
   "delay_hours": 0.0,
   "rank": 9
  },
  {
   "action": "Assign Cabin Crew C-2165 (day-off callout)",
   "crew_id": "C-2165",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 12500,
   "delay_hours": 0.0,
   "rank": 10
  },
  {
   "action": "Assign Cabin Crew C-2252 (day-off callout)",
   "crew_id": "C-2252",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 12500,
   "delay_hours": 0.0,
   "rank": 11
  },
  {
   "action": "Assign Cabin Crew C-2286 (day-off callout)",
   "crew_id": "C-2286",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 12500,
   "delay_hours": 0.0,
   "rank": 12
  },
  {
   "action": "Assign Cabin Crew C-2435 (day-off callout)",
   "crew_id": "C-2435",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 12500,
   "delay_hours": 0.0,
   "rank": 13
  },
  {
   "action": "Assign Cabin Crew C-2751 (day-off callout)",
   "crew_id": "C-2751",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 12500,
   "delay_hours": 0.0,
   "rank": 14
  },
  {
   "action": "Assign Cabin Crew C-2840 (day-off callout)",
   "crew_id": "C-2840",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 12500,
   "delay_hours": 0.0,
   "rank": 15
  },
  {
   "action": "Assign Cabin Crew C-2907 (day-off callout)",
   "crew_id": "C-2907",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 12500,
   "delay_hours": 0.0,
   "rank": 16
  },
  {
   "action": "Assign Cabin Crew C-3046 (day-off callout)",
   "crew_id": "C-3046",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 12500,
   "delay_hours": 0.0,
   "rank": 17
  },
  {
   "action": "Assign Cabin Crew C-3167 (day-off callout)",
   "crew_id": "C-3167",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 12500,
   "delay_hours": 0.0,
   "rank": 18
  },
  {
   "action": "Assign Cabin Crew C-3545 (day-off callout)",
   "crew_id": "C-3545",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 12500,
   "delay_hours": 0.0,
   "rank": 19
  },
  {
   "action": "Assign Cabin Crew C-3757 (day-off callout)",
   "crew_id": "C-3757",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 12500,
   "delay_hours": 0.0,
   "rank": 20
  },
  {
   "action": "Assign Cabin Crew C-3973 (day-off callout)",
   "crew_id": "C-3973",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 12500,
   "delay_hours": 0.0,
   "rank": 21
  },
  {
   "action": "Assign Cabin Crew C-3988 (day-off callout)",
   "crew_id": "C-3988",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 12500,
   "delay_hours": 0.0,
   "rank": 22
  },
  {
   "action": "Assign Cabin Crew C-4273 (day-off callout)",
   "crew_id": "C-4273",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 12500,
   "delay_hours": 0.0,
   "rank": 23
  },
  {
   "action": "Assign Cabin Crew C-4326 (day-off callout)",
   "crew_id": "C-4326",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 12500,
   "delay_hours": 0.0,
   "rank": 24
  },
  {
   "action": "Assign Cabin Crew C-4395 (day-off callout)",
   "crew_id": "C-4395",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 12500,
   "delay_hours": 0.0,
   "rank": 25
  },
  {
   "action": "Assign Cabin Crew C-4458 (day-off callout)",
   "crew_id": "C-4458",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 12500,
   "delay_hours": 0.0,
   "rank": 26
  },
  {
   "action": "Assign Cabin Crew C-4462 (day-off callout)",
   "crew_id": "C-4462",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 12500,
   "delay_hours": 0.0,
   "rank": 27
  },
  {
   "action": "Assign Cabin Crew C-4531 (day-off callout)",
   "crew_id": "C-4531",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 12500,
   "delay_hours": 0.0,
   "rank": 28
  },
  {
   "action": "Assign Cabin Crew C-4588 (day-off callout)",
   "crew_id": "C-4588",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 12500,
   "delay_hours": 0.0,
   "rank": 29
  },
  {
   "action": "Assign Cabin Crew C-4622 (day-off callout)",
   "crew_id": "C-4622",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 12500,
   "delay_hours": 0.0,
   "rank": 30
  },
  {
   "action": "Assign Cabin Crew C-4679 (day-off callout)",
   "crew_id": "C-4679",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 12500,
   "delay_hours": 0.0,
   "rank": 31
  },
  {
   "action": "Assign Cabin Crew C-4874 (day-off callout)",
   "crew_id": "C-4874",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 12500,
   "delay_hours": 0.0,
   "rank": 32
  },
  {
   "action": "Assign Cabin Crew C-5751 (day-off callout)",
   "crew_id": "C-5751",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 12500,
   "delay_hours": 0.0,
   "rank": 33
  },
  {
   "action": "Assign Cabin Crew C-5795 (day-off callout)",
   "crew_id": "C-5795",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 12500,
   "delay_hours": 0.0,
   "rank": 34
  },
  {
   "action": "Assign Cabin Crew C-5881 (day-off callout)",
   "crew_id": "C-5881",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 12500,
   "delay_hours": 0.0,
   "rank": 35
  },
  {
   "action": "Assign Cabin Crew C-5906 (day-off callout)",
   "crew_id": "C-5906",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 12500,
   "delay_hours": 0.0,
   "rank": 36
  },
  {
   "action": "Assign Cabin Crew C-5994 (day-off callout)",
   "crew_id": "C-5994",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 12500,
   "delay_hours": 0.0,
   "rank": 37
  },
  {
   "action": "Assign Cabin Crew C-1622 (reserve callout + deadhead from DEL (first departure delayed ~7.0h))",
   "crew_id": "C-1622",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 53800,
   "delay_hours": 7.0,
   "rank": 38
  },
  {
   "action": "Assign Cabin Crew C-4280 (day-off callout + deadhead from DEL (first departure delayed ~7.0h))",
   "crew_id": "C-4280",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 56800,
   "delay_hours": 7.0,
   "rank": 39
  },
  {
   "action": "Assign Cabin Crew C-4839 (day-off callout + deadhead from DEL (first departure delayed ~7.0h))",
   "crew_id": "C-4839",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 56800,
   "delay_hours": 7.0,
   "rank": 40
  },
  {
   "action": "Assign Cabin Crew C-5168 (day-off callout + deadhead from DEL (first departure delayed ~7.0h))",
   "crew_id": "C-5168",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 56800,
   "delay_hours": 7.0,
   "rank": 41
  },
  {
   "action": "Assign Cabin Crew C-5444 (day-off callout + deadhead from DEL (first departure delayed ~7.0h))",
   "crew_id": "C-5444",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 56800,
   "delay_hours": 7.0,
   "rank": 42
  },
  {
   "action": "Cancel all 4 flights of the pairing",
   "crew_id": null,
   "legal": true,
   "rules_checked": [],
   "cost_inr": 1000000,
   "delay_hours": 0.0,
   "rank": 43
  }
 ],
 "excluded_candidates": [
  {
   "crew_id": "C-2876",
   "reason": "RULE-REST-04: only -10.75h rest before COVER on 2026-09-19 (rest conflict); double-booked: P-2206 overlaps COVER on 2026-09-19"
  },
  {
   "crew_id": "C-1542",
   "reason": "RULE-REST-04: only -10.75h rest before COVER on 2026-09-19 (rest conflict); double-booked: P-2206 overlaps COVER on 2026-09-19"
  },
  {
   "crew_id": "C-5089",
   "reason": "RULE-REST-04: only -10.75h rest before COVER on 2026-09-19 (rest conflict); double-booked: P-2206 overlaps COVER on 2026-09-19"
  },
  {
   "crew_id": "C-3569",
   "reason": "RULE-REST-04: only -10.75h rest before P-2220 on 2026-09-19 (downstream conflict); double-booked: COVER overlaps P-2220 on 2026-09-19"
  },
  {
   "crew_id": "C-5119",
   "reason": "RULE-REST-04: only -10.75h rest before P-2220 on 2026-09-19 (downstream conflict); double-booked: COVER overlaps P-2220 on 2026-09-19"
  },
  {
   "crew_id": "C-5666",
   "reason": "RULE-REST-04: only -10.75h rest before P-2220 on 2026-09-19 (downstream conflict); double-booked: COVER overlaps P-2220 on 2026-09-19"
  },
  {
   "crew_id": "C-1594",
   "reason": "RULE-QUAL-05: no A320 rating"
  },
  {
   "crew_id": "C-2100",
   "reason": "RULE-QUAL-05: no A320 rating"
  },
  {
   "crew_id": "C-3145",
   "reason": "RULE-QUAL-05: no A320 rating"
  },
  {
   "crew_id": "C-3897",
   "reason": "RULE-QUAL-05: no A320 rating"
  },
  {
   "crew_id": "C-1568",
   "reason": "RULE-QUAL-05: no A320 rating"
  },
  {
   "crew_id": "C-5723",
   "reason": "RULE-QUAL-05: no A320 rating"
  },
  {
   "crew_id": "C-3271",
   "reason": "RULE-REST-04: only 11.25h rest before COVER on 2026-09-19 (rest conflict)"
  },
  {
   "crew_id": "C-3249",
   "reason": "RULE-REST-04: only 11.25h rest before COVER on 2026-09-19 (rest conflict)"
  },
  {
   "crew_id": "C-3619",
   "reason": "RULE-REST-04: only 11.25h rest before COVER on 2026-09-19 (rest conflict)"
  },
  {
   "crew_id": "C-4999",
   "reason": "RULE-REST-04: only -7.25h rest before P-2295 on 2026-09-19 (downstream conflict); double-booked: COVER overlaps P-2295 on 2026-09-19"
  },
  {
   "crew_id": "C-2352",
   "reason": "RULE-REST-04: only -7.25h rest before P-2295 on 2026-09-19 (downstream conflict); double-booked: COVER overlaps P-2295 on 2026-09-19"
  },
  {
   "crew_id": "C-5848",
   "reason": "RULE-REST-04: only -7.25h rest before P-2295 on 2026-09-19 (downstream conflict); double-booked: COVER overlaps P-2295 on 2026-09-19"
  },
  {
   "crew_id": "C-5418",
   "reason": "reserve on-call window 04:00-16:00Z does not cover required report 02:00Z"
  },
  {
   "crew_id": "C-1329",
   "reason": "reserve on-call window 04:00-16:00Z does not cover required report 02:00Z"
  },
  {
   "crew_id": "C-2248",
   "reason": "reserve on-call window 04:00-16:00Z does not cover required report 02:00Z"
  }
 ],
 "expected_choice": {
  "action": "Assign Cabin Crew C-4809 (reserve callout)",
  "crew_id": "C-4809",
  "legal": true,
  "rules_checked": [
   "RULE-FDP-01",
   "RULE-DUTY-02",
   "RULE-FLT-03",
   "RULE-REST-04",
   "RULE-QUAL-05",
   "RULE-CERT-06",
   "RULE-BASE-07"
  ],
  "cost_inr": 9500,
  "delay_hours": 0.0,
  "rank": 1
 }
}
```

</details>

**Last recorded LLM run:** **PARTIAL** — 38/76 atoms, 13 tool call(s), 49.1s — missing: `C-1568`, `C-1569`, `C-1594`, `C-1748`, `C-1873`, `C-1970`, `C-2083`, `C-2100`, `C-2165`, `C-2248`, `C-2252`, `C-2286`, `C-2435`, `C-2751`, `C-2907`, `C-3046`, `C-3167`, `C-3249`, `C-3271`, `C-3545`, `C-3757`, `C-3973`, `C-3988`, `C-4273`, `C-4326`, `C-4395`, `C-4458`, `C-4462`, `C-4531`, `C-4588`, `C-4622`, `C-4679`, `C-4874`, `C-5751`, `C-5795`, `C-5881`, `C-5906`, `C-5994`

#### S6 — Two simultaneous captain sick calls

**Difficulty:** hard  |  **Event type:** `MULTI_SICK`

**Narrative (LLM prompt):** At 00:30Z on 18 Sep, the captains of both VT-DXA (C-3940) and VT-DXB (C-1938) call in sick. One qualified reserve captain's window covers the early reports; the desk must allocate scarce cover across both pairings.

**Event parameters:** `{"events": [{"crew_id": "C-3940", "pairing_id": "P-2205", "reported_utc": "2026-09-18T00:30:00Z"}, {"crew_id": "C-1938", "pairing_id": "P-2212", "reported_utc": "2026-09-18T00:30:00Z"}]}`

**Graded atoms (39):** `C-1017`, `C-1042`, `C-1443`, `C-1526`, `C-1600`, `C-1671`, `C-1938`, `C-2087`, `C-2091`, `C-2143`, `C-2210`, `C-2221`, `C-3187`, `C-3231`, `C-3305`, `C-3310`, `C-3315`, `C-3721`, `C-3940`, `C-3983`, `C-5392`, `C-5566`, `C-5647`, `C-5820`, `C-5837`, `P-2205`, `P-2212`, `P-2219`, `P-2293`, `RULE-QUAL-05`, `RULE-REST-04`, `1000000`, `18500`, `24000`, `42500`, `57400`, `6.0`, `6.5`, `60100`

<details><summary>Answer key</summary>

```json
{
 "options_dxa": [
  {
   "action": "Assign Captain C-3305 (reserve callout)",
   "crew_id": "C-3305",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 18500,
   "delay_hours": 0.0,
   "rank": 1
  },
  {
   "action": "Assign Captain C-1017 (day-off callout)",
   "crew_id": "C-1017",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 24000,
   "delay_hours": 0.0,
   "rank": 2
  },
  {
   "action": "Assign Captain C-1042 (day-off callout)",
   "crew_id": "C-1042",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 24000,
   "delay_hours": 0.0,
   "rank": 3
  },
  {
   "action": "Assign Captain C-1526 (day-off callout)",
   "crew_id": "C-1526",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 24000,
   "delay_hours": 0.0,
   "rank": 4
  },
  {
   "action": "Assign Captain C-2087 (day-off callout)",
   "crew_id": "C-2087",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 24000,
   "delay_hours": 0.0,
   "rank": 5
  },
  {
   "action": "Assign Captain C-2143 (day-off callout)",
   "crew_id": "C-2143",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 24000,
   "delay_hours": 0.0,
   "rank": 6
  },
  {
   "action": "Assign Captain C-3187 (day-off callout)",
   "crew_id": "C-3187",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 24000,
   "delay_hours": 0.0,
   "rank": 7
  },
  {
   "action": "Assign Captain C-3983 (day-off callout)",
   "crew_id": "C-3983",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 24000,
   "delay_hours": 0.0,
   "rank": 8
  },
  {
   "action": "Assign Captain C-5647 (day-off callout)",
   "crew_id": "C-5647",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 24000,
   "delay_hours": 0.0,
   "rank": 9
  },
  {
   "action": "Assign Captain C-5820 (day-off callout)",
   "crew_id": "C-5820",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 24000,
   "delay_hours": 0.0,
   "rank": 10
  },
  {
   "action": "Assign Captain C-5837 (day-off callout)",
   "crew_id": "C-5837",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 24000,
   "delay_hours": 0.0,
   "rank": 11
  },
  {
   "action": "Assign Captain C-2210 (reserve callout + deadhead from DEL (first departure delayed ~6.5h))",
   "crew_id": "C-2210",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 60100,
   "delay_hours": 6.5,
   "rank": 12
  },
  {
   "action": "Cancel all 4 flights of the pairing",
   "crew_id": null,
   "legal": true,
   "rules_checked": [],
   "cost_inr": 1000000,
   "delay_hours": 0.0,
   "rank": 13
  }
 ],
 "excluded_dxa": [
  {
   "crew_id": "C-3310",
   "reason": "reserve on-call window 06:00-18:00Z does not cover required report 01:30Z"
  },
  {
   "crew_id": "C-3315",
   "reason": "reserve on-call window 03:00-15:00Z does not cover required report 01:30Z"
  },
  {
   "crew_id": "C-2091",
   "reason": "RULE-QUAL-05: no A320 rating"
  },
  {
   "crew_id": "C-1938",
   "reason": "RULE-REST-04: only -10.75h rest before P-2212 on 2026-09-18 (downstream conflict); double-booked: COVER overlaps P-2212 on 2026-09-18"
  },
  {
   "crew_id": "C-1443",
   "reason": "RULE-REST-04: only -10.25h rest before P-2219 on 2026-09-18 (downstream conflict); double-booked: COVER overlaps P-2219 on 2026-09-18"
  },
  {
   "crew_id": "C-1671",
   "reason": "RULE-QUAL-05: no A320 rating"
  },
  {
   "crew_id": "C-1600",
   "reason": "RULE-QUAL-05: no A320 rating"
  },
  {
   "crew_id": "C-3231",
   "reason": "RULE-QUAL-05: no A320 rating"
  },
  {
   "crew_id": "C-2221",
   "reason": "RULE-QUAL-05: no A320 rating"
  },
  {
   "crew_id": "C-3721",
   "reason": "RULE-QUAL-05: no A320 rating"
  },
  {
   "crew_id": "C-5392",
   "reason": "RULE-QUAL-05: no A320 rating"
  },
  {
   "crew_id": "C-5566",
   "reason": "RULE-REST-04: only 10.0h rest before COVER on 2026-09-18 (rest conflict); RULE-REST-04: only -8.75h rest before P-2293 on 2026-09-18 (downstream conflict); double-booked: COVER overlaps P-2293 on 2026-09-18"
  }
 ],
 "options_dxb": [
  {
   "action": "Assign Captain C-3305 (reserve callout)",
   "crew_id": "C-3305",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 18500,
   "delay_hours": 0.0,
   "rank": 1
  },
  {
   "action": "Assign Captain C-1017 (day-off callout)",
   "crew_id": "C-1017",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 24000,
   "delay_hours": 0.0,
   "rank": 2
  },
  {
   "action": "Assign Captain C-1042 (day-off callout)",
   "crew_id": "C-1042",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 24000,
   "delay_hours": 0.0,
   "rank": 3
  },
  {
   "action": "Assign Captain C-1526 (day-off callout)",
   "crew_id": "C-1526",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 24000,
   "delay_hours": 0.0,
   "rank": 4
  },
  {
   "action": "Assign Captain C-2087 (day-off callout)",
   "crew_id": "C-2087",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 24000,
   "delay_hours": 0.0,
   "rank": 5
  },
  {
   "action": "Assign Captain C-2143 (day-off callout)",
   "crew_id": "C-2143",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 24000,
   "delay_hours": 0.0,
   "rank": 6
  },
  {
   "action": "Assign Captain C-3187 (day-off callout)",
   "crew_id": "C-3187",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 24000,
   "delay_hours": 0.0,
   "rank": 7
  },
  {
   "action": "Assign Captain C-3983 (day-off callout)",
   "crew_id": "C-3983",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 24000,
   "delay_hours": 0.0,
   "rank": 8
  },
  {
   "action": "Assign Captain C-5647 (day-off callout)",
   "crew_id": "C-5647",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 24000,
   "delay_hours": 0.0,
   "rank": 9
  },
  {
   "action": "Assign Captain C-5820 (day-off callout)",
   "crew_id": "C-5820",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 24000,
   "delay_hours": 0.0,
   "rank": 10
  },
  {
   "action": "Assign Captain C-5837 (day-off callout)",
   "crew_id": "C-5837",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 24000,
   "delay_hours": 0.0,
   "rank": 11
  },
  {
   "action": "Assign Captain C-2210 (reserve callout + deadhead from DEL (first departure delayed ~6.0h))",
   "crew_id": "C-2210",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 57400,
   "delay_hours": 6.0,
   "rank": 12
  },
  {
   "action": "Cancel all 4 flights of the pairing",
   "crew_id": null,
   "legal": true,
   "rules_checked": [],
   "cost_inr": 1000000,
   "delay_hours": 0.0,
   "rank": 13
  }
 ],
 "excluded_dxb": [
  {
   "crew_id": "C-3310",
   "reason": "reserve on-call window 06:00-18:00Z does not cover required report 02:00Z"
  },
  {
   "crew_id": "C-3315",
   "reason": "reserve on-call window 03:00-15:00Z does not cover required report 02:00Z"
  },
  {
   "crew_id": "C-2091",
   "reason": "RULE-QUAL-05: no A320 rating"
  },
  {
   "crew_id": "C-3940",
   "reason": "RULE-REST-04: only -10.75h rest before COVER on 2026-09-18 (rest conflict); double-booked: P-2205 overlaps COVER on 2026-09-18"
  },
  {
   "crew_id": "C-1443",
   "reason": "RULE-REST-04: only -10.75h rest before P-2219 on 2026-09-18 (downstream conflict); double-booked: COVER overlaps P-2219 on 2026-09-18"
  },
  {
   "crew_id": "C-1671",
   "reason": "RULE-QUAL-05: no A320 rating"
  },
  {
   "crew_id": "C-1600",
   "reason": "RULE-QUAL-05: no A320 rating"
  },
  {
   "crew_id": "C-3231",
   "reason": "RULE-QUAL-05: no A320 rating"
  },
  {
   "crew_id": "C-2221",
   "reason": "RULE-QUAL-05: no A320 rating"
  },
  {
   "crew_id": "C-3721",
   "reason": "RULE-QUAL-05: no A320 rating"
  },
  {
   "crew_id": "C-5392",
   "reason": "RULE-QUAL-05: no A320 rating"
  },
  {
   "crew_id": "C-5566",
   "reason": "RULE-REST-04: only 10.5h rest before COVER on 2026-09-18 (rest conflict); RULE-REST-04: only -9.25h rest before P-2293 on 2026-09-18 (downstream conflict); double-booked: COVER overlaps P-2293 on 2026-09-18"
  }
 ],
 "optimal_joint_plan": {
  "total_cost_inr": 42500,
  "assign_dxa": {
   "action": "Assign Captain C-3305 (reserve callout)",
   "crew_id": "C-3305",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 18500,
   "delay_hours": 0.0,
   "rank": 1
  },
  "assign_dxb": {
   "action": "Assign Captain C-1017 (day-off callout)",
   "crew_id": "C-1017",
   "legal": true,
   "rules_checked": [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07"
   ],
   "cost_inr": 24000,
   "delay_hours": 0.0,
   "rank": 2
  }
 },
 "note": "The same crew member cannot cover both pairings; the optimal plan minimises total cost across both. Equal-cost mirror assignments (swapping which pairing each candidate covers) are equally correct."
}
```

</details>

**Last recorded LLM run:** **PARTIAL** — 0/39 atoms, 4 tool call(s), 34.4s — missing: `1000000`, `18500`, `24000`, `42500`, `57400`, `6.0`, `6.5`, `60100`, `C-1017`, `C-1042`, `C-1443`, `C-1526`, `C-1600`, `C-1671`, `C-1938`, `C-2087`, `C-2091`, `C-2143`, `C-2210`, `C-2221`, `C-3187`, `C-3231`, `C-3305`, `C-3310`, `C-3315`, `C-3721`, `C-3940`, `C-3983`, `C-5392`, `C-5566`, `C-5647`, `C-5820`, `C-5837`, `P-2205`, `P-2212`, `P-2219`, `P-2293`, `RULE-QUAL-05`, `RULE-REST-04`

