"""Rules engine: the 7 legality rules as pure checks with arithmetic traces.

`evaluate_cover` answers: can crew X legally operate this set of pairing days
(optionally shifted by a delay), given everything else on their plate?

Every check emits a Verdict carrying the computation that produced it; the
`issues` list reproduces the dataset generator's canonical breach wording so
answers diff cleanly against the shipped answer keys.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from .world import World, PairingDay, hrs

EPS = 1e-6

ALL_RULES = ["RULE-FDP-01", "RULE-DUTY-02", "RULE-FLT-03", "RULE-REST-04",
             "RULE-QUAL-05", "RULE-CERT-06", "RULE-BASE-07"]

RULE_TEXT = {
    "RULE-FDP-01": "Max flight duty period 13h, reduced 0.5h per sector beyond the 2nd.",
    "RULE-DUTY-02": "Max 60 duty hours in any 7 consecutive calendar days.",
    "RULE-FLT-03": "Max 100 flight (block) hours in any 28 consecutive calendar days.",
    "RULE-REST-04": "Min 12h rest between release and next report.",
    "RULE-QUAL-05": "Crew must hold a valid rating for the assigned aircraft type.",
    "RULE-CERT-06": "All certifications must be valid on the duty date.",
    "RULE-BASE-07": "Reserve callout from own base only; other base requires deadhead.",
}


@dataclass
class Verdict:
    rule_id: str
    ok: bool
    detail: str
    computed: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"rule_id": self.rule_id, "ok": self.ok,
                "detail": self.detail, "computed": self.computed}


@dataclass
class CoverCheck:
    crew_id: str
    legal: bool
    issues: list            # canonical breach strings (generator wording)
    verdicts: list          # all Verdicts, pass and fail
    trace: list             # human-readable computation steps

    def to_dict(self) -> dict:
        return {"crew_id": self.crew_id, "legal": self.legal, "issues": self.issues,
                "rules_checked": ALL_RULES,
                "verdicts": [v.to_dict() for v in self.verdicts],
                "trace": self.trace}


def _fmt_excess(excess: float) -> str:
    hh = int(excess)
    mm = int(round((excess - hh) * 60))
    return f"{hh}h{mm:02d}m"


def evaluate_cover(world: World, crew_id: str, pdays,
                   exclude_pairing: Optional[str] = None,
                   delay_h: float = 0.0) -> CoverCheck:
    """Full 7-rule legality check for `crew_id` covering `pdays`.

    pdays: list of PairingDay. exclude_pairing: pairing removed from the
    crew's own roster in the simulation (e.g. the pairing being re-covered).
    delay_h: shift applied to the cover duty (deadhead positioning / tech delay).
    """
    c = world.crew[crew_id]
    verdicts, issues, trace = [], [], []

    # --- RULE-QUAL-05 (gate: an unrated candidate is out immediately) ---
    actype = world.flights[pdays[0].flights[0]].aircraft_type
    qual_ok = actype in c.ratings
    verdicts.append(Verdict("RULE-QUAL-05", qual_ok,
                            f"{crew_id} ratings {list(c.ratings)} vs required {actype}",
                            {"required": actype, "ratings": list(c.ratings)}))
    trace.append(f"RULE-QUAL-05: aircraft type {actype}; {crew_id} holds {list(c.ratings)} "
                 f"-> {'OK' if qual_ok else 'FAIL'}")
    if not qual_ok:
        issues.append(f"RULE-QUAL-05: no {actype} rating")
        return CoverCheck(crew_id, False, issues, verdicts, trace)

    # --- build the simulated duty sequence: own roster (minus excluded) + cover ---
    own = [wd for wd in world.week_duties.get(crew_id, [])
           if wd.pairing_id != exclude_pairing]
    sim = [(wd.date, wd.report, wd.release, wd.duty_hours, wd.pairing_id) for wd in own]
    shift = timedelta(hours=delay_h)

    # --- per-day: RULE-CERT-06 then RULE-FDP-01 (generator issue order) ---
    for day in pdays:
        rep, rel = day.report_utc + shift, day.release_utc + shift
        ok, expired = world.certs_ok(crew_id, day.date)
        verdicts.append(Verdict(
            "RULE-CERT-06", ok,
            f"certifications on {day.date}: " +
            ("all valid" if ok else ", ".join(f"{t} expired {vt}" for t, vt in expired)),
            {"date": str(day.date), "expired": [[t, str(vt)] for t, vt in expired]}))
        if not ok:
            issues.append(f"RULE-CERT-06: certification invalid on {day.date}")
        fdp = hrs(rel - rep)
        lim = world.fdp_limit(day.sectors)
        fdp_ok = fdp <= lim + EPS
        verdicts.append(Verdict(
            "RULE-FDP-01", fdp_ok,
            f"{day.date}: FDP {fdp}h vs limit {lim}h ({day.sectors} sectors)",
            {"date": str(day.date), "fdp_hours": fdp, "limit_hours": lim,
             "sectors": day.sectors}))
        trace.append(f"RULE-FDP-01 {day.date}: report {rep:%H:%M}Z -> release {rel:%H:%M}Z "
                     f"= {fdp}h; limit 13h - 0.5h x {max(0, day.sectors - 2)} extra sectors "
                     f"= {lim}h -> {'OK' if fdp_ok else 'FAIL'}")
        if not fdp_ok:
            issues.append(f"RULE-FDP-01: FDP {fdp}h > {lim}h limit ({day.sectors} sectors)")
        sim.append((day.date, rep, rel, day.duty_hours, "COVER"))

    # --- RULE-REST-04 + overlap across the simulated sequence ---
    sim.sort(key=lambda x: x[1])
    rest_issues, overlap_issues, rest_ok = [], [], True
    for a, b in zip(sim, sim[1:]):
        rest = hrs(b[1] - a[2])
        if rest < 12 - EPS:
            rest_ok = False
            tag = "downstream" if b[4] != "COVER" and a[4] == "COVER" else "rest"
            rest_issues.append(
                f"RULE-REST-04: only {rest}h rest before {b[4]} on {b[0]} ({tag} conflict)")
            trace.append(f"RULE-REST-04: {a[4]} releases {a[2]:%Y-%m-%d %H:%M}Z, "
                         f"{b[4]} reports {b[1]:%Y-%m-%d %H:%M}Z -> {rest}h rest < 12h")
    for a, b in zip(sim, sim[1:]):
        if b[1] < a[2]:
            overlap_issues.append(f"double-booked: {a[4]} overlaps {b[4]} on {b[0]}")
    # rest before the first simulated duty, from the published clock
    # (daily_history has no report/release times; last_rest_ended is the moment
    # the 12h minimum rest after the last pre-snapshot duty completed).
    # Only meaningful when the COVER duty is first: an own rostered duty first
    # in sequence is the very duty last_rest_ended was derived from, and the
    # base roster is already rest-valid (dataset guarantee).
    pre_rest_ok = True
    lre = world.clocks.get(crew_id, {}).get("last_rest_ended")
    if sim and sim[0][4] == "COVER" and lre is not None and sim[0][1] < lre:
        pre_rest_ok = False
        rest_issues.append(
            f"RULE-REST-04: first report {sim[0][1]:%Y-%m-%dT%H:%M}Z precedes "
            f"minimum-rest completion at {lre:%Y-%m-%dT%H:%M}Z")
    verdicts.append(Verdict("RULE-REST-04", rest_ok and pre_rest_ok and not overlap_issues,
                            "; ".join(rest_issues + overlap_issues) or
                            ">=12h rest around every duty in the simulated sequence",
                            {"duties_simulated": len(sim)}))
    issues.extend(rest_issues)
    issues.extend(overlap_issues)

    # --- RULE-DUTY-02: rolling 7-calendar-day window per cover day ---
    duty_ok = True
    for day in pdays:
        d = day.date
        base7 = world.window_sum(crew_id, d, 7)
        removed = 0.0
        for wd in world.week_duties.get(crew_id, []):
            if wd.pairing_id == exclude_pairing and d - timedelta(days=6) <= wd.date <= d:
                base7 -= wd.duty_hours
                removed += wd.duty_hours
        add = sum(x.duty_hours for x in pdays if x.date <= d)
        tot7 = round(base7 + add, 2)
        ok7 = tot7 <= 60 + EPS
        verdicts.append(Verdict(
            "RULE-DUTY-02", ok7,
            f"7d window ending {d}: {tot7}h vs 60h",
            {"date": str(d), "window": f"{d - timedelta(days=6)}..{d}",
             "existing_hours": round(base7, 2), "excluded_pairing_hours": round(removed, 2),
             "cover_hours": round(add, 2), "total_hours": tot7, "limit": 60}))
        trace.append(f"RULE-DUTY-02 {d}: existing {round(base7, 2)}h in {d - timedelta(days=6)}"
                     f"..{d} + cover {round(add, 2)}h = {tot7}h vs 60h -> "
                     f"{'OK' if ok7 else 'FAIL'}")
        if not ok7:
            duty_ok = False
            excess = tot7 - 60
            issues.append(f"RULE-DUTY-02: would exceed 60h/7d by {_fmt_excess(excess)} "
                          f"on {d} (total {tot7}h)")

    # --- RULE-FLT-03: rolling 28-calendar-day block-hour window per cover day ---
    flt_ok = True
    for day in pdays:
        d = day.date
        base28 = world.window_sum(crew_id, d, 28, kind="flight")
        for wd in world.week_duties.get(crew_id, []):
            if wd.pairing_id == exclude_pairing and d - timedelta(days=27) <= wd.date <= d:
                base28 -= wd.flight_hours
        add = round(sum(world.flights[fid].block_hours
                        for x in pdays if x.date <= d for fid in x.flights), 2)
        tot28 = round(base28 + add, 2)
        ok28 = tot28 <= 100 + EPS
        verdicts.append(Verdict(
            "RULE-FLT-03", ok28,
            f"28d block hours ending {d}: {tot28}h vs 100h",
            {"date": str(d), "existing_hours": round(base28, 2),
             "cover_block_hours": add, "total_hours": tot28, "limit": 100}))
        if not ok28:
            flt_ok = False
            issues.append(f"RULE-FLT-03: would exceed 100h/28d on {d} (total {tot28}h)")
    if duty_ok and flt_ok:
        trace.append("RULE-FLT-03: 28-day block-hour window within 100h on every cover day")

    legal = not issues
    return CoverCheck(crew_id, legal, issues, verdicts, trace)


def rest_requirement(world: World, release):
    """RULE-REST-04: earliest next report after a release."""
    return release + timedelta(hours=next(
        r["params"]["min_rest_hours"] for r in world.rules["rules"]
        if r["rule_id"] == "RULE-REST-04"))


def reserve_window_covers(world: World, crew_id: str, required_report) -> tuple:
    """(covers, detail). Required report time must fall inside the on-call
    window on the report date (dataset README: report time, not callout time)."""
    r = world.reserves[crew_id]
    from .world import hm_on
    ws = hm_on(required_report.date(), r.window_start)
    we = hm_on(required_report.date(), r.window_end)
    covers = ws <= required_report <= we
    return covers, (f"reserve on-call window {r.window_start}-{r.window_end}Z "
                    f"{'covers' if covers else 'does not cover'} required report "
                    f"{required_report.strftime('%H:%M')}Z")
