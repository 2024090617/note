"""Tests for the context budget manager."""

from llm_service.agent.session.budget import (
    ContextBudgetManager,
    estimate_tokens,
    DEFAULT_CONTEXT_WINDOW,
    DEFAULT_RESPONSE_RESERVE,
)


def test_estimate_tokens_basic():
    assert estimate_tokens("") == 1  # minimum 1
    assert estimate_tokens("abcd") == 1  # 4 chars → 1 token
    assert estimate_tokens("a" * 400) == 100


def test_budget_defaults():
    mgr = ContextBudgetManager()
    assert mgr.context_window == DEFAULT_CONTEXT_WINDOW
    assert mgr.response_reserve == DEFAULT_RESPONSE_RESERVE
    assert mgr.available == DEFAULT_CONTEXT_WINDOW - DEFAULT_RESPONSE_RESERVE
    assert mgr.total_used == 0
    assert not mgr.is_over_budget()


def test_record_and_remaining():
    mgr = ContextBudgetManager(context_window=1000, response_reserve=200)
    # available = 800

    tokens = mgr.record("system_prompt", "x" * 400)
    assert tokens == 100
    assert mgr.remaining("system_prompt") == mgr.limit("system_prompt") - 100


def test_is_over_budget_triggers():
    mgr = ContextBudgetManager(context_window=200, response_reserve=100)
    # available = 100
    mgr.record("history", "x" * 500)  # 125 tokens > 100 available
    assert mgr.is_over_budget()


def test_reset_clears_usage():
    mgr = ContextBudgetManager(context_window=1000, response_reserve=100)
    mgr.record("system_prompt", "x" * 400)
    assert mgr.total_used > 0
    mgr.reset()
    assert mgr.total_used == 0


def test_snapshot_contains_total():
    mgr = ContextBudgetManager(context_window=1000, response_reserve=200)
    mgr.record("system_prompt", "hello world")
    snap = mgr.snapshot()
    assert "_total" in snap
    assert snap["_total"]["limit"] == 800
    assert snap["_total"]["used"] == mgr.total_used


def test_set_context_window_recomputes():
    mgr = ContextBudgetManager(context_window=1000, response_reserve=200)
    old_limit = mgr.limit("history")
    mgr.set_context_window(2000)
    new_limit = mgr.limit("history")
    assert new_limit > old_limit


def test_unknown_component_gets_unbounded_slot():
    mgr = ContextBudgetManager(context_window=1000, response_reserve=200)
    mgr.record("custom_block", "data")
    assert mgr.remaining("custom_block") >= 0
