"""Tier-3 recommender: the engineered options, costs and exclusions from the
dataset README, plus ranking and joint-plan invariants."""

from datetime import date

from crew_ops import recommender as REC


def _s2(world):
    return REC.cover_options(world, "P-2291", "Captain", sick_crew_id="C-1042")


def test_s2_top_option_is_reserve_c3310_at_18500(world):
    r = _s2(world)
    top = r["options"][0]
    assert top["crew_id"] == "C-3310"
    assert top["cost_inr"] == 18500
    assert top["legal"] is True and top["rank"] == 1
    assert top["delay_hours"] == 0.0


def test_s2_c2210_deadhead_costs_41200_with_3h_delay(world):
    r = _s2(world)
    o = next(o for o in r["options"] if o["crew_id"] == "C-2210")
    assert o["cost_inr"] == 41200  # 18500 callout + 6500 deadhead + 3h x 5400
    assert o["delay_hours"] == 3.0
    items = {c["item"]: c["inr"] for c in o["cost_breakdown"]}
    assert items["reserve callout"] == 18500
    assert items["deadhead positioning"] == 6500
    assert items["3.0h departure delay"] == 16200


def test_s2_engineered_exclusions(world):
    r = _s2(world)
    reasons = {e["crew_id"]: e["reason"] for e in r["excluded_candidates"]}
    assert "RULE-DUTY-02" in reasons["C-2087"] and "1h20m" in reasons["C-2087"]
    # C-3305's 00:00-05:30 window can't take the 06:00Z report (the DUTY-02
    # day-2 trap shows in the direct legality check, tested in test_rules)
    assert "on-call window" in reasons["C-3305"]
    assert reasons["C-2091"] == "RULE-QUAL-05: no A320 rating"
    # crew on leave never appear anywhere
    on_leave = {c.crew_id for c in world.crew.values() if c.status != "active"}
    mentioned = {o["crew_id"] for o in r["options"]} | set(reasons)
    assert not (on_leave & mentioned)


def test_options_ranked_by_cost_cancellation_last(world):
    r = _s2(world)
    costs = [o["cost_inr"] for o in r["options"][:-1]]
    assert costs == sorted(costs)
    assert [o["rank"] for o in r["options"]] == list(range(1, len(r["options"]) + 1))
    last = r["options"][-1]
    assert last["crew_id"] is None and last["cost_inr"] == 250000 * 6  # 6 legs


def test_every_option_carries_verdicts_and_reasoning(world):
    r = _s2(world)
    for o in r["options"][:-1]:
        assert o["rules_checked"], o
        assert o["reasoning"]
        assert {v["rule_id"] for v in o["verdicts"]} >= {"RULE-DUTY-02", "RULE-FDP-01"}
        assert sum(c["inr"] for c in o["cost_breakdown"]) == o["cost_inr"]


def test_reserve_window_gates_early_report(world):
    """S6 morning (report 01:30Z): C-3310's 06:00-18:00 window excludes them;
    C-3305's 00:00-05:30 window qualifies."""
    p = world.pairing_for("VT-DXA", date(2026, 9, 18))
    sick = next(m for m, r in p.crew if r == "Captain")
    r = REC.cover_options(world, p.pairing_id, "Captain", sick_crew_id=sick)
    excl = {e["crew_id"]: e["reason"] for e in r["excluded_candidates"]}
    assert "on-call window" in excl["C-3310"]
    assert any(o["crew_id"] == "C-3305" for o in r["options"])


def test_joint_plan_s6(world):
    events = []
    for ac in ("VT-DXA", "VT-DXB"):
        p = world.pairing_for(ac, date(2026, 9, 18))
        sick = next(m for m, r in p.crew if r == "Captain")
        events.append({"pairing_id": p.pairing_id, "role": "Captain",
                       "sick_crew_id": sick})
    j = REC.joint_plan(world, events)
    assert j["total_cost_inr"] == 42500  # 18500 reserve + 24000 day-off
    a, b = j["assignments"]
    assert a["crew_id"] != b["crew_id"]
    assert {a["cost_inr"], b["cost_inr"]} == {18500, 24000}


def test_joint_plan_never_double_books(world):
    """Same sick captain scenario duplicated: the scarce reserve can only be
    used once; the second pairing must get a different (pricier) cover."""
    p = world.pairing_for("VT-DXA", date(2026, 9, 18))
    sick = next(m for m, r in p.crew if r == "Captain")
    ev = {"pairing_id": p.pairing_id, "role": "Captain", "sick_crew_id": sick}
    j = REC.joint_plan(world, [ev, dict(ev)])
    a, b = j["assignments"]
    assert a["crew_id"] != b["crew_id"]


def test_delay_recovery_s4(world):
    r = REC.delay_recovery(world, "VT-DXA", date(2026, 9, 16), 1.5)
    assert r["breach"] is True
    opt_a, opt_b = r["options"]
    assert opt_a["cost_inr"] == 75000   # 2 pilots x 18500 + 4 cabin x 9500
    assert "DX401–DX403" in opt_a["action"] and "DX404" in opt_a["action"]
    assert opt_b["action"] == "Cancel DX404" and opt_b["cost_inr"] == 250000
    assert r["recommended"] is r["options"][0]


def test_delay_recovery_no_breach_no_options(world):
    r = REC.delay_recovery(world, "VT-DXA", date(2026, 9, 16), 0.25)
    assert r["breach"] is False and r["options"] == []


def test_cabin_crew_cover_uses_cabin_rates(world):
    ex = world.flagged_exceptions[0]
    p = world.pairing_for("VT-DXB", date.fromisoformat(ex["date"]))
    r = REC.cover_options(world, p.pairing_id, "Cabin Crew",
                          sick_crew_id=ex["crew_id"])
    top = r["options"][0]
    assert top["cost_inr"] == 9500  # cabin reserve callout, not pilot rate


def test_notification_draft_facts(world):
    n = REC.draft_notification(world, "C-3310", "P-2291")
    msg = n["message"]
    for token in ["C-3310", "P-2291", "06:00Z", "BLR", "DX412/DX413/DX588",
                  "DX589/DX590/DX591", "04:00Z", "DEL", "hotel", "acknowledge"]:
        assert token in msg, token
    assert n["facts"]["days"][0]["report_utc"] == "2026-09-15T06:00:00Z"
    assert n["facts"]["days"][1]["report_station"] == "DEL"
