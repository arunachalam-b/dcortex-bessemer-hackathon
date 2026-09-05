"""World loading, indexing and rolling-window arithmetic.

The strongest check here: our window computation must reproduce the published
duty_hours_7d / flight_hours_28d summaries for EVERY crew member — that pins
the calendar-window convention (daily_history + rostered week duties).
"""

from datetime import date

from crew_ops.world import hrs, parse_utc


def test_load_counts(world):
    assert len(world.flights) == 147
    assert len(world.crew) == 150
    assert len(world.pairings) == 39
    assert len(world.reserves) == 16
    assert len(world.certs) == 150  # 4 cert types per crew


def test_flight_index_and_pairing_of_flight(world):
    f = world.flight("DX412-2026-09-15")
    assert (f.dep_station, f.arr_station, f.aircraft, f.seats) == ("BLR", "BOM", "VT-DXC", 162)
    p, day = world.pairing_day_of_flight("DX412-2026-09-15")
    assert p.pairing_id == "P-2291"
    assert day.date == date(2026, 9, 15)
    assert day.sectors == 3


def test_engineered_pairing_p2291(world):
    p = world.pairings["P-2291"]
    assert [world.flights[f].flight_no for f in p.days[0].flights] == ["DX412", "DX413", "DX588"]
    assert [world.flights[f].flight_no for f in p.days[1].flights] == ["DX589", "DX590", "DX591"]
    assert ("C-1042", "Captain") in p.crew


def test_duty_period_convention(world):
    # report = first dep - 60 min; release = last arr + 30 min
    p = world.pairings["P-2291"]
    d1 = p.days[0]
    first = world.flights[d1.flights[0]]
    last = world.flights[d1.flights[-1]]
    assert hrs(first.dep_utc - d1.report_utc) == 1.0
    assert hrs(d1.release_utc - last.arr_utc) == 0.5


def test_window_sums_reproduce_published_clocks(world):
    """Engine window arithmetic == every published clock summary (150 crew)."""
    end = date(2026, 9, 14)
    for cid, clock in world.clocks.items():
        assert abs(world.window_sum(cid, end, 7) - clock["duty_hours_7d"]) < 0.05, cid
        assert abs(world.window_sum(cid, end, 28, kind="flight")
                   - clock["flight_hours_28d"]) < 0.05, cid


def test_window_sum_includes_rostered_plan(world):
    # C-1042 works P-2291 on 15-16 Sep: the window ending on the 15th must
    # include that planned duty on top of history.
    base = world.window_sum("C-1042", date(2026, 9, 14), 7)
    with_plan = world.window_sum("C-1042", date(2026, 9, 15), 7)
    day1 = world.pairings["P-2291"].days[0].duty_hours
    assert with_plan > base  # plan included
    assert with_plan >= day1


def test_window_sum_exclude_pairing(world):
    incl = world.window_sum("C-1042", date(2026, 9, 15), 7)
    excl = world.window_sum("C-1042", date(2026, 9, 15), 7, exclude_pairing="P-2291")
    assert round(incl - excl, 2) == world.pairings["P-2291"].days[0].duty_hours


def test_fdp_limit_reduction(world):
    assert world.fdp_limit(1) == 13.0
    assert world.fdp_limit(2) == 13.0
    assert world.fdp_limit(3) == 12.5
    assert world.fdp_limit(4) == 12.0


def test_certs_ok_engineered_lapse(world):
    ok_before, _ = world.certs_ok("C-5417", date(2026, 9, 17))
    ok_after, expired = world.certs_ok("C-5417", date(2026, 9, 19))
    assert ok_before and not ok_after
    assert expired[0][0] == "recurrent_training"
    assert str(expired[0][1]) == "2026-09-17"


def test_snapshot(world):
    assert world.snapshot == parse_utc("2026-09-14T18:00:00Z")
