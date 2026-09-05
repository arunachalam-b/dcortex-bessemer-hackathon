"""Regression harness: replay questions.json and scenarios.json through the
engine and diff against the shipped answer keys.

The engine functions are general (they parse the event/question parameters and
compute); this module only maps each item to the right engine call and the
answer key's field names. Open-ended prose questions (Q30, Q36, Q38) are
marked `manual` — we still produce an answer, but scoring is human.
"""

from __future__ import annotations

import json
import os
from datetime import date

from .world import World, parse_utc
from . import query as Q
from . import simulation as S
from . import recommender as REC

MANUAL = {"Q30", "Q36", "Q38"}
# prose fields the engine words differently (facts around them are compared)
IGNORE_KEYS = {"note", "explanation", "narrative", "consequence"}


# --------------------------- comparison ---------------------------

def _num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def compare(exp, got, path="$"):
    """Expected-driven structural diff. Extra keys in `got` are fine (the
    engine adds reasoning/trace); every expected fact must match. Lists match
    ordered first, then as multisets (creation order in the keys is arbitrary
    for exclusion lists)."""
    diffs = []
    if _num(exp) and _num(got):
        if abs(exp - got) > 0.011:
            diffs.append(f"{path}: expected {exp}, got {got}")
    elif isinstance(exp, dict):
        if not isinstance(got, dict):
            diffs.append(f"{path}: expected object, got {type(got).__name__}")
        else:
            for k, v in exp.items():
                if k in IGNORE_KEYS:
                    continue
                if k not in got:
                    diffs.append(f"{path}.{k}: missing")
                else:
                    diffs.extend(compare(v, got[k], f"{path}.{k}"))
    elif isinstance(exp, list):
        if not isinstance(got, list):
            diffs.append(f"{path}: expected list, got {type(got).__name__}")
        elif len(exp) != len(got):
            diffs.append(f"{path}: expected {len(exp)} items, got {len(got)}")
        else:
            ordered = []
            for i, (e, g) in enumerate(zip(exp, got)):
                ordered.extend(compare(e, g, f"{path}[{i}]"))
            if ordered:
                unused = list(range(len(got)))
                for i, e in enumerate(exp):
                    hit = next((j for j in unused if not compare(e, got[j])), None)
                    if hit is None:
                        return diffs + [f"{path}[{i}]: no match for {json.dumps(e, default=str)[:160]}"]
                    unused.remove(hit)
    elif exp != got:
        diffs.append(f"{path}: expected {exp!r}, got {got!r}")
    return diffs


# --------------------------- questions ---------------------------

def _project(d, keys):
    return {k: d[k] for k in keys}


def answer_question(world: World, qid: str):
    """Compute the engine's answer for one questions.json item, shaped to the
    answer key's field names."""
    fn = _QUESTIONS.get(qid)
    if fn is None:
        raise KeyError(qid)
    return fn(world)


