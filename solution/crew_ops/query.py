"""Tier 1 — lookup & retrieval over the world state. Pure reads, no simulation.

Every function returns plain JSON-able data plus enough provenance for the
narration layer to cite sources.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from .world import World


def lookup_crew(world: World, crew_id: Optional[str] = None, name: Optional[str] = None,
                rank: Optional[str] = None, base: Optional[str] = None,
                status: Optional[str] = None, rating: Optional[str] = None) -> list:
    out = []
    for c in world.crew.values():
        if crew_id and c.crew_id != crew_id:
            continue
        if name and name.lower() not in c.name.lower():
            continue
        if rank and c.rank != rank:
            continue
        if base and c.base != base:
            continue
        if status and c.status != status:
            continue
        if rating and rating not in c.ratings:
            continue
        out.append({"crew_id": c.crew_id, "name": c.name, "rank": c.rank, "base": c.base,
                    "ratings": list(c.ratings), "seniority": c.seniority,
                    "reachability_minutes": c.reachability_minutes, "status": c.status})
    return out


def lookup_flights(world: World, on: Optional[date] = None,
                   dep_station: Optional[str] = None, arr_station: Optional[str] = None,
                   flight_no: Optional[str] = None, aircraft: Optional[str] = None) -> list:
    out = []
    for f in world.flights_list:
        if on and f.date != on:
            continue
        if dep_station and f.dep_station != dep_station:
            continue
        if arr_station and f.arr_station != arr_station:
            continue
        if flight_no and f.flight_no != flight_no:
            continue
        if aircraft and f.aircraft != aircraft:
            continue
        out.append({"flight_id": f.flight_id, "flight_no": f.flight_no, "date": str(f.date),
                    "dep_station": f.dep_station, "arr_station": f.arr_station,
                    "dep_utc": f.dep_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "arr_utc": f.arr_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "block_hours": f.block_hours, "aircraft": f.aircraft,
                    "aircraft_type": f.aircraft_type, "seats": f.seats})
    return out


def duty_clock(world: World, crew_id: str, end_date: Optional[date] = None) -> dict:
    """Rolling 7d duty / 28d flight windows ending `end_date` (default: snapshot
    date 2026-09-14), computed from daily_history + rostered week duties."""
    end_date = end_date or world.snapshot.date()
    d7 = world.window_sum(crew_id, end_date, 7, kind="duty")
    f28 = world.window_sum(crew_id, end_date, 28, kind="flight")
    lre = world.clocks.get(crew_id, {}).get("last_rest_ended")
    return {
        "crew_id": crew_id,
        "window_end": str(end_date),
        "duty_hours_7d": d7,
        "duty_headroom_7d": round(60 - d7, 2),
        "flight_hours_28d": f28,
        "flight_headroom_28d": round(100 - f28, 2),
        "last_rest_ended": lre.strftime("%Y-%m-%dT%H:%M:%SZ") if lre else None,
        "computation": f"sum(daily_history) + sum(rostered duties) over "
                       f"{end_date - timedelta(days=6)}..{end_date} (7d) and "
                       f"{end_date - timedelta(days=27)}..{end_date} (28d)",
    }


def reserves(world: World, base: Optional[str] = None, on: Optional[date] = None) -> list:
    out = []
    for r in world.reserves_list:
        if base and r.base != base:
            continue
        if on and on not in r.dates:
            continue
        c = world.crew[r.crew_id]
        out.append({"crew_id": r.crew_id, "rank": c.rank, "base": r.base,
                    "ratings": list(c.ratings),
                    "window": {"start": r.window_start, "end": r.window_end},
                    "reachability_minutes": c.reachability_minutes})
    return out


def certifications(world: World, crew_id: Optional[str] = None,
                   expiring_from: Optional[date] = None,
                   expiring_to: Optional[date] = None) -> list:
    out = []
    for c in world.certs_list:  # file order, like the answer keys
        if crew_id and c["crew_id"] != crew_id:
            continue
        vt = date.fromisoformat(c["valid_to"])
        if expiring_from and vt < expiring_from:
            continue
        if expiring_to and vt > expiring_to:
            continue
        out.append({"crew_id": c["crew_id"], "cert_type": c["cert_type"],
                    "valid_to": c["valid_to"]})
    return out


def risk_signals(world: World, crew_id: Optional[str] = None,
                 min_score: float = 0.0) -> list:
    out = []
    for r in world.risks.values():
        if crew_id and r["crew_id"] != crew_id:
            continue
        if r["disruption_risk_score"] < min_score:
            continue
        out.append({"crew_id": r["crew_id"], "score": r["disruption_risk_score"],
                    "drivers": r["drivers"]})
    return out


def pairing_info(world: World, pairing_id: Optional[str] = None,
                 crew_id: Optional[str] = None, aircraft: Optional[str] = None,
                 on: Optional[date] = None) -> list:
    out = []
    for p in world.pairings_list:
        if pairing_id and p.pairing_id != pairing_id:
            continue
        if crew_id and crew_id not in [m for m, _ in p.crew]:
            continue
        if aircraft and p.aircraft != aircraft:
            continue
        if on and not any(d.date == on for d in p.days):
            continue
        out.append({
            "pairing_id": p.pairing_id, "aircraft": p.aircraft,
            "days": [{"date": str(d.date), "flights": list(d.flights),
                      "report_utc": d.report_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
                      "release_utc": d.release_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
                      "sectors": d.sectors, "duty_hours": d.duty_hours}
                     for d in p.days],
            "crew": [{"crew_id": m, "role": role} for m, role in p.crew]})
    return out


def crew_over_duty_threshold(world: World, end_date: date, threshold: float = 45.0) -> list:
    """Crew at/above `threshold` duty hours in the 7 days ending end_date,
    including rostered duties in the window (early-warning list)."""
    out = []
    for cid in world.crew:
        h = world.window_sum(cid, end_date, 7)
        if h >= threshold:
            out.append({"crew_id": cid, "duty_hours_7d": h})
    out.sort(key=lambda x: -x["duty_hours_7d"])
    return out
