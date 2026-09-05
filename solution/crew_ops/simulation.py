"""Tier 2 — consequence & simulation.

Every simulation is an alternate timeline layered over the base snapshot:
nothing here mutates the World, so disruptions never leak between questions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional

from .world import World, hrs, iso
from . import rules as R


@dataclass
class Disruption:
    """Overlay describing one disruptive event (mirrors scenarios.json types)."""
    type: str                       # SICK_CREW | STATION_CLOSURE | DELAY | CERT_EXPIRY | MULTI_SICK
    crew_id: Optional[str] = None
    pairing_id: Optional[str] = None
    station: Optional[str] = None
    window_start: Optional[datetime] = None
    window_end: Optional[datetime] = None
    aircraft: Optional[str] = None
    on_date: Optional[date] = None
    delay_hours: float = 0.0
    reported_utc: Optional[datetime] = None
    events: list = field(default_factory=list)   # for MULTI_SICK: [Disruption]


def _pairing_for_crew(world: World, crew_id: str, pairing_id: Optional[str],
                      from_date: Optional[date]):
    if pairing_id:
        return world.pairings[pairing_id]
    cands = [p for p in world.pairings_list if crew_id in [m for m, _ in p.crew]
             and (from_date is None or any(d.date >= from_date for d in p.days))]
    if not cands:
        raise ValueError(f"{crew_id} has no rostered pairing"
                         + (f" on/after {from_date}" if from_date else ""))
    return cands[0]


def sick_crew_impact(world: World, crew_id: str, pairing_id: Optional[str] = None,
                     reported_utc: Optional[datetime] = None) -> dict:
    """Which flights lose crew when `crew_id` drops out, including later days of
    a multi-day pairing (the pairing overnights away from base, so every
    remaining day is at risk, not just the first)."""
    from_date = reported_utc.date() if reported_utc else None
    p = _pairing_for_crew(world, crew_id, pairing_id, from_date)
    role = next(r for m, r in p.crew if m == crew_id)
    days = [d for d in p.days if from_date is None or d.date >= from_date]
    per_day = [{"date": str(d.date), "flights": list(d.flights),
                "passengers": sum(world.flights[f].seats for f in d.flights)}
               for d in days]
    uncovered = [f for d in days for f in d.flights]
    trace = [
        f"{crew_id} is rostered as {role} on pairing {p.pairing_id} ({p.aircraft})",
        f"pairing days affected from {from_date or 'start'}: "
        + ", ".join(x["date"] for x in per_day),
        "all remaining legs of the pairing lose their " + role,
    ]
    if len(days) > 1:
        last = world.flights[days[0].flights[-1]]
        trace.append(f"multi-day pairing: day 1 ends at {last.arr_station}, so the cover "
                     f"must take the FULL remaining pairing, not just day 1")
    return {
        "pairing_broken": p.pairing_id,
        "role": role,
        "uncovered_flights": uncovered,
        "per_day": per_day,
        "passengers_affected": sum(x["passengers"] for x in per_day),
        "trace": trace,
    }


def station_closure_impact(world: World, station: str,
                           window_start: datetime, window_end: datetime) -> dict:
    """Flights touching the closed station in the window, plus a per-flight
    assessment: minimum delay to reopen(+30min turnaround) and whether the
    rostered crew's FDP survives the extension (RULE-FDP-01)."""
    affected, per_flight, trace = [], [], []
    on = window_start.date()
    for f in world.flights_list:
        if f.date != on:
            continue
        hit = ((f.dep_station == station and window_start <= f.dep_utc < window_end) or
               (f.arr_station == station and window_start <= f.arr_utc < window_end))
        if not hit:
            continue
        affected.append(f.flight_id)
        p, day = world.pairing_day_of_flight(f.flight_id)
        anchor = (f.dep_utc if f.dep_station == station and
                  window_start <= f.dep_utc < window_end else f.arr_utc)
        shift = hrs((window_end + timedelta(minutes=30)) - anchor)
        new_rel = day.release_utc + timedelta(hours=shift)
        new_fdp = hrs(new_rel - day.report_utc)
        lim = world.fdp_limit(day.sectors)
        feasible = new_fdp <= lim
        per_flight.append({
            "flight_id": f.flight_id, "pairing_id": p.pairing_id,
            "min_delay_hours": round(shift, 2),
            "crew_fdp_after_delay": round(new_fdp, 2), "fdp_limit": lim,
            "action": "delay (crew legal)" if feasible
            else "delay exceeds crew FDP — re-crew tail legs from reserves or cancel"})
        trace.append(f"{f.flight_id}: {'departure' if anchor == f.dep_utc else 'arrival'} "
                     f"{anchor:%H:%M}Z inside closure; min delay to reopen+30min = "
                     f"{round(shift, 2)}h; crew FDP {round(new_fdp, 2)}h vs {lim}h limit "
                     f"-> {'legal' if feasible else 'FDP breach'}")
    return {"station": station,
            "window_utc": {"start": iso(window_start), "end": iso(window_end)},
            "affected_flights": affected, "per_flight_assessment": per_flight,
            "trace": trace}


