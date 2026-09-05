"""The LLM <-> engine boundary: typed tools, JSON in / JSON out.

An LLM adapter (any provider) exposes `tool_schemas()` as its tool definitions
and routes every tool call through `dispatch(name, args)`. Everything below
this file is deterministic; nothing above it computes.

Every response: {"ok": bool, "result": ..., "sources": [...], "trace": [...]}
or {"ok": false, "error": "..."} — errors are answers too (the honest-refusal
path), never exceptions leaking to the model.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Callable, Optional

from .world import World, parse_utc
from . import query as Q
from . import simulation as S
from . import recommender as REC

_REGISTRY: dict = {}


def _tool(name: str, description: str, params: dict, sources: list):
    def wrap(fn: Callable):
        _REGISTRY[name] = {"fn": fn, "description": description,
                           "params": params, "sources": sources}
        return fn
    return wrap


def _date(v: Optional[str]) -> Optional[date]:
    return date.fromisoformat(v) if v else None


def _dt(v: Optional[str]) -> Optional[datetime]:
    return parse_utc(v) if v else None


# The model writes what the controller typed ("captain", "blr", "c-1042");
# the engine stores canonical forms. Normalize here, at the boundary, so a
# casing mismatch can never silently return an empty (and wrong) result.

_RANKS = {"captain": "Captain", "capt": "Captain", "cpt": "Captain",
          "first officer": "First Officer", "fo": "First Officer",
          "f/o": "First Officer", "first-officer": "First Officer",
          "senior cabin crew": "Senior Cabin Crew", "scc": "Senior Cabin Crew",
          "senior cc": "Senior Cabin Crew",
          "cabin crew": "Cabin Crew", "cc": "Cabin Crew", "cabin": "Cabin Crew"}


def _rank(v: Optional[str]) -> Optional[str]:
    if not v:
        return v
    key = " ".join(v.strip().lower().replace("_", " ").split())
    if key not in _RANKS:
        raise ValueError(f"unknown rank/role '{v}'; expected one of: Captain, "
                         "First Officer, Senior Cabin Crew, Cabin Crew")
    return _RANKS[key]


def _up(v: Optional[str]) -> Optional[str]:
    """Stations, aircraft, ratings and dataset ids are upper-case."""
    return v.upper() if isinstance(v, str) else v


def tool_schemas() -> list:
    """JSON-schema-style tool definitions for any LLM adapter."""
    return [{
        "name": name,
        "description": t["description"],
        "input_schema": {"type": "object", "properties": t["params"],
                         "required": [k for k, v in t["params"].items()
                                      if v.get("required")]},
    } for name, t in _REGISTRY.items()]


def dispatch(world: World, name: str, args: Optional[dict] = None) -> dict:
    args = args or {}
    if name not in _REGISTRY:
        return {"ok": False,
                "error": f"unknown tool '{name}'; available: {sorted(_REGISTRY)}"}
    t = _REGISTRY[name]
    try:
        result = t["fn"](world, **args)
    except Exception as e:  # errors are answers too — never leak an exception
        return {"ok": False, "error": f"{type(e).__name__}: {e}",
                "hint": "check ids/dates against the dataset; this tool cannot "
                        "answer reliably with these arguments"}
    trace = []
    if isinstance(result, dict) and "trace" in result:
        trace = result["trace"]
    return {"ok": True, "result": result, "sources": t["sources"], "trace": trace}


# --------------------------- Tier 1: lookup ---------------------------

@_tool("lookup_crew", "Find crew by id/name/rank/base/status/rating.",
       {"crew_id": {"type": "string"}, "name": {"type": "string"},
        "rank": {"type": "string"}, "base": {"type": "string"},
        "status": {"type": "string"}, "rating": {"type": "string"}},
       ["crew.json"])
def _lookup_crew(world, crew_id=None, name=None, rank=None, base=None,
                 status=None, rating=None):
    return Q.lookup_crew(world, crew_id=_up(crew_id), name=name,
                         rank=_rank(rank), base=_up(base),
                         status=status.lower() if status else None,
                         rating=_up(rating))


@_tool("lookup_flights", "Filter the flight schedule.",
       {"date": {"type": "string"}, "dep_station": {"type": "string"},
        "arr_station": {"type": "string"}, "flight_no": {"type": "string"},
        "aircraft": {"type": "string"}},
       ["flights.json"])
def _lookup_flights(world, date=None, **kw):
    return Q.lookup_flights(world, on=_date(date),
                            **{k: _up(v) for k, v in kw.items()})


@_tool("get_duty_clock",
       "Rolling 7d duty / 28d flight-hour windows for a crew member ending a "
       "given date (daily history + rostered duties), with headroom.",
       {"crew_id": {"type": "string", "required": True},
        "end_date": {"type": "string"}},
       ["duty_clocks.json", "rosters.json", "rules.json"])
def _duty_clock(world, crew_id, end_date=None):
    return Q.duty_clock(world, _up(crew_id), _date(end_date))


@_tool("get_reserves", "Reserve pool with on-call windows, filtered by base/date.",
       {"base": {"type": "string"}, "date": {"type": "string"}},
       ["reserve_pool.json", "crew.json"])
def _reserves(world, base=None, date=None):
    return Q.reserves(world, base=_up(base), on=_date(date))


@_tool("get_certifications",
       "Certifications, optionally for one crew member or expiring in a window.",
       {"crew_id": {"type": "string"}, "expiring_from": {"type": "string"},
        "expiring_to": {"type": "string"}},
       ["certifications.json"])
def _certs(world, crew_id=None, expiring_from=None, expiring_to=None):
    return Q.certifications(world, _up(crew_id), _date(expiring_from),
                            _date(expiring_to))


@_tool("get_risk_signals", "Pre-computed disruption-risk scores (provided input).",
       {"crew_id": {"type": "string"}, "min_score": {"type": "number"}},
       ["risk_signals.json"])
def _risks(world, crew_id=None, min_score=0.0):
    return Q.risk_signals(world, _up(crew_id), min_score)


@_tool("get_pairing", "Pairings with days, flights, report/release and crew.",
       {"pairing_id": {"type": "string"}, "crew_id": {"type": "string"},
        "aircraft": {"type": "string"}, "date": {"type": "string"}},
       ["rosters.json"])
def _pairing(world, pairing_id=None, crew_id=None, aircraft=None, date=None):
    return Q.pairing_info(world, _up(pairing_id), _up(crew_id), _up(aircraft),
                          _date(date))


@_tool("get_duty_watchlist",
       "Crew at/above a 7-day duty-hour threshold (early-warning list).",
       {"end_date": {"type": "string", "required": True},
        "threshold": {"type": "number"}},
       ["duty_clocks.json", "rosters.json"])
def _watchlist(world, end_date, threshold=45.0):
    return Q.crew_over_duty_threshold(world, _date(end_date), threshold)


# ----------------------- Tier 2: simulation -----------------------

@_tool("simulate_sick_crew",
       "Impact of a crew member dropping out: uncovered flights (all remaining "
       "days of the pairing), passengers, broken pairing.",
       {"crew_id": {"type": "string", "required": True},
        "pairing_id": {"type": "string"}, "reported_utc": {"type": "string"}},
       ["rosters.json", "flights.json"])
def _sick(world, crew_id, pairing_id=None, reported_utc=None):
    return S.sick_crew_impact(world, _up(crew_id), _up(pairing_id),
                              _dt(reported_utc))


@_tool("simulate_station_closure",
       "Flights hit by a station closure window plus per-flight delay/FDP assessment.",
       {"station": {"type": "string", "required": True},
        "window_start_utc": {"type": "string", "required": True},
        "window_end_utc": {"type": "string", "required": True}},
       ["flights.json", "rosters.json", "rules.json"])
def _closure(world, station, window_start_utc, window_end_utc):
    return S.station_closure_impact(world, _up(station), _dt(window_start_utc),
                                    _dt(window_end_utc))


@_tool("simulate_delay",
       "A pre-duty delay shifts all legs: does the rostered crew's FDP hold, "
       "and how many legs can they legally fly?",
       {"aircraft": {"type": "string", "required": True},
        "date": {"type": "string", "required": True},
        "delay_hours": {"type": "number", "required": True}},
       ["flights.json", "rosters.json", "rules.json"])
def _delay(world, aircraft, date, delay_hours):
    return S.delay_impact(world, _up(aircraft), _date(date), delay_hours)


@_tool("check_certification_validity",
       "Is a crew member legal to operate on a date (RULE-CERT-06)?",
       {"crew_id": {"type": "string", "required": True},
        "date": {"type": "string", "required": True}},
       ["certifications.json", "rosters.json"])
def _cert_check(world, crew_id, date):
    return S.cert_expiry_impact(world, _up(crew_id), _date(date))


@_tool("check_assignment_legality",
       "Full 7-rule check: can this crew member cover this pairing (optionally "
       "from a date, with a delay)? Returns verdicts, issues and arithmetic trace.",
       {"crew_id": {"type": "string", "required": True},
        "pairing_id": {"type": "string", "required": True},
        "exclude_pairing": {"type": "string"},
        "delay_hours": {"type": "number"}, "days_from": {"type": "string"}},
       ["rosters.json", "duty_clocks.json", "certifications.json", "rules.json"])
def _legality(world, crew_id, pairing_id, exclude_pairing="COVERED",
              delay_hours=0.0, days_from=None):
    if exclude_pairing != "COVERED":
        exclude_pairing = _up(exclude_pairing)
    return S.check_assignment(world, _up(crew_id), _up(pairing_id),
                              exclude_pairing, delay_hours, _date(days_from))


@_tool("compute_rest_requirement",
       "Earliest legal next report after a release (RULE-REST-04).",
       {"release_utc": {"type": "string", "required": True}},
       ["rules.json"])
def _rest(world, release_utc):
    return S.rest_requirement(world, _dt(release_utc))


@_tool("cancellation_impact", "Passengers affected and direct cost of cancelling a leg.",
       {"flight_id": {"type": "string", "required": True}},
       ["flights.json", "costs.json"])
def _cancel(world, flight_id):
    return S.cancellation_impact(world, _up(flight_id))


# --------------------- Tier 3: recommendation ---------------------

@_tool("recommend_cover",
       "Ranked, rule-checked, costed options to cover a role on a pairing, "
       "with every rejected candidate and the rule that killed them.",
       {"pairing_id": {"type": "string", "required": True},
        "role": {"type": "string", "required": True},
        "sick_crew_id": {"type": "string"}, "days_from": {"type": "string"},
        "reported_utc": {"type": "string"}},
       ["crew.json", "rosters.json", "reserve_pool.json", "duty_clocks.json",
        "certifications.json", "rules.json", "costs.json"])
def _recommend(world, pairing_id, role, sick_crew_id=None, days_from=None,
               reported_utc=None):
    return REC.cover_options(world, _up(pairing_id), _rank(role),
                             _up(sick_crew_id), _date(days_from),
                             _dt(reported_utc))


@_tool("recommend_joint",
       "Optimal joint plan for simultaneous disruptions (no crew member used "
       "twice; total cost minimised).",
       {"events": {"type": "array", "required": True,
                   "items": {"type": "object",
                             "properties": {"pairing_id": {"type": "string"},
                                            "role": {"type": "string"},
                                            "sick_crew_id": {"type": "string"},
                                            "days_from": {"type": "string"}}}}},
       ["crew.json", "rosters.json", "reserve_pool.json", "costs.json", "rules.json"])
def _joint(world, events):
    if not events or not all(e.get("pairing_id") and e.get("role")
                             for e in events):
        raise ValueError("each event needs at least pairing_id and role")
    events = [{**e, "pairing_id": _up(e.get("pairing_id")),
               "role": _rank(e.get("role")),
               "sick_crew_id": _up(e.get("sick_crew_id")),
               "days_from": _date(e.get("days_from"))} for e in events]
    return REC.joint_plan(world, events)


@_tool("recommend_delay_recovery",
       "Recovery for a delay that breaches FDP: split the duty at the longest "
       "legal prefix, re-crew or cancel the tail, ranked by cost.",
       {"aircraft": {"type": "string", "required": True},
        "date": {"type": "string", "required": True},
        "delay_hours": {"type": "number", "required": True}},
       ["rosters.json", "rules.json", "costs.json"])
def _delay_recovery(world, aircraft, date, delay_hours):
    return REC.delay_recovery(world, _up(aircraft), _date(date), delay_hours)


@_tool("draft_notification",
       "Structured callout facts + plain-text message for a chosen cover.",
       {"crew_id": {"type": "string", "required": True},
        "pairing_id": {"type": "string", "required": True},
        "days_from": {"type": "string"}},
       ["rosters.json", "crew.json", "flights.json"])
def _notify(world, crew_id, pairing_id, days_from=None):
    return REC.draft_notification(world, _up(crew_id), _up(pairing_id),
                                  _date(days_from))
