"""World state: loads the dataset once, builds indexes, answers time-window sums.

Conventions (from rules.json / dataset README):
- All times UTC. Duty period = report -> release.
  Report = first departure - 60 min; release = last arrival + 30 min.
- Rolling duty/flight windows are CALENDAR-DAY windows (UTC dates), inclusive
  of the duty date. They are computed as:
      sum(daily_history entries in window)  # actuals through 2026-09-14
    + sum(rostered week duties in window)   # plan for 2026-09-14 .. 09-20
  (validate.py, shipped with the dataset, uses exactly this convention.)
"""

from __future__ import annotations

import glob
import json
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional

UTC_FMT = "%Y-%m-%dT%H:%M:%SZ"


def parse_utc(s: str) -> datetime:
    return datetime.strptime(s, UTC_FMT)


def iso(x: datetime) -> str:
    return x.strftime(UTC_FMT)


def hrs(td: timedelta) -> float:
    """Timedelta -> hours, rounded to 2 dp (the dataset's own rounding)."""
    return round(td.total_seconds() / 3600.0, 2)


def hm_on(d: date, hm: str) -> datetime:
    h, m = map(int, hm.split(":"))
    return datetime(d.year, d.month, d.day, h, m)


@dataclass(frozen=True)
class Flight:
    flight_id: str
    flight_no: str
    date: date
    dep_station: str
    arr_station: str
    dep_utc: datetime
    arr_utc: datetime
    block_hours: float
    aircraft: str
    aircraft_type: str
    seats: int


@dataclass(frozen=True)
class CrewMember:
    crew_id: str
    name: str
    rank: str
    base: str
    ratings: tuple
    seniority: int
    reachability_minutes: int
    status: str


@dataclass(frozen=True)
class PairingDay:
    date: date
    flights: tuple  # flight_ids in file order
    report_utc: datetime
    release_utc: datetime

    @property
    def sectors(self) -> int:
        return len(self.flights)

    @property
    def duty_hours(self) -> float:
        return hrs(self.release_utc - self.report_utc)


@dataclass(frozen=True)
class Pairing:
    pairing_id: str
    aircraft: str
    days: tuple  # of PairingDay
    crew: tuple  # of (crew_id, role)


@dataclass(frozen=True)
class Duty:
    """One rostered duty day for one crew member (derived from rosters)."""
    date: date
    report: datetime
    release: datetime
    duty_hours: float
    flight_hours: float
    pairing_id: str


@dataclass(frozen=True)
class ReserveEntry:
    crew_id: str
    base: str
    dates: frozenset  # of date
    window_start: str  # "HH:MM"
    window_end: str


@dataclass
class World:
    data_dir: str
    snapshot: datetime
    flights: dict = field(default_factory=dict)          # fid -> Flight
    flights_list: list = field(default_factory=list)     # file order
    crew: dict = field(default_factory=dict)             # cid -> CrewMember (file order = sorted by id)
    pairings: dict = field(default_factory=dict)         # pid -> Pairing
    pairings_list: list = field(default_factory=list)
    flagged_exceptions: list = field(default_factory=list)
    history: dict = field(default_factory=dict)          # cid -> {date: (duty_h, flight_h)}
    clocks: dict = field(default_factory=dict)           # cid -> summary dict (parsed)
    reserves: dict = field(default_factory=dict)         # cid -> ReserveEntry
    reserves_list: list = field(default_factory=list)    # file order
    certs: dict = field(default_factory=dict)            # cid -> {cert_type: (valid_from, valid_to)}
    certs_list: list = field(default_factory=list)       # file order (raw dicts)
    risks: dict = field(default_factory=dict)            # cid -> raw dict
    rules: dict = field(default_factory=dict)
    costs: dict = field(default_factory=dict)
    week_duties: dict = field(default_factory=dict)      # cid -> [Duty] sorted by date
    pairing_of_flight: dict = field(default_factory=dict)  # fid -> pairing_id

    # ---------- indexes / lookups ----------

    def flight(self, fid: str) -> Flight:
        return self.flights[fid]

    def pairing_day_of_flight(self, fid: str):
        p = self.pairings[self.pairing_of_flight[fid]]
        day = next(d for d in p.days if fid in d.flights)
        return p, day

    def pairing_for(self, aircraft: str, on: date) -> Optional[Pairing]:
        for p in self.pairings_list:
            if p.aircraft == aircraft and any(d.date == on for d in p.days):
                return p
        return None

    def fdp_limit(self, sectors: int) -> float:
        p = next(r["params"] for r in self.rules["rules"] if r["rule_id"] == "RULE-FDP-01")
        return p["base_fdp_hours"] - p["reduction_per_extra_sector_hours"] * max(
            0, sectors - p["free_sectors"])

    # ---------- rolling windows ----------

    def window_sum(self, crew_id: str, end_date: date, days: int,
                   kind: str = "duty", exclude_pairing: Optional[str] = None) -> float:
        """Sum duty ('duty') or block ('flight') hours over the calendar window
        of `days` days ending `end_date` inclusive: daily_history + week roster.
        Optionally exclude one pairing's rostered duties (what-if removal)."""
        k = 0 if kind == "duty" else 1
        start = end_date - timedelta(days=days - 1)
        tot = 0.0
        for d, v in self.history.get(crew_id, {}).items():
            if start <= d <= end_date:
                tot += v[k]
        for wd in self.week_duties.get(crew_id, []):
            if wd.pairing_id == exclude_pairing:
                continue
            if start <= wd.date <= end_date:
                tot += wd.duty_hours if k == 0 else wd.flight_hours
        return round(tot, 2)

    def certs_ok(self, crew_id: str, on: date):
        """(all_valid, [expired (cert_type, valid_to)])."""
        expired = [(t, vt) for t, (_vf, vt) in self.certs.get(crew_id, {}).items() if vt < on]
        return (not expired), expired


