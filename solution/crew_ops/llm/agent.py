"""Provider-agnostic advisor loop over the deterministic tool boundary.

Understand -> plan (tool calls) -> narrate, exactly as ARCHITECTURE.md §4:
the model never computes a number — every fact must come back through
`tools.dispatch` — and a deterministic groundedness gate flags any dataset
id in the final answer that no tool result (or the controller's own
question) contains.

The loop also owns the two failure modes a live provider actually has:
an answer cut off at the output-token limit is continued rather than
returned truncated, and a conversation that outgrows the model's context
window is compacted by eliding the oldest tool results (the model can
always re-call a tool it still needs).
"""

from __future__ import annotations

import json
import re
from typing import Callable, Optional

from .. import tools as T
from ..world import World
from .providers import Provider, ProviderError, Turn, _TRUNCATION_NOTE

SNAPSHOT_NOW = "2026-09-14T18:00:00Z"

SYSTEM_PROMPT = f"""You are the Crew Ops Advisor on an airline crew-control desk.
The operational snapshot "now" is {SNAPSHOT_NOW}. All times are UTC (Z); currency is INR.

Rules of engagement:
- Resolve names, phrases and relative dates ("tomorrow", "the VT-DXE captain") to \
canonical ids (C-xxxx crew, P-xxxx pairings, DXnnn flights) and ISO dates before \
calling tools; echo the resolution in your answer ("Assuming you mean ...") so the \
controller can catch a wrong guess. If genuinely ambiguous, ask instead of guessing.
- Call tools for EVERY fact. Never compute duty hours, legality, costs or times \
yourself, and never rely on memory of the dataset. State only values present in \
tool results, keeping ids, hours and INR amounts exactly as returned.
- Legality verdicts come only from check_assignment_legality / recommend_* results. \
When you rank or recommend, use the engine's ranking and cite its costs and the \
rules that excluded candidates.
- Cite rule ids in full, exactly as tools return them: RULE-FDP-01, RULE-CERT-06 — \
never shortened forms like FDP-01 or CERT-06.
- If no tool can answer (out of scope, missing data), say plainly that you cannot \
answer reliably from the data you have, and why. A tool response with ok=false is \
such an answer: relay the error, do not improvise.
- A tail number VT-XXX is an aircraft, never a crew member: resolve "the VT-DXE \
captain" by calling get_pairing with aircraft="VT-DXE" and the date, then read the \
pairing's crew. Disruptions on an aircraft's pairing are resolved the same way.
- Tools are invoked ONLY through the tool-calling interface. Never write tool-call \
markup or JSON in your answer text — it will not be executed.
- When you present options, list EVERY legal option the engine returned, each with \
its crew id, cost in INR and delay hours, in the engine's rank order — and list \
every excluded candidate id with the exact rule/reason that excluded it (group ids \
sharing a reason on one line).
- When a tool returns a per-flight or per-item table (per_flight_assessment, \
options, assignments), reproduce EVERY row with its exact numbers — flight id, \
minimum delay, FDP after delay vs the limit, cost — never aggregate rows away.
- For a joint plan, state each assignment's own cost_inr as well as the total.
- Be concise and operational: the decision first, then the key numbers, then \
caveats. Prefer compact lines and tables over prose so the complete answer fits \
in the output budget."""

# Deliberately wider than the dataset's exact shapes: a garbled flight number
# ("DL402" for DX402) or rule id ("ROLE-CERT-06") must be flagged too, so the
# correction round can push the model back to the verbatim tool value.
_ID_PATTERNS = (re.compile(r"\bC-\d{3,5}\b"), re.compile(r"\bP-\d{3,5}\b"),
                re.compile(r"\b[A-Z]{2}\d{2,4}\b"), re.compile(r"\bVT-[A-Z]{3}\b"),
                re.compile(r"\b[A-Z]{2,6}-[A-Z]{2,6}-\d{2}\b"))

MAX_CONTINUATIONS = 4

