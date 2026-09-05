"""Rules engine against the dataset's engineered teaching cases.

These are the exact traps the dataset README documents; each one pins a rule's
arithmetic, not just its verdict.
"""

from datetime import date

from crew_ops import rules as R
from crew_ops.world import parse_utc


def _p2291_days(world):
    return list(world.pairings["P-2291"].days)


def test_c2087_breaches_duty02_by_1h20m(world):
    """The flagship trap: C-2087 covering P-2291 exceeds 60h/7d by exactly 1h20m."""
    chk = R.evaluate_cover(world, "C-2087", _p2291_days(world), exclude_pairing="P-2291")
    assert not chk.legal
    assert chk.issues[0] == ("RULE-DUTY-02: would exceed 60h/7d by 1h20m "
                             "on 2026-09-15 (total 61.33h)")
    v = next(v for v in chk.verdicts if v.rule_id == "RULE-DUTY-02" and not v.ok)
    assert v.computed["total_hours"] == 61.33
    assert v.computed["limit"] == 60


def test_c3305_legal_day1_breaches_day2(world):
    """Reserve C-3305: fine for day 1 in isolation, breaches DUTY-02 on day 2 —
    a per-day check that forgets multi-day pairings gets this wrong."""
    days = _p2291_days(world)
    day1_only = R.evaluate_cover(world, "C-3305", days[:1], exclude_pairing="P-2291")
    assert day1_only.legal
    full = R.evaluate_cover(world, "C-3305", days, exclude_pairing="P-2291")
    assert not full.legal
    assert full.issues == ["RULE-DUTY-02: would exceed 60h/7d by 8h15m "
                           "on 2026-09-16 (total 68.25h)"]


def test_c2091_fails_qual05_for_a320(world):
    chk = R.evaluate_cover(world, "C-2091", _p2291_days(world), exclude_pairing="P-2291")
    assert not chk.legal
    assert chk.issues == ["RULE-QUAL-05: no A320 rating"]


def test_c5417_fails_cert06_on_sep19(world):
    p = world.pairing_for("VT-DXB", date(2026, 9, 19))
    days = [d for d in p.days if d.date == date(2026, 9, 19)]
    chk = R.evaluate_cover(world, "C-5417", days, exclude_pairing=p.pairing_id)
    assert not chk.legal
    assert "RULE-CERT-06: certification invalid on 2026-09-19" in chk.issues


def test_c3310_clean_cover(world):
    chk = R.evaluate_cover(world, "C-3310", _p2291_days(world), exclude_pairing="P-2291")
    assert chk.legal and chk.issues == []
    # all 7 rules represented in the verdicts
    assert {v.rule_id for v in chk.verdicts} >= {
        "RULE-QUAL-05", "RULE-CERT-06", "RULE-FDP-01", "RULE-REST-04",
        "RULE-DUTY-02", "RULE-FLT-03"}


def test_c2210_deadhead_legal_with_delay(world):
    chk = R.evaluate_cover(world, "C-2210", _p2291_days(world),
                           exclude_pairing="P-2291", delay_h=3.0)
    assert chk.legal


def test_line_captain_downstream_rest_conflict(world):
    """C-5837 (works 14/17/20 Sep) covering P-2291 (15-16 Sep) collides with
    their own 17 Sep duty — a downstream conflict, not a same-day one."""
    chk = R.evaluate_cover(world, "C-5837", _p2291_days(world))
    assert not chk.legal
    assert chk.issues == ["RULE-REST-04: only 10.75h rest before P-2204 "
                          "on 2026-09-17 (downstream conflict)"]


def test_fdp_breach_message(world):
    """An over-long duty day trips RULE-FDP-01 with the sector-reduced limit.
    (A whole-duty shift keeps FDP length constant — both report and release
    move — so we stretch the release to build the breach case.)"""
    from datetime import timedelta
    from crew_ops.world import PairingDay
    p = world.pairing_for("VT-DXA", date(2026, 9, 16))
    day = next(d for d in p.days if d.date == date(2026, 9, 16))
    stretched = PairingDay(date=day.date, flights=day.flights,
                           report_utc=day.report_utc,
                           release_utc=day.release_utc + timedelta(hours=2))
    chk = R.evaluate_cover(world, "C-3310", [stretched])
    assert "RULE-FDP-01: FDP 13.25h > 12.0h limit (4 sectors)" in chk.issues


def test_whole_duty_shift_preserves_fdp(world):
    """A positioned/late start shifts report AND release: FDP length is
    unchanged, so no FDP issue — the extension case lives in delay_impact."""
    p = world.pairing_for("VT-DXA", date(2026, 9, 16))
    day = next(d for d in p.days if d.date == date(2026, 9, 16))
    chk = R.evaluate_cover(world, "C-3310", [day], delay_h=1.5)
    fdp = next(v for v in chk.verdicts if v.rule_id == "RULE-FDP-01")
    assert fdp.ok and fdp.computed["fdp_hours"] == day.duty_hours


def test_rest_requirement(world):
    rel = parse_utc("2026-09-16T15:30:00Z")
    assert R.rest_requirement(world, rel) == parse_utc("2026-09-17T03:30:00Z")


def test_reserve_window_report_time_not_callout_time(world):
    """The REQUIRED REPORT time must fall in the window (dataset README):
    C-3310 (06:00-18:00) covers a 06:00Z report but not a 02:30Z one."""
    ok, _ = R.reserve_window_covers(world, "C-3310", parse_utc("2026-09-15T06:00:00Z"))
    assert ok
    ok, _ = R.reserve_window_covers(world, "C-3310", parse_utc("2026-09-18T02:30:00Z"))
    assert not ok


def test_verdicts_carry_arithmetic(world):
    """Explainability contract: every verdict exposes the computed numbers."""
    chk = R.evaluate_cover(world, "C-2087", _p2291_days(world), exclude_pairing="P-2291")
    duty = [v for v in chk.verdicts if v.rule_id == "RULE-DUTY-02"]
    assert all("existing_hours" in v.computed and "cover_hours" in v.computed
               and "total_hours" in v.computed for v in duty)
    assert chk.trace  # human-readable steps present
