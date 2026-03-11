"""Extensible sub-agent role registry for the delegation engine.

Roles define specialist personas that review candidates from different
angles.  Built-in roles ship with the package; users and plugins can
register additional roles at runtime.

Usage::

    from llm_service.agent.core.roles import RoleRegistry

    registry = RoleRegistry()         # pre-loaded with built-in roles
    registry.register(
        name="performance",
        system_prompt="You are a performance specialist. ...",
        description="Evaluate latency and throughput impact.",
        tags=["nfr"],
    )

    role = registry.get("performance")
    all_roles = registry.list_roles()
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)


# ── Role dataclass ───────────────────────────────────────────────────
@dataclass
class Role:
    """A specialist sub-agent role."""

    name: str
    system_prompt: str
    description: str = ""
    tags: List[str] = field(default_factory=list)
    builtin: bool = False  # True for shipped roles

    def __repr__(self) -> str:
        tag_str = f" tags={self.tags}" if self.tags else ""
        return f"<Role {self.name!r}{tag_str}>"


# ── Built-in role definitions ────────────────────────────────────────
_BUILTIN_ROLES: List[Role] = [
    Role(
        name="relevance",
        system_prompt=(
            "You are a relevance specialist. Rank candidate documentation pages "
            "by direct task fit. Prioritize practical fixability and task alignment."
        ),
        description="Rank candidates by task relevance.",
        tags=["review"],
        builtin=True,
    ),
    Role(
        name="freshness",
        system_prompt=(
            "You are a freshness specialist. Evaluate if candidate pages appear "
            "current and safe to trust. Use last-updated, version clues, and "
            "deprecation signals."
        ),
        description="Evaluate recency and trustworthiness of candidates.",
        tags=["review"],
        builtin=True,
    ),
    Role(
        name="applicability",
        system_prompt=(
            "You are an implementation specialist. Evaluate whether each candidate "
            "solution can be applied quickly with low risk and clear steps."
        ),
        description="Assess ease and risk of applying candidate solutions.",
        tags=["review"],
        builtin=True,
    ),
    Role(
        name="security",
        system_prompt=(
            "You are a security specialist. Review candidate solutions for "
            "security pitfalls and safer alternatives."
        ),
        description="Identify security risks in candidate solutions.",
        tags=["review"],
        builtin=True,
    ),
    Role(
        name="extraction",
        system_prompt=(
            "You are a content extraction specialist. Given raw documentation, "
            "extract the key facts, actionable steps, configuration snippets, "
            "and owner/contact information. Output a concise structured summary. "
            "Omit boilerplate, navigation chrome, and unrelated sections."
        ),
        description="Extract key facts from raw pages (map-reduce helper).",
        tags=["extraction", "map-reduce"],
        builtin=True,
    ),
    Role(
        name="synthesizer",
        system_prompt=(
            "You are a lead engineer synthesizing specialist reviews. "
            "Return: best page(s), final recommended solution, confidence, "
            "risks, and owner/contact list."
        ),
        description="Synthesize specialist reviews into a recommendation.",
        tags=["synthesis"],
        builtin=True,
    ),
]


# ── RoleRegistry ─────────────────────────────────────────────────────
class RoleRegistry:
    """Extensible registry of specialist sub-agent roles.

    Pre-loaded with built-in roles.  Additional roles can be registered
    (and unregistered) at runtime.
    """

    def __init__(self, *, load_builtins: bool = True) -> None:
        self._roles: Dict[str, Role] = {}
        if load_builtins:
            for role in _BUILTIN_ROLES:
                self._roles[role.name] = role

    # ── mutators ─────────────────────────────────────────────────────

    def register(
        self,
        name: str,
        system_prompt: str,
        description: str = "",
        tags: Optional[List[str]] = None,
        *,
        overwrite: bool = False,
    ) -> Role:
        """Register a new role.

        Args:
            name: Unique role identifier (lowercase, no spaces recommended).
            system_prompt: System prompt text for the specialist.
            description: Human-readable one-liner.
            tags: Optional classification tags.
            overwrite: If True, allow overwriting an existing role.

        Returns:
            The registered Role.

        Raises:
            ValueError: If *name* already exists and *overwrite* is False.
        """
        name = name.strip().lower()
        if not name:
            raise ValueError("Role name must not be empty")

        if name in self._roles and not overwrite:
            raise ValueError(
                f"Role '{name}' already registered. Pass overwrite=True to replace."
            )

        role = Role(
            name=name,
            system_prompt=system_prompt,
            description=description,
            tags=tags or [],
            builtin=False,
        )
        self._roles[name] = role
        logger.debug("Registered role: %s", name)
        return role

    def unregister(self, name: str) -> bool:
        """Remove a role. Returns True if it existed."""
        name = name.strip().lower()
        if name in self._roles:
            del self._roles[name]
            logger.debug("Unregistered role: %s", name)
            return True
        return False

    # ── queries ──────────────────────────────────────────────────────

    def get(self, name: str) -> Optional[Role]:
        """Look up a role by name. Returns None if not found."""
        return self._roles.get(name.strip().lower())

    def list_roles(self, *, tag: Optional[str] = None) -> List[Role]:
        """List roles, optionally filtered by tag."""
        roles = list(self._roles.values())
        if tag:
            tag_lower = tag.lower()
            roles = [r for r in roles if tag_lower in (t.lower() for t in r.tags)]
        return sorted(roles, key=lambda r: r.name)

    def list_names(self, *, tag: Optional[str] = None) -> List[str]:
        """Convenience: list role names only."""
        return [r.name for r in self.list_roles(tag=tag)]

    def has(self, name: str) -> bool:
        """Check if a role exists."""
        return name.strip().lower() in self._roles

    def __len__(self) -> int:
        return len(self._roles)

    def __contains__(self, name: str) -> bool:
        return self.has(name)

    def __repr__(self) -> str:
        return f"<RoleRegistry roles={list(self._roles.keys())}>"
