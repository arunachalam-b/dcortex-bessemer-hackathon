"""Tier-2 simulation engine: sick crew, closures, delays, certs, rest, cancels."""

from datetime import date

from crew_ops import simulation as S
from crew_ops.world import parse_utc


def test_sick_crew_multiday_pairing(world):
    imp = S.sick_crew_impact(world, "C-1042", "P-2291",
                             parse_utc("2026-09-15T05:00:00Z"))
    assert imp["pairing_broken"] == "P-2291"
    assert imp["role"] == "Captain"
    assert [world.flights[f].flight_no for f in imp["per_day"][0]["flights"]] == \
        ["DX412", "DX413", "DX588"]
    assert [world.flights[f].flight_no for f in imp["per_day"][1]["flights"]] == \
        ["DX589", "DX590", "DX591"]
    assert imp["per_day"][0]["passengers"] == 486  # 3 x A320 (162)


def test_sick_crew_reported_mid_pairing_only_remaining_days(world):
    """Called in sick on day 2: only day 2 legs are uncovered."""
    imp = S.sick_crew_impact(world, "C-1042", "P-2291",
                             parse_utc("2026-09-16T01:00:00Z"))
    assert len(imp["per_day"]) == 1
    assert imp["per_day"][0]["date"] == "2026-09-16"


def test_sick_crew_resolves_pairing_from_roster(world):
    """No pairing_id given: engine finds the crew member's rostered pairing."""
    imp = S.sick_crew_impact(world, "C-1042",
                             reported_utc=parse_utc("2026-09-15T05:00:00Z"))
    assert imp["pairing_broken"] == "P-2291"


def test_station_closure_blr(world):
    r = S.station_closure_impact(world, "BLR",
                                 parse_utc("2026-09-17T08:00:00Z"),
                                 parse_utc("2026-09-17T14:00:00Z"))
    assert r["affected_flights"]  # non-empty
    for pf in r["per_flight_assessment"]:
        assert pf["min_delay_hours"] > 0
        assert pf["action"].startswith("delay")
        # feasibility claim must match the arithmetic it reports
        feasible = pf["crew_fdp_after_delay"] <= pf["fdp_limit"]
        assert (pf["action"] == "delay (crew legal)") == feasible


def test_station_closure_excludes_flights_outside_window(world):
    r = S.station_closure_impact(world, "BLR",
                                 parse_utc("2026-09-17T08:00:00Z"),
                                 parse_utc("2026-09-17T14:00:00Z"))
    for fid in r["affected_flights"]:
        f = world.flights[fid]
        assert str(f.date) == "2026-09-17"
        in_dep = f.dep_station == "BLR" and "08:00" <= f.dep_utc.strftime("%H:%M") < "14:00"
        in_arr = f.arr_station == "BLR" and "08:00" <= f.arr_utc.strftime("%H:%M") < "14:00"
        assert in_dep or in_arr


def test_delay_breach_and_legal_prefix(world):
    r = S.delay_impact(world, "VT-DXA", date(2026, 9, 16), 1.5)
    assert r["breach"] is True
    assert r["fdp_after_delay"] == 12.75 and r["fdp_limit"] == 12.0
    assert r["legal_prefix_sectors"] == 3
    assert r["uncoverable_flight_nos"] == ["DX404"]
    assert r["prefix_fdp"] == 9.5 and r["prefix_fdp_limit"] == 12.5


def test_delay_no_breach(world):
    r = S.delay_impact(world, "VT-DXA", date(2026, 9, 16), 0.5)
    assert r["breach"] is False
    assert r["uncoverable_flight_nos"] == []


def test_cert_expiry_impact(world):
    r = S.cert_expiry_impact(world, "C-5417", date(2026, 9, 19))
    assert r["legal"] is False and r["rule"] == "RULE-CERT-06"
    assert r["expired"][0]["cert_type"] == "recurrent_training"
    ok = S.cert_expiry_impact(world, "C-5417", date(2026, 9, 16))
    assert ok["legal"] is True and ok["rule"] is None


def test_check_assignment_default_excludes_covered_pairing(world):
    r = S.check_assignment(world, "C-2087", "P-2291")
    assert r["legal"] is False
    assert any("RULE-DUTY-02" in i for i in r["issues"])
    assert r["rules_checked"] == ["RULE-FDP-01", "RULE-DUTY-02", "RULE-FLT-03",
                                  "RULE-REST-04", "RULE-QUAL-05", "RULE-CERT-06",
                                  "RULE-BASE-07"]


def test_rest_requirement_tool(world):
    r = S.rest_requirement(world, parse_utc("2026-09-16T15:30:00Z"))
    assert r["earliest_next_report_utc"] == "2026-09-17T03:30:00Z"


def test_cancellation_impact(world):
    r = S.cancellation_impact(world, "DX404-2026-09-16")
    assert r["passengers"] == 162 and r["cost_inr"] == 250000


def test_simulations_do_not_mutate_world(world):
    """Scenario independence: running one simulation leaves the base state
    untouched for the next question."""
    before = world.window_sum("C-1042", date(2026, 9, 15), 7)
    S.sick_crew_impact(world, "C-1042", "P-2291", parse_utc("2026-09-15T05:00:00Z"))
    S.delay_impact(world, "VT-DXA", date(2026, 9, 16), 1.5)
    S.station_closure_impact(world, "BLR", parse_utc("2026-09-17T08:00:00Z"),
                             parse_utc("2026-09-17T14:00:00Z"))
    assert world.window_sum("C-1042", date(2026, 9, 15), 7) == before
    assert ("C-1042", "Captain") in world.pairings["P-2291"].crew