_CONTINUE_NUDGE = (
    "Your answer hit the output-token limit and was cut off. Continue EXACTLY "
    "where you stopped, without repeating anything you already wrote. If you "
    "had not produced any answer text yet, skip further deliberation and write "
    "the complete final answer now, as compactly as possible.")


def grounding_violations(answer: str, evidence: str) -> list:
    """Dataset ids referenced in the answer but absent from the evidence."""
    return sorted({tok for pat in _ID_PATTERNS for tok in pat.findall(answer)
                   if tok not in evidence})


def _is_context_overflow(err: Exception) -> bool:
    s = str(err).lower()
    return "context window" in s or "prompt_tokens" in s or "context length" in s


def _value_in(v, text: str) -> bool:
    if isinstance(v, float) and not v.is_integer():
        return f"{v:g}" in text
    if isinstance(v, (int, float)):
        return re.search(rf"\b{int(v)}\b", text) is not None
    return str(v) in text


def assessment_gaps(answer: str, tool_responses: list) -> list:
    """Facts a tool returned that the final answer silently dropped.

    A crew desk cannot act on a plan that omits affected flights, excluded
    candidates or the passengers at risk, so completeness is enforced
    deterministically, exactly like groundedness: every per-flight row
    (flight, minimum delay, FDP after delay), every excluded candidate
    (id plus the pairings named in its reason) and every per-day passenger
    figure must appear in the final answer."""
    text = answer.replace(",", "")
    gaps, seen = [], set()

    def require(label, need):
        key = (label, tuple(map(str, need)))
        if key in seen:
            return
        seen.add(key)
        missing = [str(v) for v in need if not _value_in(v, text)]
        if missing:
            gaps.append(f"{label}: {', '.join(missing)}")

    def blocks_of(result):
        # a joint plan nests one full cover result per event
        return [result] + [pe for pe in result.get("per_event") or []
                           if isinstance(pe, dict)]

    results = [r["result"] for r in tool_responses
               if isinstance(r, dict) and isinstance(r.get("result"), dict)]

    for result in results:
        for block in blocks_of(result):
            for row in block.get("per_flight_assessment") or []:
                fid = row.get("flight_id", "")
                need = [fid.split("-")[0]]  # DX402-2026-09-17 -> DX402
                for k in ("min_delay_hours", "crew_fdp_after_delay"):
                    if isinstance(row.get(k), (int, float)) and row[k]:
                        need.append(row[k])
                require(fid, need)
            for row in block.get("per_day") or []:
                if isinstance(row.get("passengers"), (int, float)):
                    require(f"passengers on {row.get('date')}",
                            [row["passengers"]])
            # verdict rule ids (an FDP breach or cert rule) must be cited
            for rid in re.findall(r"\bRULE-[A-Z]+-\d{2}\b",
                                  block.get("breach_detail") or ""):
                require(f"rule {rid}", [rid])
            if isinstance(block.get("rule"), str):
                require(f"rule {block['rule']}", [block["rule"]])

    # The full ranked options and exclusion lists are demanded only when the
    # question centred on ONE cover/joint decision; a sweep across many
    # pairings is legitimately summarised per pairing instead.
    decisions = {}  # one entry per distinct decision, latest result wins
    for r in results:
        if r.get("options") or r.get("per_event") or r.get("assignments"):
            key = ("joint",) if r.get("per_event") or r.get("assignments") \
                else (r.get("pairing_id"), r.get("role"))
            decisions[key] = r
    if len(decisions) == 1:
        result = next(iter(decisions.values()))
        if isinstance(result.get("total_cost_inr"), (int, float)) \
                and result["total_cost_inr"]:
            require("total cost", [result["total_cost_inr"]])
        for block in blocks_of(result):
            for kind in ("options", "assignments"):
                for row in block.get(kind) or []:
                    if not isinstance(row, dict):
                        continue
                    need = [v for v in (row.get("crew_id"),) if v]
                    for k in ("cost_inr", "delay_hours"):
                        if isinstance(row.get(k), (int, float)) and row[k]:
                            need.append(row[k])
                    if need:
                        require(f"{kind[:-1]} "
                                f"{row.get('crew_id') or row.get('action', '')}",
                                need)
            for row in block.get("excluded_candidates") or []:
                cid = row.get("crew_id")
                if not cid:
                    continue
                need = [cid] + re.findall(r"\bP-\d{3,5}\b",
                                          row.get("reason") or "")
                require(f"excluded {cid}", need)
    return gaps


