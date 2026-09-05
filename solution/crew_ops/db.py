"""SQLite persistence: a mirror of the frozen dataset plus eval-run history.

The dataset does not change for the duration of the hackathon, so it is
seeded into the DB once (verbatim JSON per record) and every later load
reads from SQLite; callers fall back to the original JSON files whenever
anything here raises DBError.

Eval runs are appended (`eval_runs` + `eval_results`) so the full history
survives server restarts — not just the last run.

Default DB file: solution/crew_ops.db (override with CREW_OPS_DB).
"""

from __future__ import annotations

import json
import os
import sqlite3

_LIST_FILES = ("flights.json", "crew.json", "duty_clocks.json",
               "reserve_pool.json", "certifications.json",
               "risk_signals.json", "questions.json", "scenarios.json")
_DOC_FILES = ("rosters.json", "rules.json", "costs.json")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(
  key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS dataset_records(
  file TEXT NOT NULL, seq INTEGER NOT NULL, data TEXT NOT NULL,
  PRIMARY KEY(file, seq));
CREATE TABLE IF NOT EXISTS dataset_documents(
  file TEXT PRIMARY KEY, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS eval_runs(
  run_id INTEGER PRIMARY KEY AUTOINCREMENT,
  started_utc TEXT NOT NULL, finished_utc TEXT,
  provider TEXT, model TEXT, requested_ids TEXT, total INTEGER);
CREATE TABLE IF NOT EXISTS eval_results(
  run_id INTEGER NOT NULL, seq INTEGER NOT NULL,
  item_id TEXT, status TEXT, atoms INTEGER, found INTEGER, missing TEXT,
  seconds REAL, tool_calls INTEGER, prompt TEXT, answer TEXT, error TEXT,
  PRIMARY KEY(run_id, seq));
"""


class DBError(Exception):
    pass


def db_path() -> str:
    env = os.environ.get("CREW_OPS_DB")
    if env:
        return env
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "crew_ops.db")


def _connect() -> sqlite3.Connection:
    try:
        conn = sqlite3.connect(db_path(), timeout=10)
        conn.execute("PRAGMA busy_timeout=10000")
        return conn
    except sqlite3.Error as e:
        raise DBError(f"cannot open {db_path()}: {e}")


# ---------------------------------------------------------------- dataset

def ensure_seeded(data_dir: str) -> bool:
    """Create the schema and mirror the dataset files in once.

    Returns True if this call seeded the dataset. Refuses (raises DBError)
    if the DB was seeded from a different data_dir, so stale mirrors are
    never served for another dataset.
    """
    conn = _connect()
    try:
        conn.executescript(_SCHEMA)
        row = conn.execute("SELECT value FROM meta WHERE key='data_dir'"
                           ).fetchone()
        if row:
            if row[0] != os.path.abspath(data_dir):
                raise DBError(f"DB seeded from {row[0]}, not {data_dir}")
            return False
        for name in _LIST_FILES:
            path = os.path.join(data_dir, name)
            if not os.path.isfile(path):
                continue
            with open(path) as fh:
                items = json.load(fh)
            conn.executemany(
                "INSERT OR REPLACE INTO dataset_records VALUES(?,?,?)",
                [(name, i, json.dumps(x)) for i, x in enumerate(items)])
        for name in _DOC_FILES:
            path = os.path.join(data_dir, name)
            if not os.path.isfile(path):
                continue
            with open(path) as fh:
                conn.execute(
                    "INSERT OR REPLACE INTO dataset_documents VALUES(?,?)",
                    (name, json.dumps(json.load(fh))))
        conn.execute("INSERT INTO meta VALUES('data_dir',?)",
                     (os.path.abspath(data_dir),))
        conn.commit()
        return True
    except (sqlite3.Error, OSError, json.JSONDecodeError) as e:
        raise DBError(str(e))
    finally:
        conn.close()


def load_json(name: str):
    """Parsed content of one dataset file, read from SQLite."""
    conn = _connect()
    try:
        if name in _DOC_FILES:
            row = conn.execute(
                "SELECT data FROM dataset_documents WHERE file=?",
                (name,)).fetchone()
            if not row:
                raise DBError(f"{name} not in DB")
            return json.loads(row[0])
        rows = conn.execute(
            "SELECT data FROM dataset_records WHERE file=? ORDER BY seq",
            (name,)).fetchall()
        if not rows:
            raise DBError(f"{name} not in DB")
        return [json.loads(r[0]) for r in rows]
    except sqlite3.Error as e:
        raise DBError(str(e))
    finally:
        conn.close()


# ---------------------------------------------------------------- eval runs

def create_run(started_utc, provider, model, requested_ids, total) -> int:
    conn = _connect()
    try:
        cur = conn.execute(
            "INSERT INTO eval_runs(started_utc, provider, model,"
            " requested_ids, total) VALUES(?,?,?,?,?)",
            (started_utc, provider, model,
             json.dumps(sorted(requested_ids or [])), total))
        conn.commit()
        return cur.lastrowid
    except sqlite3.Error as e:
        raise DBError(str(e))
    finally:
        conn.close()


def add_result(run_id: int, seq: int, rec: dict) -> None:
    conn = _connect()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO eval_results VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (run_id, seq, rec["id"], rec["status"], rec["atoms"],
             rec["found"], json.dumps(rec["missing"]), rec["seconds"],
             rec["tool_calls"], rec["prompt"], rec["answer"], rec["error"]))
        conn.commit()
    except sqlite3.Error as e:
        raise DBError(str(e))
    finally:
        conn.close()


def finish_run(run_id: int, finished_utc: str) -> None:
    conn = _connect()
    try:
        conn.execute("UPDATE eval_runs SET finished_utc=? WHERE run_id=?",
                     (finished_utc, run_id))
        conn.commit()
    except sqlite3.Error as e:
        raise DBError(str(e))
    finally:
        conn.close()


def _results_of(conn, run_id: int) -> list:
    rows = conn.execute(
        "SELECT item_id, status, atoms, found, missing, seconds, tool_calls,"
        " prompt, answer, error FROM eval_results WHERE run_id=? ORDER BY seq",
        (run_id,)).fetchall()
    return [{"id": r[0], "status": r[1], "atoms": r[2], "found": r[3],
             "missing": json.loads(r[4] or "[]"), "seconds": r[5],
             "tool_calls": r[6], "prompt": r[7], "answer": r[8],
             "error": r[9]} for r in rows]


def list_runs() -> list:
    """All runs, newest first, with per-status counts (no transcripts)."""
    conn = _connect()
    try:
        runs = conn.execute(
            "SELECT run_id, started_utc, finished_utc, provider, model, total"
            " FROM eval_runs ORDER BY run_id DESC").fetchall()
        out = []
        for run_id, started, finished, provider, model, total in runs:
            counts = dict(conn.execute(
                "SELECT status, COUNT(*) FROM eval_results WHERE run_id=?"
                " GROUP BY status", (run_id,)).fetchall())
            done = sum(counts.values())
            out.append({"run_id": run_id, "started_utc": started,
                        "finished_utc": finished, "provider": provider,
                        "model": model, "total": total, "done": done,
                        "counts": counts})
        return out
    except sqlite3.Error as e:
        raise DBError(str(e))
    finally:
        conn.close()


def get_run(run_id: int):
    """One run with its full graded results, or None."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT run_id, started_utc, finished_utc, provider, model, total"
            " FROM eval_runs WHERE run_id=?", (run_id,)).fetchone()
        if not row:
            return None
        return {"run_id": row[0], "started_utc": row[1],
                "finished_utc": row[2], "provider": row[3], "model": row[4],
                "total": row[5], "results": _results_of(conn, row[0])}
    except sqlite3.Error as e:
        raise DBError(str(e))
    finally:
        conn.close()


def latest_run():
    """The most recent run (finished preferred), or None."""
    conn = _connect()
    try:
        row = (conn.execute(
                   "SELECT run_id FROM eval_runs WHERE finished_utc IS NOT NULL"
                   " ORDER BY run_id DESC LIMIT 1").fetchone()
               or conn.execute("SELECT run_id FROM eval_runs"
                               " ORDER BY run_id DESC LIMIT 1").fetchone())
    except sqlite3.Error as e:
        raise DBError(str(e))
    finally:
        conn.close()
    return get_run(row[0]) if row else None