def find_data_dir(start: Optional[str] = None) -> str:
    """Locate the dataset's data/ directory (env override: CREW_OPS_DATA)."""
    env = os.environ.get("CREW_OPS_DATA")
    if env:
        return env
    root = start or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for base in (root, os.path.dirname(root)):
        hits = glob.glob(os.path.join(base, "**", "data", "flights.json"), recursive=True)
        if hits:
            return os.path.dirname(sorted(hits)[0])
    raise FileNotFoundError("dataset data/ directory not found; set CREW_OPS_DATA")


def load_world(data_dir: Optional[str] = None) -> World:
    data_dir = data_dir or find_data_dir()

    def load(name):
        with open(os.path.join(data_dir, name)) as fh:
            return json.load(fh)

    w = World(data_dir=data_dir, snapshot=parse_utc("2026-09-14T18:00:00Z"))

    for f in load("flights.json"):
        fl = Flight(
            flight_id=f["flight_id"], flight_no=f["flight_no"],
            date=date.fromisoformat(f["date"]),
            dep_station=f["dep_station"], arr_station=f["arr_station"],
            dep_utc=parse_utc(f["dep_utc"]), arr_utc=parse_utc(f["arr_utc"]),
            block_hours=f["block_hours"], aircraft=f["aircraft"],
            aircraft_type=f["aircraft_type"], seats=f["seats"])
        w.flights[fl.flight_id] = fl
        w.flights_list.append(fl)

    for c in load("crew.json"):
        w.crew[c["crew_id"]] = CrewMember(
            crew_id=c["crew_id"], name=c["name"], rank=c["rank"], base=c["base"],
            ratings=tuple(c["ratings"]), seniority=c["seniority"],
            reachability_minutes=c["reachability_minutes"], status=c["status"])

    rosters = load("rosters.json")
    w.flagged_exceptions = rosters.get("flagged_exceptions", [])
    for p in rosters["pairings"]:
        days = tuple(PairingDay(
            date=date.fromisoformat(d["date"]), flights=tuple(d["flights"]),
            report_utc=parse_utc(d["report_utc"]), release_utc=parse_utc(d["release_utc"]))
            for d in p["days"])
        pairing = Pairing(pairing_id=p["pairing_id"], aircraft=p["aircraft"], days=days,
                          crew=tuple((m["crew_id"], m["role"]) for m in p["crew"]))
        w.pairings[pairing.pairing_id] = pairing
        w.pairings_list.append(pairing)
        for d in days:
            for fid in d.flights:
                w.pairing_of_flight[fid] = pairing.pairing_id

    # derived per-crew rostered duties
    for p in w.pairings_list:
        for d in p.days:
            fh = round(sum(w.flights[fid].block_hours for fid in d.flights), 2)
            duty = Duty(date=d.date, report=d.report_utc, release=d.release_utc,
                        duty_hours=d.duty_hours, flight_hours=fh, pairing_id=p.pairing_id)
            for cid, _role in p.crew:
                w.week_duties.setdefault(cid, []).append(duty)
    for v in w.week_duties.values():
        v.sort(key=lambda x: x.date)

    for c in load("duty_clocks.json"):
        cid = c["crew_id"]
        w.history[cid] = {date.fromisoformat(x["date"]): (x["duty_hours"], x["flight_hours"])
                          for x in c["daily_history"]}
        w.clocks[cid] = {
            "duty_hours_7d": c["duty_hours_7d"],
            "flight_hours_28d": c["flight_hours_28d"],
            "last_rest_ended": parse_utc(c["last_rest_ended"]) if c["last_rest_ended"] else None,
        }

    for r in load("reserve_pool.json"):
        entry = ReserveEntry(
            crew_id=r["crew_id"], base=r["base"],
            dates=frozenset(date.fromisoformat(d) for d in r["dates"]),
            window_start=r["oncall_window_utc"]["start"],
            window_end=r["oncall_window_utc"]["end"])
        w.reserves[entry.crew_id] = entry
        w.reserves_list.append(entry)

    w.certs_list = load("certifications.json")
    for c in w.certs_list:
        w.certs.setdefault(c["crew_id"], {})[c["cert_type"]] = (
            date.fromisoformat(c["valid_from"]), date.fromisoformat(c["valid_to"]))

    for r in load("risk_signals.json"):
        w.risks[r["crew_id"]] = r

    w.rules = load("rules.json")
    w.costs = load("costs.json")
    return w