class Advisor:
    """Multi-turn conversation loop: any Provider, one tool boundary."""

    def __init__(self, world: World, provider: Provider, max_steps: int = 24,
                 on_event: Optional[Callable[[str, dict], None]] = None):
        self.world = world
        self.provider = provider
        self.max_steps = max_steps
        self.on_event = on_event or (lambda kind, payload: None)
        self.history: list = []
        self._evidence: list = []  # persists across turns for the gate

    def ask(self, question: str) -> str:
        self.history.append({"role": "user", "text": question})
        self._evidence.append(question)  # ids the controller typed are fair to echo
        parts: list = []       # stitched text of turns cut off at max_tokens
        continuations = 0
        corrected = False      # one grounding-correction round per question
        completeness_rounds = 0  # up to two completeness push-backs per question
        ask_responses: list = []  # dispatch responses gathered for THIS question
        for _ in range(self.max_steps):
            turn = self._complete()
            self.history.append({
                "role": "assistant", "text": turn.text,
                "tool_calls": [{"id": c.id, "name": c.name, "args": c.args}
                               for c in turn.tool_calls],
                "raw": turn.raw, "provider": self.provider.name})
            if not turn.tool_calls:
                text = (turn.text or "").replace(_TRUNCATION_NOTE, "")
                if (turn.stop_reason in ("max_tokens", "length")
                        and continuations < MAX_CONTINUATIONS):
                    # Continue a cut-off answer instead of returning a stump.
                    continuations += 1
                    parts.append(text)
                    self.on_event("continue", {"reason": "output token limit"})
                    self.history.append({"role": "user", "text": _CONTINUE_NUDGE})
                    continue
                # A model that writes tool-call markup as text executed nothing:
                # push it back to the real interface instead of showing the leak.
                if "<tool_call" in text or '"tool_call"' in text:
                    self.on_event("retry", {"reason": "tool call written as text"})
                    self.history.append({
                        "role": "user",
                        "text": "Those tool calls were written as plain text and "
                                "were NOT executed. Invoke the tools through the "
                                "tool-calling interface, then answer."})
                    continue
                answer = "".join(parts + [text])
                gaps = assessment_gaps(answer, ask_responses)
                if gaps and completeness_rounds < 3:
                    completeness_rounds += 1
                    parts, continuations = [], 0
                    self.on_event("retry", {"reason": "incomplete assessment",
                                            "rows": gaps})
                    self.history.append({
                        "role": "user",
                        "text": "Your answer drops facts the tools returned. "
                                "Every one of these missing values must appear "
                                f"verbatim in the answer: {'; '.join(gaps)}. "
                                "Re-issue the complete final answer: every "
                                "per-flight row (flight, minimum delay hours, "
                                "crew FDP after delay vs the limit, action), "
                                "every excluded candidate quoting the rule and "
                                "the pairing ids from its reason exactly as "
                                "returned, and the per-day passenger figures. "
                                "Output the ENTIRE answer in one message — "
                                "never an excerpt or summary; if it gets cut "
                                "off you will be asked to continue."})
                    continue
                if gaps:
                    # correction rounds exhausted — never silently drop a
                    # tool-returned fact: append it deterministically, the
                    # same way the groundedness footnote works.
                    answer += ("\n\n[completeness check] tool-returned facts "
                               "not covered above: " + "; ".join(gaps))
                missing = grounding_violations(answer, "\n".join(self._evidence))
                if missing and not corrected:
                    # One deterministic push-back: fix or drop unverified ids.
                    corrected = True
                    parts, continuations = [], 0
                    self.on_event("retry", {"reason": "ungrounded ids",
                                            "ids": missing})
                    self.history.append({
                        "role": "user",
                        "text": "These ids in your answer appear in no tool "
                                f"result: {', '.join(missing)}. Re-issue the "
                                "complete final answer, citing every id exactly "
                                "as a tool returned it (call a tool again if "
                                "needed) or dropping the unverified ones."})
                    continue
                return self._finalize(answer)
            results = []
            for c in turn.tool_calls:
                self.on_event("tool_call", {"name": c.name, "args": c.args})
                resp = T.dispatch(self.world, c.name, c.args)
                self.on_event("tool_result",
                              {"name": c.name, "ok": resp.get("ok", False),
                               "error": resp.get("error")})
                results.append({"id": c.id, "name": c.name, "content": resp})
                ask_responses.append(resp)
                self._evidence.append(json.dumps(resp, default=str))
            self.history.append({"role": "tool_results", "results": results})
        return self._finalize(
            "".join(parts)
            or "I hit the tool-call budget before converging on an answer; "
               "please narrow the question or ask it one step at a time.")

    # ------------------------- provider plumbing -------------------------

    def _complete(self) -> Turn:
        """One provider call, with proactive and reactive context compaction."""
        self._fit_context(self.provider.context_char_budget)
        try:
            return self.provider.complete(SYSTEM_PROMPT, self.history,
                                          T.tool_schemas())
        except ProviderError as e:
            if not _is_context_overflow(e):
                raise
            self.on_event("compact", {"reason": str(e)[:200]})
            self._fit_context(self.provider.context_char_budget // 2,
                              keep_recent=1)
            return self.provider.complete(SYSTEM_PROMPT, self.history,
                                          T.tool_schemas())

    def _history_chars(self) -> int:
        return sum(len(json.dumps(m, default=str)) for m in self.history)

    def _fit_context(self, budget: int, keep_recent: int = 3) -> None:
        """Keep the serialized history under `budget` chars.

        Pass 1 elides whole results from the oldest tool-result messages,
        sparing the newest `keep_recent`. Pass 2 handles a burst of parallel
        calls whose results land in few (recent) messages: the biggest recent
        results are cut down to a head. Pass 3 drops replayable provider-raw
        payloads. The model is told what happened and can re-call any tool."""
        if self._history_chars() <= budget:
            return
        tool_msgs = [m for m in self.history if m["role"] == "tool_results"]
        for m in tool_msgs[:max(0, len(tool_msgs) - keep_recent)]:
            for r in m["results"]:
                c = r["content"]
                if isinstance(c, dict) and "elided" not in c:
                    r["content"] = {
                        "ok": c.get("ok"),
                        "elided": f"large {r['name']} result removed to fit "
                                  "the context window — call the tool again "
                                  "if you still need it"}
            if self._history_chars() <= budget:
                return
        recent = [r for m in tool_msgs[max(0, len(tool_msgs) - keep_recent):]
                  for r in m["results"]]
        sized = sorted(((len(json.dumps(r["content"], default=str)), r)
                        for r in recent), key=lambda x: -x[0])
        for size, r in sized:
            if size < 8000:
                break
            head = json.dumps(r["content"], default=str)[:6000]
            r["content"] = {
                "truncated_result": head,
                "note": f"result cut from {size} to 6000 chars to fit the "
                        "context window — re-call the tool with narrower "
                        "arguments if you need the rest"}
            if self._history_chars() <= budget:
                return
        for m in self.history[:-2]:  # raw provider blobs are replayable extras
            if m.get("raw") is not None:
                m["raw"] = None
            if self._history_chars() <= budget:
                return

    def _finalize(self, text: str) -> str:
        text = (text or "").strip() or "(the model returned an empty answer)"
        missing = grounding_violations(text, "\n".join(self._evidence))
        if missing:
            text += ("\n\n[groundedness check] ids in this answer that appear in "
                     f"no tool result: {', '.join(missing)} — treat them as "
                     "unverified.")
        return text
