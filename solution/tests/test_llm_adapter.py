"""The AI layer without any network: env-file config, provider selection,
message translation for both wire formats, and the advisor loop + grounding
gate driven by a fake provider."""

import json

import pytest

from crew_ops.llm import config as C
from crew_ops.llm import providers as P
from crew_ops.llm.agent import SYSTEM_PROMPT, Advisor, grounding_violations
from crew_ops.llm.providers import ToolCall, Turn


# ------------------------------ config ------------------------------

def _isolate_env(monkeypatch, tmp_path):
    """Point the .env search at an empty file and clear the relevant vars."""
    empty = tmp_path / "empty.env"
    empty.write_text("")
    monkeypatch.setenv("CREW_OPS_ENV", str(empty))
    for var in ("LLM_PROVIDER", "ANTHROPIC_API_KEY", "SARVAM_API_KEY",
                "CLAUDE_MODEL", "SARVAM_MODEL", "LLM_MAX_TOKENS",
                "CLAUDE_FALLBACKS", "SARVAM_REASONING_EFFORT"):
        monkeypatch.delenv(var, raising=False)


def test_load_env_parses_and_never_overrides(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(
        "# comment\n"
        "LLM_PROVIDER=sarvam   # inline comment\n"
        "SARVAM_API_KEY='sk_secret'\n"
        "EMPTYLINE_BELOW=1\n"
        "\n"
        'QUOTED="hello world"\n')
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("SARVAM_API_KEY", raising=False)
    monkeypatch.setenv("QUOTED", "already-set")
    loaded = C.load_env(path=str(env))
    assert loaded["LLM_PROVIDER"] == "sarvam"
    assert loaded["SARVAM_API_KEY"] == "sk_secret"
    assert "QUOTED" not in loaded  # real env wins
    import os
    assert os.environ["QUOTED"] == "already-set"


def test_provider_selection_sarvam(tmp_path, monkeypatch):
    _isolate_env(monkeypatch, tmp_path)
    monkeypatch.setenv("LLM_PROVIDER", "sarvam")
    monkeypatch.setenv("SARVAM_API_KEY", "sk_x")
    prov = C.provider_from_env()
    assert isinstance(prov, P.SarvamProvider)
    assert prov.model == P.SARVAM_DEFAULT_MODEL


def test_provider_selection_claude_with_overrides(tmp_path, monkeypatch):
    _isolate_env(monkeypatch, tmp_path)
    monkeypatch.setenv("LLM_PROVIDER", "claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-x")
    monkeypatch.setenv("CLAUDE_MODEL", "claude-sonnet-5")
    monkeypatch.setenv("LLM_MAX_TOKENS", "9000")
    prov = C.provider_from_env()
    assert isinstance(prov, P.ClaudeProvider)
    assert prov.model == "claude-sonnet-5"
    assert prov.max_tokens == 9000


def test_provider_selection_errors(tmp_path, monkeypatch):
    _isolate_env(monkeypatch, tmp_path)
    monkeypatch.setenv("LLM_PROVIDER", "claude")
    with pytest.raises(C.ConfigError, match="ANTHROPIC_API_KEY"):
        C.provider_from_env()
    monkeypatch.setenv("LLM_PROVIDER", "hal9000")
    with pytest.raises(C.ConfigError, match="hal9000"):
        C.provider_from_env()


# ------------------------- message translation -------------------------

NEUTRAL = [
    {"role": "user", "text": "Who can cover P-2291?"},
    {"role": "assistant", "text": "Checking.",
     "tool_calls": [{"id": "t1", "name": "recommend_cover",
                     "args": {"pairing_id": "P-2291", "role": "Captain"}}]},
    {"role": "tool_results",
     "results": [{"id": "t1", "name": "recommend_cover",
                  "content": {"ok": True, "result": {"options": []}}}]},
]


def test_to_claude_messages():
    msgs = P.to_claude_messages(NEUTRAL)
    assert msgs[0] == {"role": "user", "content": "Who can cover P-2291?"}
    blocks = msgs[1]["content"]
    assert blocks[0] == {"type": "text", "text": "Checking."}
    assert blocks[1]["type"] == "tool_use" and blocks[1]["id"] == "t1"
    assert blocks[1]["input"] == {"pairing_id": "P-2291", "role": "Captain"}
    result = msgs[2]["content"][0]
    assert result["type"] == "tool_result" and result["tool_use_id"] == "t1"
    assert json.loads(result["content"])["ok"] is True


def test_to_claude_messages_echoes_own_raw_content():
    sentinel = [{"type": "text", "text": "verbatim"}]
    msgs = P.to_claude_messages(
        [{"role": "assistant", "text": "x", "provider": "claude", "raw": sentinel}])
    assert msgs[0]["content"] is sentinel
    # a turn from the other provider is reconstructed, not echoed
    msgs = P.to_claude_messages(
        [{"role": "assistant", "text": "x", "provider": "sarvam", "raw": {"a": 1}}])
    assert msgs[0]["content"] == [{"type": "text", "text": "x"}]


def test_to_openai_messages():
    msgs = P.to_openai_messages("SYS", NEUTRAL)
    assert msgs[0] == {"role": "system", "content": "SYS"}
    assert msgs[1] == {"role": "user", "content": "Who can cover P-2291?"}
    call = msgs[2]["tool_calls"][0]
    assert call["type"] == "function" and call["id"] == "t1"
    assert json.loads(call["function"]["arguments"])["pairing_id"] == "P-2291"
    assert msgs[3]["role"] == "tool" and msgs[3]["tool_call_id"] == "t1"


def test_parse_sarvam_response():
    turn = P.parse_sarvam_response({
        "choices": [{"finish_reason": "tool_calls", "message": {
            "role": "assistant", "content": None,
            "tool_calls": [{"id": "abc", "type": "function", "function": {
                "name": "lookup_crew",
                "arguments": '{"crew_id": "C-1042"}'}}]}}]})
    assert turn.tool_calls[0].name == "lookup_crew"
    assert turn.tool_calls[0].args == {"crew_id": "C-1042"}
    assert turn.stop_reason == "tool_calls"

    final = P.parse_sarvam_response(
        {"choices": [{"finish_reason": "stop",
                      "message": {"role": "assistant", "content": "Done."}}]})
    assert final.text == "Done." and not final.tool_calls


def test_clean_tool_schemas_strips_property_level_required():
    from crew_ops.tools import tool_schemas
    for schema in P.clean_tool_schemas(tool_schemas()):
        for prop in schema["input_schema"]["properties"].values():
            assert "required" not in prop
    # object-level required list survives
    clock = next(s for s in P.clean_tool_schemas(tool_schemas())
                 if s["name"] == "get_duty_clock")
    assert clock["input_schema"]["required"] == ["crew_id"]


# ------------------------------ advisor loop ------------------------------

class FakeProvider(P.Provider):
    name = "fake"
    model = "fake-1"

    def __init__(self, turns):
        self.turns = list(turns)
        self.calls = []

    def complete(self, system, messages, tool_schemas):
        assert system == SYSTEM_PROMPT
        self.calls.append([m["role"] for m in messages])
        return self.turns.pop(0)


def test_advisor_runs_tools_then_answers(world):
    fake = FakeProvider([
        Turn(text="", tool_calls=[ToolCall("t1", "lookup_crew",
                                           {"crew_id": "C-1042"})]),
        Turn(text="C-1042 is a Captain based at BLR."),
    ])
    events = []
    advisor = Advisor(world, fake, on_event=lambda k, p: events.append((k, p["name"])))
    answer = advisor.ask("Who is C-1042?")
    assert "C-1042" in answer
    assert "[groundedness check]" not in answer
    assert events == [("tool_call", "lookup_crew"), ("tool_result", "lookup_crew")]
    roles = [m["role"] for m in advisor.history]
    assert roles == ["user", "assistant", "tool_results", "assistant"]
    assert advisor.history[2]["results"][0]["content"]["ok"] is True


def test_advisor_flags_ungrounded_ids(world):
    # An ungrounded id earns one corrective push-back; if the model insists,
    # the deterministic warning is appended.
    fake = FakeProvider([Turn(text="Assign C-9999 to P-2291."),
                         Turn(text="Assign C-9999 to P-2291.")])
    advisor = Advisor(world, fake)
    answer = advisor.ask("Who should cover P-2291?")  # P-2291 comes from the user
    assert "[groundedness check]" in answer and "C-9999" in answer
    assert "P-2291" not in answer.split("[groundedness check]")[1]
    assert any(m["role"] == "user" and "appear in no tool result" in m["text"]
               for m in advisor.history)


def test_advisor_correction_round_can_fix_ungrounded_ids(world):
    fake = FakeProvider([Turn(text="Assign C-9999 to P-2291."),
                         Turn(text="I cannot verify a legal cover from the data.")])
    advisor = Advisor(world, fake)
    answer = advisor.ask("Who should cover P-2291?")
    assert "[groundedness check]" not in answer and "C-9999" not in answer


def test_advisor_continues_truncated_answers(world):
    fake = FakeProvider([
        Turn(text="The ranked options are: first,", stop_reason="max_tokens"),
        Turn(text=" second and third."),
    ])
    advisor = Advisor(world, fake)
    answer = advisor.ask("Rank the options")
    assert answer == "The ranked options are: first, second and third."
    assert any(m["role"] == "user" and "cut off" in m["text"]
               for m in advisor.history)


def test_advisor_relays_tool_refusal(world):
    fake = FakeProvider([
        Turn(text="", tool_calls=[ToolCall("t1", "no_such_tool", {})]),
        Turn(text="That tool does not exist, so I cannot answer."),
    ])
    advisor = Advisor(world, fake)
    advisor.ask("Do something odd")
    refusal = advisor.history[2]["results"][0]["content"]
    assert refusal["ok"] is False and "unknown tool" in refusal["error"]


def test_advisor_retries_text_leaked_tool_calls(world):
    fake = FakeProvider([
        Turn(text="<tool_call>lookup_crew ...</tool_call>"),
        Turn(text="", tool_calls=[ToolCall("t1", "lookup_crew",
                                           {"crew_id": "C-1042"})]),
        Turn(text="C-1042 is a Captain."),
    ])
    advisor = Advisor(world, fake)
    answer = advisor.ask("Who is C-1042?")
    assert "<tool_call" not in answer and "C-1042" in answer
    # the corrective nudge landed in the history as a user turn
    assert any(m["role"] == "user" and "NOT executed" in m["text"]
               for m in advisor.history)


def test_advisor_stops_at_step_budget(world):
    fake = FakeProvider([Turn(text="", tool_calls=[ToolCall("t1", "lookup_crew",
                                                            {"crew_id": "C-1042"})])
                         for _ in range(3)])
    advisor = Advisor(world, fake, max_steps=3)
    answer = advisor.ask("loop forever")
    assert "budget" in answer


def test_grounding_violations():
    evidence = '{"crew_id": "C-1042", "flight": "DX589"}'
    assert grounding_violations("Use C-1042 on DX589", evidence) == []
    assert grounding_violations("Use C-2087 on DX589 (VT-DXE)", evidence) == \
        ["C-2087", "VT-DXE"]
