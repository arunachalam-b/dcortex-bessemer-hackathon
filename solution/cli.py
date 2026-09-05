#!/usr/bin/env python3
"""Crew Ops Advisor — CLI.

Engine-only commands (no LLM, no keys needed):

  python3 cli.py tools                       # list tools + parameters
  python3 cli.py call <tool> '<json-args>'   # invoke one tool
  python3 cli.py demo                        # walk the flagship S2 disruption
  python3 cli.py repl                        # interactive tool shell

AI advisor commands (configure a provider in solution/.env — see
.env.example; switch Claude <-> Sarvam by changing LLM_PROVIDER):

  python3 cli.py ask "Who can cover P-2291 if C-1042 is sick?"
  python3 cli.py chat                        # multi-turn advisor session

Examples:
  python3 cli.py call get_reserves '{"base": "BLR", "date": "2026-09-15"}'
  python3 cli.py call recommend_cover \\
      '{"pairing_id": "P-2291", "role": "Captain", "sick_crew_id": "C-1042"}'
"""

import json
import os
import sys

from crew_ops import load_world
from crew_ops import tools as T


def show(resp, max_trace=12):
    if not resp.get("ok"):
        print(f"REFUSED: {resp.get('error')}")
        if resp.get("hint"):
            print(f"  hint: {resp['hint']}")
        return
    result = dict(resp["result"]) if isinstance(resp["result"], dict) else resp["result"]
    trace = result.pop("trace", None) if isinstance(result, dict) else None
    print(json.dumps(result, indent=2, default=str))
    print(f"\nsources: {', '.join(resp['sources'])}")
    if trace:
        print("reasoning:")
        for step in trace[:max_trace]:
            print(f"  - {step}")


def demo(world):
    print("=" * 72)
    print("DEMO — 05:00Z, 15 Sep: Captain C-1042 calls in sick (pairing P-2291)")
    print("=" * 72)
    steps = [
        ("1. Who is C-1042?", "lookup_crew", {"crew_id": "C-1042"}),
        ("2. What breaks?", "simulate_sick_crew",
         {"crew_id": "C-1042", "reported_utc": "2026-09-15T05:00:00Z"}),
        ("3. Can C-2087 take it?", "check_assignment_legality",
         {"crew_id": "C-2087", "pairing_id": "P-2291"}),
        ("4. What should I do?", "recommend_cover",
         {"pairing_id": "P-2291", "role": "Captain", "sick_crew_id": "C-1042"}),
        ("5. Draft the callout", "draft_notification",
         {"crew_id": "C-3310", "pairing_id": "P-2291"}),
    ]
    for title, tool, args in steps:
        print(f"\n--- {title}  [{tool}] ---")
        resp = T.dispatch(world, tool, args)
        if tool == "recommend_cover" and resp["ok"]:
            r = resp["result"]
            print(f"{len(r['options'])} options "
                  f"({len(r['excluded_candidates'])} candidates excluded):")
            for o in r["options"][:4]:
                print(f"  #{o['rank']} {o['action']}: INR {o['cost_inr']:,}"
                      + (f", ~{o['delay_hours']}h delay" if o["delay_hours"] else ""))
            print("excluded (sample):")
            for e in r["excluded_candidates"][:3]:
                print(f"  x {e['crew_id']}: {e['reason']}")
        elif tool == "draft_notification" and resp["ok"]:
            print(resp["result"]["message"])
        else:
            show(resp, max_trace=6)


def repl(world):
    print("crew-ops> tool shell — '<tool> <json-args>', 'tools', or 'quit'")
    while True:
        try:
            line = input("crew-ops> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not line or line in ("quit", "exit"):
            break
        if line == "tools":
            for s in T.tool_schemas():
                print(f"  {s['name']}: {s['description']}")
            continue
        parts = line.split(None, 1)
        args = {}
        if len(parts) > 1:
            try:
                args = json.loads(parts[1])
            except json.JSONDecodeError as e:
                print(f"bad JSON args: {e}")
                continue
        show(T.dispatch(world, parts[0], args))


def make_advisor(world):
    from crew_ops.llm import Advisor, ConfigError, provider_from_env
    try:
        provider = provider_from_env()
    except ConfigError as e:
        print(f"config error: {e}")
        return None

    def on_event(kind, p):
        if kind == "tool_call":
            print(f"  -> {p['name']}({json.dumps(p['args'])})")
        elif kind == "tool_result" and not p["ok"]:
            print(f"     x {p['name']} refused (relayed to the model)")

    print(f"[AI layer: provider={provider.name} model={provider.model}]")
    return Advisor(world, provider, on_event=on_event,
                   max_steps=int(os.environ.get("LLM_MAX_STEPS", "16")))


def ask(world, question):
    from crew_ops.llm import ProviderError
    advisor = make_advisor(world)
    if advisor is None:
        return 1
    try:
        answer = advisor.ask(question)
    except ProviderError as e:
        print(f"provider error: {e}")
        return 1
    print(f"\n{answer}")
    return 0


def chat(world):
    from crew_ops.llm import ProviderError
    advisor = make_advisor(world)
    if advisor is None:
        return 1
    print("crew-ops-ai> ask in plain language — 'quit' to exit")
    while True:
        try:
            line = input("crew-ops-ai> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not line or line in ("quit", "exit"):
            break
        try:
            print(f"\n{advisor.ask(line)}\n")
        except ProviderError as e:
            print(f"provider error: {e}")
    return 0


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        return 0
    world = load_world()
    cmd = sys.argv[1]
    if cmd == "tools":
        for s in T.tool_schemas():
            params = ", ".join(
                k + ("*" if v.get("required") else "")
                for k, v in s["input_schema"]["properties"].items())
            print(f"{s['name']}({params})\n    {s['description']}")
    elif cmd == "call":
        if len(sys.argv) < 3:
            print("usage: cli.py call <tool> ['<json-args>']")
            return 1
        args = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}
        show(T.dispatch(world, sys.argv[2], args))
    elif cmd == "demo":
        demo(world)
    elif cmd == "repl":
        repl(world)
    elif cmd == "ask":
        if len(sys.argv) < 3:
            print('usage: cli.py ask "<question>"')
            return 1
        return ask(world, " ".join(sys.argv[2:]))
    elif cmd == "chat":
        return chat(world)
    else:
        print(f"unknown command '{cmd}'\n{__doc__}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
