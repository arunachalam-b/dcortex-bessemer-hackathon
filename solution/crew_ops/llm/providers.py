"""LLM providers behind one interface.

Each provider translates between the advisor's neutral conversation format
and its own wire format, and returns a normalized `Turn`. The advisor loop
never sees provider-specific shapes, so swapping Claude <-> Sarvam is pure
configuration.

Neutral conversation entries:
    {"role": "user", "text": str}
    {"role": "assistant", "text": str, "tool_calls": [{"id","name","args"}],
     "raw": <provider-native content>, "provider": str}
    {"role": "tool_results", "results": [{"id", "name", "content": dict}]}

`raw` lets a provider echo its own assistant turns back verbatim (Claude
must replay thinking/tool_use blocks unchanged; Sarvam its message dict);
a turn produced by a different provider is reconstructed from the neutral
fields instead, so a conversation even survives a mid-session provider swap.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Optional

CLAUDE_DEFAULT_MODEL = "claude-opus-5"
SARVAM_DEFAULT_MODEL = "sarvam-105b"
SARVAM_URL = "https://api.sarvam.ai/v1/chat/completions"

_TRUNCATION_NOTE = "\n[answer truncated: hit the max_tokens limit]"


class ProviderError(Exception):
    """A provider failed in a way the caller should surface, not crash on."""


@dataclass
class ToolCall:
    id: str
    name: str
    args: dict


@dataclass
class Turn:
    text: str
    tool_calls: list = field(default_factory=list)
    raw: object = None
    stop_reason: str = ""


class Provider:
    name = "?"
    model = "?"
    # Rough serialized-history size (chars) the advisor keeps the conversation
    # under so the request fits the model's context window (~3-4 chars/token).
    context_char_budget = 600_000

    def complete(self, system: str, messages: list, tool_schemas: list) -> Turn:
        raise NotImplementedError


def clean_tool_schemas(tool_schemas: list) -> list:
    """Strip the engine's property-level `required` markers (the real JSON
    Schema `required` array is already at object level)."""
    cleaned = []
    for s in tool_schemas:
        props = {k: {pk: pv for pk, pv in v.items() if pk != "required"}
                 for k, v in s["input_schema"]["properties"].items()}
        cleaned.append({"name": s["name"], "description": s["description"],
                        "input_schema": {**s["input_schema"], "properties": props}})
    return cleaned


# ------------------------------ Claude ------------------------------

def to_claude_messages(messages: list) -> list:
    out = []
    for m in messages:
        role = m["role"]
        if role == "user":
            out.append({"role": "user", "content": m["text"]})
        elif role == "assistant":
            if m.get("provider") == "claude" and m.get("raw") is not None:
                out.append({"role": "assistant", "content": m["raw"]})
                continue
            blocks = []
            if m.get("text"):
                blocks.append({"type": "text", "text": m["text"]})
            for c in m.get("tool_calls") or []:
                blocks.append({"type": "tool_use", "id": c["id"],
                               "name": c["name"], "input": c["args"]})
            out.append({"role": "assistant",
                        "content": blocks or [{"type": "text", "text": "(no content)"}]})
        elif role == "tool_results":
            out.append({"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": r["id"],
                 "content": json.dumps(r["content"], default=str)}
                for r in m["results"]]})
    return out


class ClaudeProvider(Provider):
    """Anthropic Claude via the official `anthropic` SDK.

    Server-side refusal fallbacks are on by default per current API guidance
    for claude-opus-5; if the account/model rejects the parameter we retry
    once without and stay off for the session.
    """

    name = "claude"

    def __init__(self, api_key: str, model: str = CLAUDE_DEFAULT_MODEL,
                 max_tokens: int = 16000, fallbacks: bool = True):
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self.fallbacks = fallbacks
        self._client = None
        self._anthropic = None

    def _client_or_raise(self):
        if self._client is None:
            try:
                import anthropic
            except ImportError:
                raise ProviderError(
                    "the 'anthropic' package is required for LLM_PROVIDER=claude "
                    "(pip install anthropic)")
            self._anthropic = anthropic
            self._client = anthropic.Anthropic(api_key=self.api_key)
        return self._client

    def complete(self, system, messages, tool_schemas):
        client = self._client_or_raise()
        a = self._anthropic
        kwargs = dict(model=self.model, max_tokens=self.max_tokens,
                      system=system, messages=to_claude_messages(messages),
                      tools=clean_tool_schemas(tool_schemas))
        try:
            if self.fallbacks:
                try:
                    resp = client.beta.messages.create(
                        betas=["server-side-fallback-2026-07-01"],
                        fallbacks="default", **kwargs)
                except a.BadRequestError as e:
                    if "fallback" not in str(e).lower():
                        raise
                    self.fallbacks = False
                    resp = client.messages.create(**kwargs)
            else:
                resp = client.messages.create(**kwargs)
        except a.AuthenticationError:
            raise ProviderError("Anthropic rejected the API key (check ANTHROPIC_API_KEY)")
        except a.NotFoundError:
            raise ProviderError(f"unknown Claude model '{self.model}' (check CLAUDE_MODEL)")
        except a.RateLimitError:
            raise ProviderError("Claude rate limit hit — retry in a minute")
        except a.APIStatusError as e:
            raise ProviderError(f"Claude API error {e.status_code}: {e.message}")
        except a.APIConnectionError as e:
            cause = e.__cause__
            detail = f" (caused by {type(cause).__name__}: {cause})" if cause else ""
            raise ProviderError(f"cannot reach the Claude API: {e}{detail}")

        if resp.stop_reason == "refusal":
            return Turn(text="The model declined to answer this request.",
                        stop_reason="refusal")
        text = "".join(b.text for b in resp.content if b.type == "text")
        if resp.stop_reason == "max_tokens":
            text += _TRUNCATION_NOTE
        calls = [ToolCall(id=b.id, name=b.name, args=dict(b.input))
                 for b in resp.content if b.type == "tool_use"]
        return Turn(text=text, tool_calls=calls, raw=resp.content,
                    stop_reason=resp.stop_reason or "")


# ------------------------------ Sarvam ------------------------------

def to_openai_tools(tool_schemas: list) -> list:
    return [{"type": "function",
             "function": {"name": s["name"], "description": s["description"],
                          "parameters": s["input_schema"]}}
            for s in clean_tool_schemas(tool_schemas)]


def to_openai_messages(system: str, messages: list) -> list:
    out = [{"role": "system", "content": system}]
    for m in messages:
        role = m["role"]
        if role == "user":
            out.append({"role": "user", "content": m["text"]})
        elif role == "assistant":
            if m.get("provider") == "sarvam" and m.get("raw") is not None:
                out.append(m["raw"])
                continue
            msg = {"role": "assistant", "content": m.get("text") or None}
            if m.get("tool_calls"):
                msg["tool_calls"] = [
                    {"id": c["id"], "type": "function",
                     "function": {"name": c["name"],
                                  "arguments": json.dumps(c["args"])}}
                    for c in m["tool_calls"]]
            out.append(msg)
        elif role == "tool_results":
            out.extend({"role": "tool", "tool_call_id": r["id"],
                        "content": json.dumps(r["content"], default=str)}
                       for r in m["results"])
    return out


def parse_sarvam_response(data: dict) -> Turn:
    choice = (data.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    calls = []
    for tc in msg.get("tool_calls") or []:
        fn = tc.get("function") or {}
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except json.JSONDecodeError:
            args = {}
        calls.append(ToolCall(id=tc.get("id") or f"call_{len(calls)}",
                              name=fn.get("name", ""), args=args))
    text = msg.get("content") or ""
    if choice.get("finish_reason") == "length":
        text += _TRUNCATION_NOTE
    return Turn(text=text, tool_calls=calls, raw=msg,
                stop_reason=choice.get("finish_reason") or "")


class SarvamProvider(Provider):
    """Sarvam AI chat completions (OpenAI-style wire format), stdlib-only."""

    name = "sarvam"
    # 128k-token window minus output headroom; dense JSON runs ~2.5 chars
    # per token, so stay well below 128k * 2.5.
    context_char_budget = 220_000

    def __init__(self, api_key: str, model: str = SARVAM_DEFAULT_MODEL,
                 max_tokens: int = 8192,
                 reasoning_effort: Optional[str] = None, timeout: int = 120):
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self.reasoning_effort = reasoning_effort
        self.timeout = timeout

    def complete(self, system, messages, tool_schemas):
        body = {"model": self.model,
                "messages": to_openai_messages(system, messages),
                "max_tokens": self.max_tokens,
                "temperature": 0.2}
        if tool_schemas:
            body["tools"] = to_openai_tools(tool_schemas)
        if self.reasoning_effort:
            body["reasoning_effort"] = self.reasoning_effort
        return parse_sarvam_response(self._post(body))

    def _post(self, body: dict) -> dict:
        payload = json.dumps(body).encode()
        headers = {"Content-Type": "application/json",
                   "api-subscription-key": self.api_key,
                   "Authorization": f"Bearer {self.api_key}"}
        last: Optional[ProviderError] = None
        for attempt in range(3):
            req = urllib.request.Request(SARVAM_URL, data=payload,
                                         headers=headers, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    return json.loads(resp.read().decode())
            except urllib.error.HTTPError as e:
                try:
                    detail = e.read().decode()[:500]
                except Exception:
                    detail = ""
                if e.code == 429 or e.code >= 500:
                    last = ProviderError(f"Sarvam API {e.code}: {detail or e.reason}")
                    time.sleep(2 ** attempt)
                    continue
                if e.code in (401, 403):
                    raise ProviderError("Sarvam rejected the API key (check SARVAM_API_KEY)")
                raise ProviderError(f"Sarvam API {e.code}: {detail or e.reason}")
            except (urllib.error.URLError, TimeoutError) as e:
                last = ProviderError(f"cannot reach the Sarvam API: {e}")
                time.sleep(2 ** attempt)
        raise last if last else ProviderError("Sarvam request failed")
