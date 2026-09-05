"""Environment-driven provider selection for the AI layer.

The provider is chosen entirely from the environment (optionally seeded
from a `.env` file next to the solution):

    LLM_PROVIDER=claude   -> ClaudeProvider   (needs ANTHROPIC_API_KEY)
    LLM_PROVIDER=sarvam   -> SarvamProvider   (needs SARVAM_API_KEY)

See `.env.example` for every knob.
"""

from __future__ import annotations

import os
from typing import Optional


class ConfigError(Exception):
    """The AI layer cannot be configured from the environment."""


def _solution_dir() -> str:
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load_env(path: Optional[str] = None) -> dict:
    """Load KEY=VALUE pairs from the first `.env` found into os.environ.

    Real environment variables always win — the file only fills gaps, so
    `LLM_PROVIDER=sarvam python3 cli.py chat` overrides the file for one run.
    Search order: explicit path, $CREW_OPS_ENV, solution/.env, ./.env.
    """
    candidates = [path, os.environ.get("CREW_OPS_ENV"),
                  os.path.join(_solution_dir(), ".env"),
                  os.path.join(os.getcwd(), ".env")]
    loaded = {}
    for cand in candidates:
        if not cand or not os.path.isfile(cand):
            continue
        with open(cand) as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                if " #" in value:  # allow inline comments
                    value = value.split(" #", 1)[0]
                value = value.strip().strip("'\"")
                if key and key not in os.environ:
                    os.environ[key] = value
                    loaded[key] = value
        break
    return loaded


def provider_from_env():
    """Build the configured provider, or raise ConfigError with the fix."""
    from . import providers

    load_env()
    name = os.environ.get("LLM_PROVIDER", "claude").strip().lower()
    max_tokens = os.environ.get("LLM_MAX_TOKENS")
    max_tokens = int(max_tokens) if max_tokens else None

    if name == "claude":
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise ConfigError(
                "LLM_PROVIDER=claude but ANTHROPIC_API_KEY is not set — put it "
                "in solution/.env (see .env.example)")
        return providers.ClaudeProvider(
            api_key=key,
            model=os.environ.get("CLAUDE_MODEL", providers.CLAUDE_DEFAULT_MODEL),
            max_tokens=max_tokens or 16000,
            fallbacks=os.environ.get("CLAUDE_FALLBACKS", "1").lower()
            not in ("0", "false", "no"))

    if name == "sarvam":
        key = os.environ.get("SARVAM_API_KEY")
        if not key:
            raise ConfigError(
                "LLM_PROVIDER=sarvam but SARVAM_API_KEY is not set — put it "
                "in solution/.env (see .env.example)")
        return providers.SarvamProvider(
            api_key=key,
            model=os.environ.get("SARVAM_MODEL", providers.SARVAM_DEFAULT_MODEL),
            max_tokens=max_tokens or 4096,
            reasoning_effort=os.environ.get("SARVAM_REASONING_EFFORT") or None)

    raise ConfigError(f"unknown LLM_PROVIDER '{name}' (expected 'claude' or 'sarvam')")