def delay_impact(world: World, aircraft: str, on: date, delay_hours: float) -> dict:
    """A pre-duty tech delay shifts every leg. Does the rostered crew's FDP
    still hold, and if not, how many legs CAN they legally fly?"""
    p = world.pairing_for(aircraft, on)
    if p is None:
        raise ValueError(f"no pairing for {aircraft} on {on}")
    day = next(d for d in p.days if d.date == on)
    dl = day.duty_hours
    new_fdp = round(dl + delay_hours, 2)
    lim = world.fdp_limit(day.sectors)
    breach = new_fdp > lim
    # longest prefix of legs the original crew can legally fly under the delay
    legal_prefix, prefix_fdp, prefix_limit = day.sectors, new_fdp, lim
    if breach:
        rep = day.report_utc + timedelta(hours=delay_hours)
        for k in range(day.sectors - 1, 0, -1):
            arr_k = world.flights[day.flights[k - 1]].arr_utc + timedelta(hours=delay_hours)
            fdp_k = hrs((arr_k + timedelta(minutes=30)) - rep)
            if fdp_k <= world.fdp_limit(k):
                legal_prefix, prefix_fdp, prefix_limit = k, round(fdp_k, 2), world.fdp_limit(k)
                break
        else:
            legal_prefix, prefix_fdp, prefix_limit = 0, 0.0, world.fdp_limit(1)
    uncoverable = [world.flights[f].flight_no for f in day.flights[legal_prefix:]]
    detail = (f"RULE-FDP-01: delayed duty runs {new_fdp}h vs {lim}h limit "
              f"({day.sectors} sectors) — the rostered crew cannot legally complete "
              f"{', '.join(uncoverable)}." if breach else
              f"RULE-FDP-01: delayed duty runs {new_fdp}h vs {lim}h limit "
              f"({day.sectors} sectors) — legal.")
    return {
        "pairing_id": p.pairing_id, "aircraft": aircraft, "date": str(on),
        "delay_hours": delay_hours,
        "fdp_after_delay": new_fdp, "fdp_limit": lim, "breach": breach,
        "breach_detail": detail,
        "legal_prefix_sectors": legal_prefix,
        "prefix_fdp": prefix_fdp, "prefix_fdp_limit": prefix_limit,
        "uncoverable_flight_nos": uncoverable,
        "trace": [
            f"duty {day.report_utc:%H:%M}Z->{day.release_utc:%H:%M}Z = {dl}h; "
            f"+{delay_hours}h delay = {new_fdp}h",
            f"limit for {day.sectors} sectors = {lim}h -> "
            f"{'BREACH' if breach else 'legal'}",
        ] + ([f"longest legal prefix: {legal_prefix} legs "
              f"(FDP {prefix_fdp}h vs {prefix_limit}h limit); "
              f"remaining legs {', '.join(uncoverable)} need re-crew or cancellation"]
             if breach else []),
    }


def cert_expiry_impact(world: World, crew_id: str, on: date) -> dict:
    """Is this crew member legal to operate their rostered duty on `on`?"""
    ok, expired = world.certs_ok(crew_id, on)
    duties = [wd for wd in world.week_duties.get(crew_id, []) if wd.date == on]
    return {
        "crew_id": crew_id, "date": str(on),
        "legal": ok,
        "rule": None if ok else "RULE-CERT-06",
        "expired": [{"cert_type": t, "valid_to": str(vt)} for t, vt in expired],
        "rostered": [{"pairing_id": wd.pairing_id} for wd in duties],
        "detail": ("all certifications valid" if ok else
                   "; ".join(f"{t} expired {vt}" for t, vt in expired)),
        "trace": [f"certifications for {crew_id} on {on}: " +
                  ("all valid" if ok else
                   ", ".join(f"{t} expired {vt}" for t, vt in expired))],
    }


def check_assignment(world: World, crew_id: str, pairing_id: str,
                     exclude_pairing: Optional[str] = "COVERED",
                     delay_hours: float = 0.0,
                     days_from: Optional[date] = None) -> dict:
    """Full 7-rule legality of `crew_id` covering `pairing_id` (or its remaining
    days from `days_from`). By default the covered pairing itself is excluded
    from the candidate's own roster (they are replacing whoever was on it)."""
    p = world.pairings[pairing_id]
    pdays = [d for d in p.days if days_from is None or d.date >= days_from]
    if exclude_pairing == "COVERED":
        exclude_pairing = pairing_id
    check = R.evaluate_cover(world, crew_id, pdays,
                             exclude_pairing=exclude_pairing, delay_h=delay_hours)
    return check.to_dict()


def rest_requirement(world: World, release_utc: datetime) -> dict:
    earliest = R.rest_requirement(world, release_utc)
    return {"release_utc": iso(release_utc), "min_rest_hours": 12,
            "earliest_next_report_utc": iso(earliest),
            "trace": [f"RULE-REST-04: {iso(release_utc)} + 12h = {iso(earliest)}"]}


def cancellation_impact(world: World, flight_id: str) -> dict:
    f = world.flights[flight_id]
    cost = world.costs["cancellation_per_flight"]
    return {"flight_id": flight_id, "passengers": f.seats, "cost_inr": cost,
            "trace": [f"{flight_id}: {f.seats} seats ({f.aircraft_type}); "
                      f"cancellation_per_flight = INR {cost}"]}