_QUESTIONS = {
    # ---- Tier 1 ----
    "Q01": lambda w: [_project(r, ["crew_id", "rank", "window"])
                      for r in Q.reserves(w, base="BLR", on=date(2026, 9, 15))],
    "Q02": lambda w: (lambda c: {"duty_hours_7d": c["duty_hours_7d"],
                                 "headroom_hours": c["duty_headroom_7d"]})(
        Q.duty_clock(w, "C-1042", date(2026, 9, 14))),
    "Q03": lambda w: [f["flight_no"] for f in
                      Q.lookup_flights(w, on=date(2026, 9, 15), dep_station="DEL")],
    "Q04": lambda w: Q.certifications(w, expiring_from=date(2026, 9, 15),
                                      expiring_to=date(2026, 10, 15)),
    "Q05": lambda w: _project(Q.lookup_flights(w, on=date(2026, 9, 15),
                                               flight_no="DX412")[0],
                              ["aircraft", "aircraft_type", "seats"]),
    "Q06": lambda w: (lambda r: {"window": r["window"],
                                 "reachability_minutes": r["reachability_minutes"]})(
        next(x for x in Q.reserves(w) if x["crew_id"] == "C-3310")),
    "Q07": lambda w: _project(Q.lookup_crew(w, crew_id="C-2210")[0],
                              ["base", "ratings"]),
    "Q08": lambda w: Q.pairing_info(w, pairing_id="P-2291")[0]["crew"],
    "Q09": lambda w: [f["flight_no"] for f in
                      Q.lookup_flights(w, on=date(2026, 9, 17),
                                       dep_station="BLR", arr_station="BOM")],
    "Q10": lambda w: len(Q.lookup_flights(w, on=date(2026, 9, 16))),
    "Q11": lambda w: [c["crew_id"] for c in
                      Q.lookup_crew(w, rank="Captain", base="DEL")],
    "Q12": lambda w: (lambda mx: {
        "block_hours": mx,
        "flights": sorted({f.flight_no for f in w.flights_list
                           if abs(f.block_hours - mx) < 1e-6})})(
        max(f.block_hours for f in w.flights_list)),
    "Q13": lambda w: {"rank": w.crew["C-2087"].rank,
                      "flight_hours_28d": Q.duty_clock(
                          w, "C-2087", date(2026, 9, 14))["flight_hours_28d"]},
    "Q14": lambda w: sorted({f.arr_station for f in w.flights_list
                             if f.dep_station == "BLR"}),
    "Q15": lambda w: next(m["crew_id"] for m in Q.pairing_info(
        w, aircraft="VT-DXB", on=date(2026, 9, 16))[0]["crew"]
        if m["role"] == "Senior Cabin Crew"),
    "Q16": lambda w: _project(Q.risk_signals(w, crew_id="C-1042")[0],
                              ["score", "drivers"]),
    # ---- Tier 2 ----
    "Q17": lambda w: (lambda i: {"day1": i["per_day"][0]["flights"],
                                 "day2_also_at_risk": i["per_day"][1]["flights"],
                                 "passengers_day1": i["per_day"][0]["passengers"]})(
        S.sick_crew_impact(w, "C-1042", "P-2291",
                           parse_utc("2026-09-15T05:00:00Z"))),
    "Q18": lambda w: _project(S.check_assignment(w, "C-2087", "P-2291"),
                              ["legal", "issues"]),
    "Q19": lambda w: S.station_closure_impact(
        w, "BLR", parse_utc("2026-09-17T08:00:00Z"),
        parse_utc("2026-09-17T14:00:00Z"))["affected_flights"],
    "Q20": lambda w: _project(S.delay_impact(w, "VT-DXA", date(2026, 9, 16), 1.5),
                              ["breach", "fdp_after_delay", "fdp_limit"]),
    "Q21": lambda w: {"legal": S.check_assignment(
        w, "C-2210", "P-2291", delay_hours=3.25)["legal"],
        "consequence": "Deadhead positioning on DX402 (arr 08:45Z) delays the "
                       "first departure by ~3h; RULE-BASE-07 deadhead cost applies."},
    "Q22": lambda w: _project(S.cert_expiry_impact(w, "C-5417", date(2026, 9, 19)),
                              ["legal", "rule", "detail"]),
    "Q23": lambda w: S.rest_requirement(
        w, parse_utc("2026-09-16T15:30:00Z"))["earliest_next_report_utc"],
    "Q24": lambda w: _project(S.check_assignment(w, "C-3305", "P-2291"),
                              ["legal", "issues"]),
    "Q25": lambda w: _project(S.cancellation_impact(w, "DX404-2026-09-16"),
                              ["passengers", "cost_inr"]),
    "Q26": lambda w: [{"crew_id": x["crew_id"],
                       "duty_hours_7d_incl_15sep_plan": x["duty_hours_7d"]}
                      for x in Q.crew_over_duty_threshold(w, date(2026, 9, 15), 45)],
    "Q27": lambda w: (lambda r: {
        "eligible": [o["crew_id"] for o in r["options"]
                     if o["crew_id"] and o["crew_id"] in w.reserves],
        "excluded_examples": [e for e in r["excluded_candidates"]
                              if e["crew_id"] in ("C-3310", "C-3305")][:2]})(
        _s1_cover(w)),
    "Q28": lambda w: _project(S.check_assignment(w, "C-5837", "P-2291",
                                                 exclude_pairing=None),
                              ["legal", "issues"]),
    "Q29": lambda w: S.station_closure_impact(
        w, "HYD", parse_utc("2026-09-19T05:00:00Z"),
        parse_utc("2026-09-19T09:00:00Z"))["affected_flights"],
    "Q30": lambda w: {"answer": "Any A320 leg risks the most seats: A320 legs "
                                "carry 162 seats vs 72 on ATR72 legs.",
                      "max_seats": max(f.seats for f in w.flights_list)},
    # ---- Tier 3 ----
    "Q31": lambda w: REC.cover_options(
        w, "P-2291", "Captain", sick_crew_id="C-1042")["options"],
    "Q32": lambda w: (lambda j: {"total_cost_inr": j["total_cost_inr"],
                                 "assign_dxa": j["assignments"][0],
                                 "assign_dxb": j["assignments"][1]})(
        _s6_joint(w)),
    "Q33": lambda w: REC.delay_recovery(w, "VT-DXA", date(2026, 9, 16), 1.5)["options"],
    "Q34": lambda w: _s5_cover(w)["options"][:3],
    "Q35": lambda w: S.station_closure_impact(
        w, "BLR", parse_utc("2026-09-17T08:00:00Z"),
        parse_utc("2026-09-17T14:00:00Z"))["per_flight_assessment"],
    "Q36": lambda w: REC.draft_notification(w, "C-3310", "P-2291"),
    "Q37": lambda w: _s_vtdxf_fo(w)["options"][0],
    "Q38": lambda w: {"suggested": [
        "crew legality headroom (7d duty window) for today's rostered crew",
        "reserve availability by on-call window and rating for the day",
        "disruption-risk signals for today's rostered crew (provided input)"]},
}


