#!/usr/bin/env python3
"""Crew Ops Advisor — local web UI.

  python3 server.py [port]          # default port 8765

Serves web/index.html plus a JSON API over the same deterministic engine
and provider-switchable AI layer the CLI uses:

  GET  /api/meta          provider info, tool schemas, dataset counts
  GET  /api/dataset       questions.json + scenarios.json (with eval prompts)
  POST /api/chat          {"session_id", "message"} -> NDJSON event stream
  POST /api/chat/reset    {"session_id"} -> fresh advisor context
  POST /api/eval/start    {"ids": [...]} (empty/absent = all items)
  GET  /api/eval/status   live progress + graded results
"""

import json
import os
import sys
import threading
import time
import traceback
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from crew_ops import load_world
from crew_ops import tools as T
from crew_ops.llm import Advisor, ConfigError, ProviderError, provider_from_env
from run_llm_eval import MANUAL, OUT_DIR, SCENARIO_INSTRUCTION, grade

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(BASE_DIR, "web")

WORLD = load_world()

_sessions = {}          # session_id -> {"advisor": Advisor, "lock": Lock}
_sessions_lock = threading.Lock()

_eval = {"running": False, "total": 0, "results": [], "provider": None,
         "model": None, "error": None, "started_utc": None}
_eval_lock = threading.Lock()


def _provider_meta():
    try:
        p = provider_from_env()
        return {"provider": p.name, "model": p.model, "error": None}
    except ConfigError as e:
        return {"provider": None, "model": None, "error": str(e)}


def _load_dataset():
    with open(os.path.join(WORLD.data_dir, "questions.json")) as fh:
        questions = json.load(fh)
    with open(os.path.join(WORLD.data_dir, "scenarios.json")) as fh:
        scenarios = json.load(fh)
    for s in scenarios:
        s["prompt"] = s["event"]["narrative"] + SCENARIO_INSTRUCTION
    return questions, scenarios


def _eval_items(ids):
    questions, scenarios = _load_dataset()
    items = [(q["question_id"], q["prompt"], q["expected_answer"])
             for q in questions]
    items += [(s["scenario_id"], s["prompt"], s["answer_key"])
              for s in scenarios]
    if ids:
        wanted = set(ids)
        items = [i for i in items if i[0] in wanted]
    return items


def _run_eval(ids):
    try:
        provider = provider_from_env()
        items = _eval_items(ids)
    except ConfigError as e:
        with _eval_lock:
            _eval.update(running=False, error=str(e))
        return
    with _eval_lock:
        _eval.update(total=len(items), results=[], error=None,
                     provider=provider.name, model=provider.model,
                     started_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                               time.gmtime()))
    for item_id, prompt, expected in items:
        advisor = Advisor(WORLD, provider_from_env())  # fresh context per item
        t0 = time.time()
        try:
            answer = advisor.ask(prompt)
            error = None
        except Exception as e:  # keep the run alive

            answer, error = "", f"{type(e).__name__}: {e}"
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
               "found": total - len(missing),
               "missing": [str(m) for m in missing],
               "seconds": round(took, 1), "tool_calls": tool_calls,
               "prompt": prompt, "answer": answer, "error": error}
        with _eval_lock:
            _eval["results"].append(rec)
        time.sleep(1)
    with _eval_lock:
        _eval["running"] = False
        os.makedirs(OUT_DIR, exist_ok=True)
        with open(os.path.join(OUT_DIR, "results.json"), "w") as fh:
            json.dump({"provider": _eval["provider"], "model": _eval["model"],
                       "results": _eval["results"]}, fh, indent=1)


def _load_saved_eval():
    path = os.path.join(OUT_DIR, "results.json")
    if not os.path.isfile(path):
        return None
    try:
        with open(path) as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


class Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        sys.stderr.write(f"[{self.log_date_time_string()}] {fmt % args}\n")

    # ---- plumbing -------------------------------------------------------

    def _send_json(self, obj, code=200):
        body = json.dumps(obj, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        return json.loads(self.rfile.read(length) or b"{}")

    def _stream_event(self, obj):
        self.wfile.write((json.dumps(obj, default=str) + "\n").encode())
        self.wfile.flush()

    # ---- routes ---------------------------------------------------------

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            return self._serve_index()
        if path == "/api/meta":
            questions, scenarios = _load_dataset()
            meta = _provider_meta()
            meta.update(snapshot_now="2026-09-14T18:00:00Z",
                        questions=len(questions), scenarios=len(scenarios),
                        scenario_instruction=SCENARIO_INSTRUCTION,
                        manual_ids=sorted(MANUAL),
                        tools=[{"name": s["name"],
                                "description": s["description"]}
                               for s in T.tool_schemas()])
            return self._send_json(meta)
        if path == "/api/dataset":
            questions, scenarios = _load_dataset()
            return self._send_json({"questions": questions,
                                    "scenarios": scenarios})
        if path == "/api/eval/status":
            with _eval_lock:
                state = dict(_eval)
            if not state["running"] and not state["results"]:
                saved = _load_saved_eval()
                if saved:
                    state.update(results=saved.get("results", []),
                                 provider=saved.get("provider"),
                                 model=saved.get("model"),
                                 total=len(saved.get("results", [])),
                                 saved=True)
            return self._send_json(state)
        self.send_error(404)

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        try:
            body = self._read_json()
        except json.JSONDecodeError:
            return self._send_json({"error": "bad JSON body"}, 400)
        if path == "/api/chat":
            return self._chat(body)
        if path == "/api/chat/reset":
            with _sessions_lock:
                _sessions.pop(body.get("session_id"), None)
            return self._send_json({"ok": True})
        if path == "/api/eval/start":
            with _eval_lock:
                if _eval["running"]:
                    return self._send_json(
                        {"error": "an eval run is already in progress"}, 409)
                _eval.update(running=True, results=[], total=0, error=None)
            ids = body.get("ids") or []
            threading.Thread(target=_run_eval, args=(ids,),
                             daemon=True).start()
            return self._send_json({"ok": True})
        self.send_error(404)

    # ---- handlers -------------------------------------------------------

    def _serve_index(self):
        try:
            with open(os.path.join(WEB_DIR, "index.html"), "rb") as fh:
                body = fh.read()
        except OSError:
            return self.send_error(404, "web/index.html missing")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _chat(self, body):
        message = (body.get("message") or "").strip()
        sid = body.get("session_id") or str(uuid.uuid4())
        if not message:
            return self._send_json({"error": "empty message"}, 400)

        with _sessions_lock:
            sess = _sessions.get(sid)
            if sess is None:
                try:
                    provider = provider_from_env()
                except ConfigError as e:
                    return self._send_json({"error": str(e)}, 503)
                sess = {"advisor": Advisor(WORLD, provider,
                                           max_steps=int(os.environ.get(
                                               "LLM_MAX_STEPS", "16"))),
                        "lock": threading.Lock()}
                _sessions[sid] = sess

        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        advisor = sess["advisor"]

        def on_event(kind, payload):
            self._stream_event({"type": kind, **payload})

        with sess["lock"]:
            advisor.on_event = on_event
            start = len(advisor.history)
            try:
                answer = advisor.ask(message)
            except ProviderError as e:
                return self._stream_event({"type": "error", "error": str(e)})
            except Exception as e:
                traceback.print_exc()
                return self._stream_event(
                    {"type": "error", "error": f"{type(e).__name__}: {e}"})
            finally:
                advisor.on_event = lambda kind, payload: None
            trace = []
            for m in advisor.history[start:]:
                if m["role"] == "tool_results":
                    trace.extend({"name": r["name"], "result": r["content"]}
                                 for r in m["results"])
            self._stream_event({"type": "answer", "session_id": sid,
                                "answer": answer, "trace": trace})


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    meta = _provider_meta()
    if meta["provider"]:
        print(f"[AI layer: provider={meta['provider']} model={meta['model']}]")
    else:
        print(f"[AI layer unavailable: {meta['error']}]")
        print("  (questions/scenarios still browsable; chat and eval need a key)")
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Crew Ops Advisor UI -> http://127.0.0.1:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
