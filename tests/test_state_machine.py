"""Unit tests for the authoritative state-machine rule table."""

from __future__ import annotations

from app.domain.state_machine import (
    CANCELLABLE_FROM,
    CANCELLATION_RULE,
    TERMINAL_STATES,
    TRANSITION_RULES,
    AllowedActorCategory,
    TransitionRule,
)
from app.enums import TicketStatus


def test_transition_rules_match_followup_contract() -> None:
    expected = {
        (None, TicketStatus.TODO): TransitionRule(
            AllowedActorCategory.PM,
            reason_required=False,
            pm_override_required=False,
        ),
        (TicketStatus.TODO, TicketStatus.IN_PROGRESS): TransitionRule(
            AllowedActorCategory.OWNER,
            reason_required=False,
            pm_override_required=False,
        ),
        (TicketStatus.TODO, TicketStatus.BLOCKED): TransitionRule(
            AllowedActorCategory.OWNER,
            reason_required=True,
            pm_override_required=False,
        ),
        (TicketStatus.IN_PROGRESS, TicketStatus.BLOCKED): TransitionRule(
            AllowedActorCategory.OWNER,
            reason_required=True,
            pm_override_required=False,
        ),
        (TicketStatus.BLOCKED, TicketStatus.IN_PROGRESS): TransitionRule(
            AllowedActorCategory.OWNER,
            reason_required=False,
            pm_override_required=False,
        ),
        (TicketStatus.IN_PROGRESS, TicketStatus.IN_QA): TransitionRule(
            AllowedActorCategory.OWNER,
            reason_required=False,
            pm_override_required=False,
        ),
        (TicketStatus.IN_QA, TicketStatus.DONE): TransitionRule(
            AllowedActorCategory.ROLE_QA,
            reason_required=False,
            pm_override_required=False,
        ),
        (TicketStatus.IN_QA, TicketStatus.QA_FAILED): TransitionRule(
            AllowedActorCategory.ROLE_QA,
            reason_required=True,
            pm_override_required=False,
        ),
        (TicketStatus.QA_FAILED, TicketStatus.TODO): TransitionRule(
            AllowedActorCategory.OWNER,
            reason_required=False,
            pm_override_required=False,
        ),
    }

    assert expected == TRANSITION_RULES


def test_cancellation_rule_matches_followup_contract() -> None:
    assert TransitionRule(
        AllowedActorCategory.PM,
        reason_required=True,
        pm_override_required=True,
    ) == CANCELLATION_RULE
    assert {
        TicketStatus.TODO,
        TicketStatus.IN_PROGRESS,
        TicketStatus.BLOCKED,
        TicketStatus.IN_QA,
        TicketStatus.QA_FAILED,
    } == CANCELLABLE_FROM


def test_terminal_states_are_terminal_by_contract() -> None:
    assert {TicketStatus.DONE, TicketStatus.CANCELLED} == TERMINAL_STATES
    assert all(key[0] not in TERMINAL_STATES for key in TRANSITION_RULES)
    assert CANCELLABLE_FROM.isdisjoint(TERMINAL_STATES)