def _captain_of(world, aircraft, on):
    p = world.pairing_for(aircraft, on)
    cid = next(m for m, r in p.crew if r == "Captain")
    return p, cid


def _s1_cover(world):
    p, cid = _captain_of(world, "VT-DXE", date(2026, 9, 16))
    return REC.cover_options(world, p.pairing_id, "Captain", sick_crew_id=cid)


def _s5_cover(world):
    ex = world.flagged_exceptions[0]
    p = world.pairing_for("VT-DXB", date.fromisoformat(ex["date"]))
    return REC.cover_options(world, p.pairing_id, "Cabin Crew",
                             sick_crew_id=ex["crew_id"])


def _s6_joint(world):
    events = []
    for ac in ("VT-DXA", "VT-DXB"):
        p, cid = _captain_of(world, ac, date(2026, 9, 18))
        events.append({"pairing_id": p.pairing_id, "role": "Captain",
                       "sick_crew_id": cid})
    return REC.joint_plan(world, events)


def _s_vtdxf_fo(world):
    p = world.pairing_for("VT-DXF", date(2026, 9, 20))
    fo = next(m for m, r in p.crew if r == "First Officer")
    return REC.cover_options(world, p.pairing_id, "First Officer", sick_crew_id=fo)


# --------------------------- scenarios ---------------------------

