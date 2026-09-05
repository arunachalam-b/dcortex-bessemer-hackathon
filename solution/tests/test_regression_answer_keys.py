"""The dataset ships its own ground truth — this makes it the test suite.

Every questions.json item (except the three open-ended prose ones) and every
scenarios.json answer key must be reproduced by the engine exactly.
"""

import json
import os

import pytest

from crew_ops.regression import (MANUAL, answer_question, answer_scenario,
                                 compare, run_all)


def _load(world, name):
    with open(os.path.join(world.data_dir, name)) as fh:
        return json.load(fh)


def _question_ids():
    # ids are stable (Q01..Q38); parametrize without loading the world
    return [f"Q{i:02d}" for i in range(1, 39)]


@pytest.mark.parametrize("qid", _question_ids())
def test_question(world, qid):
    q = next(x for x in _load(world, "questions.json") if x["question_id"] == qid)
    got = answer_question(world, qid)
    if qid in MANUAL:
        assert got  # open-ended: we still produce an answer; scoring is human
        return
    diffs = compare(q["expected_answer"], got)
    assert not diffs, "\n".join(diffs)


@pytest.mark.parametrize("sid", ["S1", "S2", "S3", "S4", "S5", "S6"])
def test_scenario(world, sid):
    sc = next(x for x in _load(world, "scenarios.json") if x["scenario_id"] == sid)
    got = answer_scenario(world, sc)
    diffs = compare(sc["answer_key"], got)
    assert not diffs, "\n".join(diffs)


def test_scoreboard_is_green(world):
    res = run_all(world)
    assert res["passed"] == res["auto_total"], [
        (r["id"], r["diffs"]) for r in res["rows"] if r["status"] not in ("PASS", "MANUAL")]


def test_manual_questions_state_their_limits():
    """Q30/Q36/Q38 are open-ended prose; they are flagged for human judging,
    never silently auto-passed (honest-limits contract)."""
    assert MANUAL == {"Q30", "Q36", "Q38"}
