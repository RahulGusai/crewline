"""Deterministic identities and secrets for integration tests."""

from __future__ import annotations

PM_ACTOR = "human:00000000-0000-0000-0000-000000000001"
PM_EMAIL = "pm@crewline.local"
PM_PASSWORD = "test_pm_password"
AGENT_KEYS = {
    "be": "test_be_key",
    "fe": "test_fe_key",
    "architect": "test_architect_key",
    "qa": "test_qa_key",
}
DEFAULT_REPO = "acme/crewline"
RELATED_REPO = "acme/frontend"
OTHER_REPO = "acme/other"