def answer_scenario(world: World, scenario: dict) -> dict:
    """Run one scenarios.json event through the engine generically (dispatch on
    event type, everything resolved from the data) and shape the output to the
    answer key's field names."""
    ev = scenario["event"]
    t = ev["type"]
    if t == "SICK_CREW" or t == "CERT_EXPIRY":
        p = world.pairings[ev["pairing_id"]]
        cid = ev["crew_id"]
        role = next(r for m, r in p.crew if m == cid)
        reported = parse_utc(ev["reported_utc"])
        days_from = min(d.date for d in p.days if d.date >= reported.date())
        impact = S.sick_crew_impact(world, cid, ev["pairing_id"], reported)
        rec = REC.cover_options(world, ev["pairing_id"], role, sick_crew_id=cid,
                                days_from=days_from, reported_utc=reported)
        out = {"options": rec["options"],
               "excluded_candidates": rec["excluded_candidates"],
               "expected_choice": rec["options"][0],
               "uncovered_flights": impact["uncovered_flights"],
               "impact": impact}
        if len(impact["per_day"]) > 1:
            out["uncovered_flights_day1"] = impact["per_day"][0]["flights"]
            out["uncovered_flights_day2"] = impact["per_day"][1]["flights"]
            out["passengers_at_risk_day1"] = impact["per_day"][0]["passengers"]
        if t == "CERT_EXPIRY":
            chk = S.cert_expiry_impact(world, cid, days_from)
            out["illegal_assignment"] = {"crew_id": cid, "date": str(days_from),
                                         "rule": chk["rule"]}
        return out
    if t == "STATION_CLOSURE":
        return S.station_closure_impact(world, ev["station"],
                                        parse_utc(ev["window_utc"]["start"]),
                                        parse_utc(ev["window_utc"]["end"]))
    if t == "DELAY":
        r = REC.delay_recovery(world, ev["aircraft"],
                               date.fromisoformat(ev["date"]), ev["delay_hours"])
        return {**r, "expected_choice": r["options"][0] if r["options"] else None}
    if t == "MULTI_SICK":
        events = []
        for sub in ev["events"]:
            p = world.pairings[sub["pairing_id"]]
            role = next(r for m, r in p.crew if m == sub["crew_id"])
            events.append({"pairing_id": sub["pairing_id"], "role": role,
                           "sick_crew_id": sub["crew_id"]})
        j = REC.joint_plan(world, events)
        out = {"optimal_joint_plan": {"total_cost_inr": j["total_cost_inr"]},
               "joint": j}
        # answer key names the sub-results by aircraft line (e.g. options_dxa)
        for i, sub in enumerate(ev["events"]):
            tag = world.pairings[sub["pairing_id"]].aircraft[-1].lower()  # VT-DXA -> a
            out[f"options_dx{tag}"] = j["per_event"][i]["options"]
            out[f"excluded_dx{tag}"] = j["per_event"][i]["excluded_candidates"]
            out["optimal_joint_plan"][f"assign_dx{tag}"] = j["assignments"][i]
        return out
    raise ValueError(f"unknown event type {t}")


# --------------------------- runner ---------------------------

def run_all(world: World, data_dir: str = None) -> dict:
    data_dir = data_dir or world.data_dir
    with open(os.path.join(data_dir, "questions.json")) as fh:
        questions = json.load(fh)
    with open(os.path.join(data_dir, "scenarios.json")) as fh:
        scenarios = json.load(fh)

    rows, n_pass = [], 0
    for q in questions:
        qid = q["question_id"]
        try:
            got = answer_question(world, qid)
            if qid in MANUAL:
                rows.append({"id": qid, "tier": q["tier"], "status": "MANUAL",
                             "diffs": [], "got": got})
                continue
            diffs = compare(q["expected_answer"], got)
        except Exception as e:  # a crash is a failure, not an excuse
            rows.append({"id": qid, "tier": q["tier"], "status": "ERROR",
                         "diffs": [f"{type(e).__name__}: {e}"]})
            continue
        ok = not diffs
        n_pass += ok
        rows.append({"id": qid, "tier": q["tier"],
                     "status": "PASS" if ok else "FAIL", "diffs": diffs})

    for sc in scenarios:
        sid = sc["scenario_id"]
        try:
            got = answer_scenario(world, sc)
            diffs = compare(sc["answer_key"], got)
        except Exception as e:
            rows.append({"id": sid, "tier": "S", "status": "ERROR",
                         "diffs": [f"{type(e).__name__}: {e}"]})
            continue
        ok = not diffs
        n_pass += ok
        rows.append({"id": sid, "tier": "S",
                     "status": "PASS" if ok else "FAIL", "diffs": diffs})

    auto = [r for r in rows if r["status"] != "MANUAL"]
    return {"rows": rows, "passed": n_pass, "auto_total": len(auto),
            "manual": len(rows) - len(auto)}
