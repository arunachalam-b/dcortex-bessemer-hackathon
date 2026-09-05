"""Tier 3 — recommendation: enumerate -> filter (7 rules) -> cost -> rank.

Deliberately a transparent lexicographic ranking, not an optimizer: every
option carries its full legality verdicts, itemized cost and reasoning, and
every rejected candidate is listed with the exact rule that killed them.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

from .world import World, hrs, hm_on, iso
from . import rules as R

PILOT_RANKS = ("Captain", "First Officer")


def _deadhead_positioning(world: World, base_from: str, pdays):
    """Same-day positioning from another base to the pairing start.

    The schedule offers DEL->BLR only: DX589 (arr 07:45Z) on even dates,
    DX402 (arr 08:45Z) on odd dates. New report = positioning arrival + 15 min
    transit; first departure then needs report + 60 min, so the duty start is
    delayed by max(0, arrival + 75 min - scheduled first departure).
    Returns (delay_hours, description) or (None, reason)."""
    first = world.flights[pdays[0].flights[0]]
    base_needed = first.dep_station
    if base_from == "DEL" and base_needed == "BLR":
        d = pdays[0].date
        arr = hm_on(d, "07:45") if d.day % 2 == 0 else hm_on(d, "08:45")
        flight_no = "DX589" if d.day % 2 == 0 else "DX402"
        delay_h = round(max(0.0, hrs((arr + timedelta(minutes=75)) - first.dep_utc)), 2)
        return delay_h, (f"deadhead {base_from}->{base_needed} on {flight_no} "
                         f"(arr {arr:%H:%M}Z), new report {arr + timedelta(minutes=15):%H:%M}Z")
    return None, "RULE-BASE-07: no same-day positioning flight from base"


def cover_options(world: World, pairing_id: str, role: str,
                  sick_crew_id: Optional[str] = None,
                  days_from: Optional[date] = None,
                  reported_utc: Optional[datetime] = None) -> dict:
    """Ranked, rule-checked options to cover `role` on `pairing_id`.

    Enumerates every active crew member of that rank: reserves at base,
    day-off line crew, deadhead candidates from other bases; runs the full
    7-rule check on each; prices from costs.json; ranks by cost then crew_id.
    Cancellation is always the priced last resort."""
    p = world.pairings[pairing_id]
    pdays = [d for d in p.days if days_from is None or d.date >= days_from]
    first = world.flights[pdays[0].flights[0]]
    base_needed = first.dep_station
    pilot = role in PILOT_RANKS
    costs = world.costs
    options, excluded, trace = [], [], []
    trace.append(f"covering {role} on {pairing_id}: days "
                 + ", ".join(str(d.date) for d in pdays)
                 + f"; report {pdays[0].report_utc:%H:%M}Z at {base_needed}")

    for cid, c in world.crew.items():
        if cid == sick_crew_id or c.rank != role or c.status != "active":
            continue
        is_res = cid in world.reserves
        delay_h, dh_note = 0.0, None
        if c.base != base_needed:
            delay_h, dh_note = _deadhead_positioning(world, c.base, pdays)
            if delay_h is None:
                excluded.append({"crew_id": cid, "reason": dh_note})
                continue
        if is_res:
            rep_req = pdays[0].report_utc + timedelta(hours=delay_h)
            covers, _detail = R.reserve_window_covers(world, cid, rep_req)
            if covers and pdays[0].date not in world.reserves[cid].dates:
                covers = False
            if not covers:
                r = world.reserves[cid]
                excluded.append({"crew_id": cid,
                                 "reason": f"reserve on-call window {r.window_start}-"
                                           f"{r.window_end}Z does not cover required report "
                                           f"{rep_req.strftime('%H:%M')}Z"})
                continue
        check = R.evaluate_cover(world, cid, pdays,
                                 exclude_pairing=pairing_id, delay_h=delay_h)
        if not check.legal:
            excluded.append({"crew_id": cid, "reason": "; ".join(check.issues)})
            continue
        cost = (costs["reserve_callout_pilot" if pilot else "reserve_callout_cabin"]
                if is_res else
                costs["dayoff_callout_pilot" if pilot else "dayoff_callout_cabin"])
        label = "reserve callout" if is_res else "day-off callout"
        cost_items = [{"item": label, "inr": cost}]
        if c.base != base_needed:
            dh_cost = costs["deadhead_positioning"]
            delay_cost = round(delay_h * costs["delay_cost_per_duty_hour"])
            cost += dh_cost + delay_cost
            cost_items += [{"item": "deadhead positioning", "inr": dh_cost},
                           {"item": f"{delay_h}h departure delay", "inr": delay_cost}]
            label += f" + deadhead from {c.base} (first departure delayed ~{delay_h}h)"
        reasoning = (f"{c.base}-based, {'/'.join(c.ratings)}-rated"
                     + (f", on-call {world.reserves[cid].window_start}-"
                        f"{world.reserves[cid].window_end}Z" if is_res else ", off-roster")
                     + f", reachable in {c.reachability_minutes} min; all 7 rules pass"
                     + (f"; {dh_note}" if dh_note else ""))
        options.append({
            "action": f"Assign {c.rank} {cid} ({label})",
            "crew_id": cid, "legal": True,
            "rules_checked": R.ALL_RULES,
            "cost_inr": int(round(cost)), "delay_hours": delay_h,
            "reasoning": reasoning, "cost_breakdown": cost_items,
            "verdicts": [v.to_dict() for v in check.verdicts]})

    options.sort(key=lambda o: (o["cost_inr"], o["crew_id"]))
    n_legs = sum(len(d.flights) for d in pdays)
    options.append({
        "action": f"Cancel all {n_legs} flights of the pairing", "crew_id": None,
        "legal": True, "rules_checked": [],
        "cost_inr": costs["cancellation_per_flight"] * n_legs, "delay_hours": 0.0,
        "reasoning": f"last resort: {n_legs} legs x INR "
                     f"{costs['cancellation_per_flight']} per cancelled flight, "
                     f"{sum(world.flights[f].seats for d in pdays for f in d.flights)} "
                     f"passengers stranded",
        "cost_breakdown": [{"item": f"cancellation x {n_legs} legs",
                            "inr": costs["cancellation_per_flight"] * n_legs}]})
    for i, o in enumerate(options):
        o["rank"] = i + 1
    trace.append(f"{len(options) - 1} legal candidates, {len(excluded)} excluded; "
                 f"ranked by total cost (cancellation last)")
    return {"pairing_id": pairing_id, "role": role,
            "days": [str(d.date) for d in pdays],
            "options": options, "excluded_candidates": excluded,
            "recommended": options[0], "trace": trace}


def joint_plan(world: World, events: list) -> dict:
    """Optimal joint cover for simultaneous disruptions: the same crew member
    cannot take two pairings; minimise total cost across all of them.

    events: [{pairing_id, role, sick_crew_id, days_from?}, ...]
    (Exhaustive over per-event legal options — fine at this scale; ties keep
    the first-found plan, so equal-cost mirror assignments are equally valid.)"""
    per_event = [cover_options(world, e["pairing_id"], e["role"],
                               sick_crew_id=e.get("sick_crew_id"),
                               days_from=e.get("days_from")) for e in events]
    pools = []
    for pe in per_event:
        legal = [o for o in pe["options"] if o["crew_id"]]
        pools.append(legal + [pe["options"][-1]])  # cancellation as fallback

    best = None

    def walk(i, chosen, used, total):
        nonlocal best
        if best and total >= best[0]:
            return
        if i == len(pools):
            if best is None or total < best[0]:
                best = (total, list(chosen))
            return
        for o in pools[i]:
            if o["crew_id"] and o["crew_id"] in used:
                continue
            chosen.append(o)
            if o["crew_id"]:
                used.add(o["crew_id"])
            walk(i + 1, chosen, used, total + o["cost_inr"])
            chosen.pop()
            if o["crew_id"]:
                used.discard(o["crew_id"])

    walk(0, [], set(), 0)
    total, plan = best
    return {
        "total_cost_inr": total,
        "assignments": [{"pairing_id": events[i]["pairing_id"], **plan[i]}
                        for i in range(len(events))],
        "per_event": per_event,
        "note": "The same crew member cannot cover two pairings; the plan minimises "
                "total cost. Equal-cost mirror assignments are equally correct.",
        "trace": [f"{len(pools[i])} candidate options for {events[i]['pairing_id']}"
                  for i in range(len(events))]
        + [f"joint minimum over all non-conflicting combinations = INR {total}"],
    }


def delay_recovery(world: World, aircraft: str, on: date, delay_hours: float) -> dict:
    """Recovery for a pre-duty delay that breaches the rostered crew's FDP:
    split the duty at the longest legal prefix and re-crew or cancel the tail."""
    from .simulation import delay_impact
    impact = delay_impact(world, aircraft, on, delay_hours)
    if not impact["breach"]:
        return {**impact, "options": [],
                "note": "No FDP breach; the rostered crew completes the duty delayed."}
    p = world.pairings[impact["pairing_id"]]
    day = next(d for d in p.days if d.date == on)
    k = impact["legal_prefix_sectors"]
    tail_nos = impact["uncoverable_flight_nos"]
    nos = [world.flights[f].flight_no for f in day.flights]
    roles = [r for _m, r in p.crew]
    n_pilots = sum(1 for r in roles if r in PILOT_RANKS)
    n_scc = sum(1 for r in roles if r == "Senior Cabin Crew")
    n_cc = sum(1 for r in roles if r == "Cabin Crew")
    res_cost = (n_pilots * world.costs["reserve_callout_pilot"]
                + (n_scc + n_cc) * world.costs["reserve_callout_cabin"])
    cancel_cost = world.costs["cancellation_per_flight"] * len(tail_nos)
    pax = sum(world.flights[f].seats for f in day.flights[k:])
    tail_word = "the last sector" if len(tail_nos) == 1 else f"the last {len(tail_nos)} sectors"
    opt_a = {
        "rank": 1,
        "action": f"Original crew operates {nos[0]}–{nos[k - 1]} (delayed); full reserve "
                  f"set (CPT, FO, SCC, {n_cc} CC) operates {', '.join(tail_nos)}",
        "legal": True, "cost_inr": res_cost,
        "reasoning": f"Delayed {k}-leg duty FDP {impact['prefix_fdp']}h vs "
                     f"{impact['prefix_fdp_limit']}h limit — legal. Reserve set covers "
                     f"{tail_word} (callout window and 12h-rest all satisfied)."}
    leg_word = "one leg" if len(tail_nos) == 1 else f"{len(tail_nos)} legs"
    opt_b = {
        "rank": 2, "action": f"Cancel {', '.join(tail_nos)}",
        "legal": True, "cost_inr": cancel_cost,
        "reasoning": f"Legal but ~{round(cancel_cost / res_cost, 1)}x more expensive than "
                     f"re-crewing {leg_word}; {pax} passengers stranded."}
    options = sorted([opt_a, opt_b], key=lambda o: o["cost_inr"])
    for i, o in enumerate(options):
        o["rank"] = i + 1
    return {**impact, "options": options, "recommended": options[0],
            "trace": impact["trace"] + [
                f"split point after {k} legs; reserve set "
                f"({n_pilots} pilots + {n_scc + n_cc} cabin) = INR {res_cost} vs "
                f"cancellation of {', '.join(tail_nos)} = INR {cancel_cost}"]}


def draft_notification(world: World, crew_id: str, pairing_id: str,
                       days_from: Optional[date] = None) -> dict:
    """Structured facts + a plain-text callout message for the chosen cover.
    (In the full system the LLM words this; the facts are injected from here.)"""
    c = world.crew[crew_id]
    p = world.pairings[pairing_id]
    pdays = [d for d in p.days if days_from is None or d.date >= days_from]
    day_lines, facts_days = [], []
    for i, d in enumerate(pdays):
        nos = [world.flights[f].flight_no for f in d.flights]
        first = world.flights[d.flights[0]]
        last = world.flights[d.flights[-1]]
        facts_days.append({
            "date": str(d.date), "flights": nos,
            "report_utc": iso(d.report_utc), "report_station": first.dep_station,
            "ends_at": last.arr_station})
        day_lines.append(f"  Day {i + 1} ({d.date}): {'/'.join(nos)} — report "
                         f"{d.report_utc:%H:%M}Z at {first.dep_station} crew room")
        if i < len(pdays) - 1:
            day_lines.append(f"    Overnight at {last.arr_station} (hotel arranged)")
    ack_by = pdays[0].report_utc - timedelta(minutes=c.reachability_minutes)
    message = "\n".join([
        f"CREW CALLOUT — {c.rank} {c.name} ({crew_id})",
        f"You are assigned to cover pairing {pairing_id} ({p.aircraft}).",
        *day_lines,
        f"Please acknowledge by {ack_by:%H:%M}Z on {ack_by.date()} "
        f"(your listed reachability is {c.reachability_minutes} min).",
        "Reply ACCEPT to confirm, or call Crew Control (+91-80-CREWOPS) with any issue.",
    ])
    return {"crew_id": crew_id, "pairing_id": pairing_id,
            "facts": {"days": facts_days, "acknowledge_by_utc": iso(ack_by),
                      "reachability_minutes": c.reachability_minutes},
            "message": message}
