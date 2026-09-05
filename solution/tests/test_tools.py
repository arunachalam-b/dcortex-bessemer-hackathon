"""The LLM boundary: every tool dispatches JSON-in/JSON-out, errors are
answers (honest refusal), and traces/sources ride along for grounding."""

import json

from crew_ops import tools as T


def test_schemas_are_json_serializable_and_complete(world):
    schemas = T.tool_schemas()
    json.dumps(schemas)  # must be valid for any LLM adapter
    names = {s["name"] for s in schemas}
    assert {"lookup_crew", "lookup_flights", "get_duty_clock", "get_reserves",
            "get_certifications", "get_risk_signals", "get_pairing",
            "get_duty_watchlist", "simulate_sick_crew", "simulate_station_closure",
            "simulate_delay", "check_certification_validity",
            "check_assignment_legality", "compute_rest_requirement",
            "cancellation_impact", "recommend_cover", "recommend_joint",
            "recommend_delay_recovery", "draft_notification"} <= names
    for s in schemas:
        assert s["description"]
        assert s["input_schema"]["type"] == "object"


def test_dispatch_tier1(world):
    r = T.dispatch(world, "get_duty_clock", {"crew_id": "C-1042",
                                             "end_date": "2026-09-14"})
    assert r["ok"] and r["result"]["duty_hours_7d"] == 20.93
    assert "duty_clocks.json" in r["sources"]


def test_dispatch_tier2_carries_trace(world):
    r = T.dispatch(world, "check_assignment_legality",
                   {"crew_id": "C-2087", "pairing_id": "P-2291"})
    assert r["ok"] and r["result"]["legal"] is False
    assert r["trace"], "non-trivial answers must carry reasoning"


def test_dispatch_tier3(world):
    r = T.dispatch(world, "recommend_cover",
                   {"pairing_id": "P-2291", "role": "Captain",
                    "sick_crew_id": "C-1042"})
    assert r["ok"] and r["result"]["options"][0]["crew_id"] == "C-3310"
    json.dumps(r)  # entire response must survive the wire


def test_unknown_tool_is_refused_not_raised(world):
    r = T.dispatch(world, "predict_the_weather", {})
    assert r["ok"] is False and "unknown tool" in r["error"]


def test_bad_args_become_honest_refusals(world):
    r = T.dispatch(world, "check_assignment_legality",
                   {"crew_id": "C-9999", "pairing_id": "P-2291"})
    assert r["ok"] is False and "cannot answer reliably" in r["hint"]
    r = T.dispatch(world, "simulate_delay",
                   {"aircraft": "VT-XXXX", "date": "2026-09-16", "delay_hours": 1.0})
    assert r["ok"] is False
    r = T.dispatch(world, "lookup_flights", {"date": "not-a-date"})
    assert r["ok"] is False


def test_all_responses_json_serializable(world):
    calls = [
        ("lookup_crew", {"rank": "Captain", "base": "DEL"}),
        ("lookup_flights", {"date": "2026-09-15", "dep_station": "DEL"}),
        ("get_reserves", {"base": "BLR", "date": "2026-09-15"}),
        ("get_certifications", {"expiring_from": "2026-09-15",
                                "expiring_to": "2026-10-15"}),
        ("get_risk_signals", {"min_score": 0.6}),
        ("get_pairing", {"pairing_id": "P-2291"}),
        ("get_duty_watchlist", {"end_date": "2026-09-15"}),
        ("simulate_sick_crew", {"crew_id": "C-1042",
                                "reported_utc": "2026-09-15T05:00:00Z"}),
        ("simulate_station_closure", {"station": "BLR",
                                      "window_start_utc": "2026-09-17T08:00:00Z",
                                      "window_end_utc": "2026-09-17T14:00:00Z"}),
        ("simulate_delay", {"aircraft": "VT-DXA", "date": "2026-09-16",
                            "delay_hours": 1.5}),
        ("check_certification_validity", {"crew_id": "C-5417",
                                          "date": "2026-09-19"}),
        ("compute_rest_requirement", {"release_utc": "2026-09-16T15:30:00Z"}),
        ("cancellation_impact", {"flight_id": "DX404-2026-09-16"}),
        ("recommend_joint", {"events": [
            {"pairing_id": "P-2205", "role": "Captain"},    # VT-DXA, 18 Sep
            {"pairing_id": "P-2212", "role": "Captain"}]}),  # VT-DXB, 18 Sep
        ("recommend_delay_recovery", {"aircraft": "VT-DXA", "date": "2026-09-16",
                                      "delay_hours": 1.5}),
        ("draft_notification", {"crew_id": "C-3310", "pairing_id": "P-2291"}),
    ]
    for name, args in calls:
        r = T.dispatch(world, name, args)
        assert r["ok"], (name, r)
        json.dumps(r)
