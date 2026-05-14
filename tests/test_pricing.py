"""Unit tests for derive-on-read runtime cost computation."""

from __future__ import annotations

from app.pricing import compute_cost


def test_compute_cost_known_model() -> None:
    assert compute_cost("claude-sonnet-4-6", 1_000_000, 2_000_000) == 33.0


def test_compute_cost_unknown_model_returns_none() -> None:
    assert compute_cost("unknown-model", 1_000, 1_000) is None


def test_compute_cost_missing_tokens_returns_none() -> None:
    assert compute_cost("claude-sonnet-4-6", None, 1_000) is None
    assert compute_cost("claude-sonnet-4-6", 1_000, None) is None
