"""Tests for the extensible role registry."""

import pytest

from llm_service.agent.core.roles import Role, RoleRegistry


def test_builtins_loaded_by_default():
    reg = RoleRegistry()
    assert len(reg) >= 6
    assert "relevance" in reg
    assert "freshness" in reg
    assert "applicability" in reg
    assert "security" in reg
    assert "extraction" in reg
    assert "synthesizer" in reg


def test_register_custom_role():
    reg = RoleRegistry()
    role = reg.register(
        name="performance",
        system_prompt="You are a performance specialist...",
        description="Evaluate latency/throughput.",
        tags=["nfr"],
    )
    assert role.name == "performance"
    assert not role.builtin
    assert reg.has("performance")
    assert reg.get("performance") is role


def test_register_duplicate_raises():
    reg = RoleRegistry()
    with pytest.raises(ValueError, match="already registered"):
        reg.register(name="relevance", system_prompt="dup")


def test_register_overwrite():
    reg = RoleRegistry()
    old_prompt = reg.get("relevance").system_prompt
    reg.register(name="relevance", system_prompt="new prompt", overwrite=True)
    assert reg.get("relevance").system_prompt == "new prompt"
    assert reg.get("relevance").system_prompt != old_prompt


def test_unregister():
    reg = RoleRegistry()
    assert reg.unregister("relevance") is True
    assert "relevance" not in reg
    assert reg.unregister("nonexistent") is False


def test_list_roles_by_tag():
    reg = RoleRegistry()
    review_roles = reg.list_roles(tag="review")
    assert all("review" in r.tags for r in review_roles)
    assert len(review_roles) >= 4

    extraction_roles = reg.list_roles(tag="extraction")
    assert len(extraction_roles) >= 1
    assert extraction_roles[0].name == "extraction"


def test_list_names():
    reg = RoleRegistry()
    names = reg.list_names()
    assert isinstance(names, list)
    assert "relevance" in names


def test_empty_name_raises():
    reg = RoleRegistry()
    with pytest.raises(ValueError, match="must not be empty"):
        reg.register(name="", system_prompt="x")


def test_no_builtins_option():
    reg = RoleRegistry(load_builtins=False)
    assert len(reg) == 0
