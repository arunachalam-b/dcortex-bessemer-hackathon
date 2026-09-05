"""Tier-1 query service."""

from datetime import date


from crew_ops import query as Q


def test_lookup_crew_filters(world):
    nair = Q.lookup_crew(world, crew_id="C-1042")
    assert nair == [{"crew_id": "C-1042", "name": "A. Nair", "rank": "Captain",
                     "base": "BLR", "ratings": ["A320"], "seniority": nair[0]["seniority"],
                     "reachability_minutes": 90, "status": "active"}]
    del_captains = Q.lookup_crew(world, rank="Captain", base="DEL")
    assert all(c["rank"] == "Captain" and c["base"] == "DEL" for c in del_captains)
    assert "C-2210" in [c["crew_id"] for c in del_captains]
    by_name = Q.lookup_crew(world, name="nair")
    assert any(c["crew_id"] == "C-1042" for c in by_name)


def test_lookup_flights(world):
    dep_del = Q.lookup_flights(world, on=date(2026, 9, 15), dep_station="DEL")
    assert [f["flight_no"] for f in dep_del] == ["DX402"]
    dx412 = Q.lookup_flights(world, on=date(2026, 9, 15), flight_no="DX412")[0]
    assert dx412["aircraft"] == "VT-DXC" and dx412["seats"] == 162


def test_duty_clock_headroom(world):
    c = Q.duty_clock(world, "C-1042", date(2026, 9, 14))
    assert c["duty_hours_7d"] == 20.93
    assert c["duty_headroom_7d"] == 39.07
    assert c["flight_hours_28d"] == 64.27


def test_reserves_filtering(world):
    blr = Q.reserves(world, base="BLR", on=date(2026, 9, 15))
    assert {r["crew_id"] for r in blr} <= set(world.reserves)
    assert all(r["base"] == "BLR" for r in blr)
    c3310 = next(r for r in blr if r["crew_id"] == "C-3310")
    assert c3310["window"] == {"start": "06:00", "end": "18:00"}
    assert c3310["reachability_minutes"] == 45


def test_certifications_expiry_window(world):
    exp = Q.certifications(world, expiring_from=date(2026, 9, 15),
                           expiring_to=date(2026, 10, 15))
    ids = {(c["crew_id"], c["cert_type"]) for c in exp}
    assert ("C-5417", "recurrent_training") in ids
    assert ("C-2087", "licence") in ids
    assert all(date(2026, 9, 15) <= date.fromisoformat(c["valid_to"])
               <= date(2026, 10, 15) for c in exp)


def test_risk_signals(world):
    r = Q.risk_signals(world, crew_id="C-1042")[0]
    assert r["score"] == 0.78
    high = Q.risk_signals(world, min_score=0.6)
    assert all(x["score"] >= 0.6 for x in high)
    assert any(x["crew_id"] == "C-1042" for x in high)


def test_pairing_info_lookups(world):
    by_id = Q.pairing_info(world, pairing_id="P-2291")[0]
    assert len(by_id["days"]) == 2
    assert by_id["days"][0]["report_utc"] == "2026-09-15T06:00:00Z"
    by_crew = Q.pairing_info(world, crew_id="C-1042")
    assert any(p["pairing_id"] == "P-2291" for p in by_crew)
    by_ac = Q.pairing_info(world, aircraft="VT-DXB", on=date(2026, 9, 16))
    assert len(by_ac) == 1


def test_duty_watchlist(world):
    wl = Q.crew_over_duty_threshold(world, date(2026, 9, 15), 45)
    assert [x["crew_id"] for x in wl] == ["C-2087", "C-3305"]
    assert wl[0]["duty_hours_7d"] == 51.83
    assert wl[1]["duty_hours_7d"] == 50.0
