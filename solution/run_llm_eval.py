#!/usr/bin/env python3
"""End-to-end LLM eval: every question + scenario through the live advisor.

Unlike run_regression.py (which checks the deterministic engine against the
answer keys), this asks the configured LLM provider the natural-language
prompts and grades the *prose* answers: the answer key is reduced to its
essential atoms — crew/pairing/flight/rule ids and numeric values — and each
must literally appear in the answer (commas stripped). `rules_checked`
boilerplate, ranks and zero values are not graded; Q30/Q36/Q38 stay MANUAL.

  python3 run_llm_eval.py            # full run (writes llm_eval_out/)
  python3 run_llm_eval.py Q01 Q05 S2 # subset
"""

import json
import os
import re
import sys
import time

from crew_ops import db as DB
from crew_ops import load_world
from crew_ops.llm import Advisor, ProviderError, provider_from_env

MANUAL = {"Q30", "Q36", "Q38"}
SKIP_KEYS = {"rules_checked", "explanation", "note", "rank", "rules_ref",
             "action", "reasoning", "must_include", "suggested"}
ID_RE = re.compile(r"\b(C-\d{3,5}|P-\d{3,5}|DX\d{2,4}|VT-[A-Z]{3}|RULE-[A-Z]+-\d{2})\b")

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "llm_eval_out")

SCENARIO_INSTRUCTION = (
    "\n\nAssess the operational impact and recommend what crew control should "
    "do: ranked options with costs in INR and delay hours, your recommended "
    "choice, and the rule reasons for key excluded candidates. Where flights "
    "are affected, include the per-flight assessment (minimum delay, crew FDP "
    "after delay vs the limit, and the action).")


def atoms(node, key=None):
    """Essential facts of an answer key: ids, rules, non-zero numbers."""
    if key in SKIP_KEYS:
        return set()
    out = set()
    if isinstance(node, dict):
        for k, v in node.items():
            out |= atoms(v, k)
    elif isinstance(node, list):
        for v in node:
            out |= atoms(v, key)
    elif isinstance(node, str):
        out |= set(ID_RE.findall(node))
        # a timestamp answer grades on its date and hh:mm parts
        for ts in re.findall(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", node):
            out.update(ts.split("T"))
    elif isinstance(node, bool):
        pass
    elif isinstance(node, (int, float)):
        if node:
            out.add(node)
    return out


def atom_found(atom, text):
    if isinstance(atom, str):
        return atom in text
    if isinstance(atom, float) and not atom.is_integer():
        return f"{atom:g}" in text
    return re.search(rf"\b{int(atom)}\b", text) is not None


def grade(expected, answer):
    if isinstance(expected, str):
        expected = {"value": expected}
    text = answer.replace(",", "")
    want = atoms(expected)
    missing = sorted((a for a in want if not atom_found(a, text)), key=str)
    return len(want), missing


def run_item(world, item_id, prompt, expected, log):
    advisor = Advisor(world, provider_from_env())  # fresh context per item
    t0 = time.time()
    try:
        answer = advisor.ask(prompt)
        error = None
    except ProviderError as e:
        answer, error = "", str(e)
    took = time.time() - t0
    total, missing = grade(expected, answer)
    if error:
        status = "ERROR"
    elif item_id in MANUAL:
        status = "MANUAL"
    elif not missing:
        status = "PASS"
    else:
        status = "PARTIAL"
    tool_calls = sum(len(m.get("tool_calls") or []) for m in advisor.history
                     if m["role"] == "assistant")
    rec = {"id": item_id, "status": status, "atoms": total,
           "found": total - len(missing), "missing": [str(m) for m in missing],
           "seconds": round(took, 1), "tool_calls": tool_calls,
           "prompt": prompt, "answer": answer, "error": error}
    log.write(f"{item_id}: {status} {rec['found']}/{total} atoms, "
              f"{tool_calls} tool calls, {took:.0f}s"
              + (f" — missing: {', '.join(rec['missing'][:8])}" if missing else "")
              + (f" — {error}" if error else "") + "\n")
    log.flush()
    return rec


def main():
    only = set(sys.argv[1:])
    world = load_world()
    with open(os.path.join(world.data_dir, "questions.json")) as fh:
        questions = json.load(fh)
    with open(os.path.join(world.data_dir, "scenarios.json")) as fh:
        scenarios = json.load(fh)

    items = [(q["question_id"], q["prompt"], q["expected_answer"])
             for q in questions]
    items += [(s["scenario_id"],
               s["event"]["narrative"] + SCENARIO_INSTRUCTION,
               s["answer_key"]) for s in scenarios]
    if only:
        items = [i for i in items if i[0] in only]

    os.makedirs(OUT_DIR, exist_ok=True)
    provider = provider_from_env()
    try:  # CLI runs land in the same SQLite history as web-UI runs
        run_id = DB.create_run(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                               provider.name, provider.model, sorted(only),
                               len(items))
    except DB.DBError:
        run_id = None
    results = []
    with open(os.path.join(OUT_DIR, "progress.log"), "w") as log:
        log.write(f"provider={provider.name} model={provider.model} "
                  f"items={len(items)}\n")
        log.flush()
        for item_id, prompt, expected in items:
            results.append(run_item(world, item_id, prompt, expected, log))
            if run_id is not None:
                try:
                    DB.add_result(run_id, len(results) - 1, results[-1])
                except DB.DBError:
                    pass
            time.sleep(1)
    if run_id is not None:
        try:
            DB.finish_run(run_id, time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                time.gmtime()))
        except DB.DBError:
            pass

    with open(os.path.join(OUT_DIR, "results.json"), "w") as fh:
        json.dump({"provider": provider.name, "model": provider.model,
                   "results": results}, fh, indent=1)

    counts = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    auto = [r for r in results if r["status"] not in ("MANUAL", "ERROR")]
    print(f"\nprovider: {provider.name} ({provider.model})")
    for status in ("PASS", "PARTIAL", "MANUAL", "ERROR"):
        if counts.get(status):
            print(f"  {status}: {counts[status]}")
    if auto:
        cov = sum(r["found"] for r in auto) / max(1, sum(r["atoms"] for r in auto))
        print(f"  atom coverage (auto-graded): {cov:.1%}")
    print(f"full transcripts: {os.path.join(OUT_DIR, 'results.json')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
