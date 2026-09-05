"""Provider-agnostic advisor loop over the deterministic tool boundary.

Understand -> plan (tool calls) -> narrate, exactly as ARCHITECTURE.md §4:
the model never computes a number — every fact must come back through
`tools.dispatch` — and a deterministic groundedness gate flags any dataset
id in the final answer that no tool result (or the controller's own
question) contains.
"""

from __future__ import annotations

import json
import re
from typing import Callable, Optional

from .. import tools as T
from ..world import World
from .providers import Provider, Turn

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
- If no tool can answer (out of scope, missing data), say plainly that you cannot \
answer reliably from the data you have, and why. A tool response with ok=false is \
such an answer: relay the error, do not improvise.
- Be concise and operational: the decision first, then the key numbers, then caveats."""

_ID_PATTERNS = (re.compile(r"\bC-\d{3,5}\b"), re.compile(r"\bP-\d{3,5}\b"),
                re.compile(r"\bDX\d{2,4}\b"), re.compile(r"\bVT-[A-Z]{3}\b"))


def grounding_violations(answer: str, evidence: str) -> list:
    """Dataset ids referenced in the answer but absent from the evidence."""
    return sorted({tok for pat in _ID_PATTERNS for tok in pat.findall(answer)
                   if tok not in evidence})


class Advisor:
    """Multi-turn conversation loop: any Provider, one tool boundary."""

    def __init__(self, world: World, provider: Provider, max_steps: int = 16,
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
        for _ in range(self.max_steps):
            turn = self.provider.complete(SYSTEM_PROMPT, self.history,
                                          T.tool_schemas())
            self.history.append({
                "role": "assistant", "text": turn.text,
                "tool_calls": [{"id": c.id, "name": c.name, "args": c.args}
                               for c in turn.tool_calls],
                "raw": turn.raw, "provider": self.provider.name})
            if not turn.tool_calls:
                return self._finalize(turn.text)
            results = []
            for c in turn.tool_calls:
                self.on_event("tool_call", {"name": c.name, "args": c.args})
                resp = T.dispatch(self.world, c.name, c.args)
                self.on_event("tool_result",
                              {"name": c.name, "ok": resp.get("ok", False)})
                results.append({"id": c.id, "name": c.name, "content": resp})
                self._evidence.append(json.dumps(resp, default=str))
            self.history.append({"role": "tool_results", "results": results})
        return ("I hit the tool-call budget before converging on an answer; "
                "please narrow the question or ask it one step at a time.")

    def _finalize(self, text: str) -> str:
        text = (text or "").strip() or "(the model returned an empty answer)"
        missing = grounding_violations(text, "\n".join(self._evidence))
        if missing:
            text += ("\n\n[groundedness check] ids in this answer that appear in "
                     f"no tool result: {', '.join(missing)} — treat them as "
                     "unverified.")
        return text
