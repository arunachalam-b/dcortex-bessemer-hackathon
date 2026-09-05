"""Crew Ops Advisor — deterministic engine.

The LLM never computes a number; this package computes every number.
See solution/ARCHITECTURE.md for the design and `tools.py` for the
LLM-facing boundary (typed tools, JSON in / JSON out, trace attached).
"""

from .world import World, load_world, find_data_dir  # noqa: F401
