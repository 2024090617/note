"""Delegation engine for specialist sub-agent review."""

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ..copilot_client import ChatMessage, CopilotBridgeClient
from .roles import Role, RoleRegistry


@dataclass
class SpecialistReview:
    """Single specialist review output."""

    role: str
    content: str


class DelegationEngine:
    """Runs specialist reviews and synthesizes a recommendation.

    Uses a :class:`RoleRegistry` for role look-ups instead of a hardcoded
    dict.  The registry can be shared across the application so roles
    registered at runtime are immediately available.
    """

    # Keep a class-level alias for backwards compat (tests, etc.)
    ROLE_PROMPTS: Dict[str, str] = {}  # populated from registry on access

    def __init__(
        self,
        client: CopilotBridgeClient,
        model: str,
        max_specialists: int = 3,
        max_collab_rounds: int = 1,
        registry: Optional[RoleRegistry] = None,
    ):
        self.client = client
        self.model = model
        self.max_specialists = max(1, max_specialists)
        self.max_collab_rounds = max(1, max_collab_rounds)
        self.registry = registry or RoleRegistry()

    # ── public alias for backward compat ──────────────────────────────

    def get_role_prompts(self) -> Dict[str, str]:
        """Return a dict of {name: system_prompt} for all review roles."""
        return {
            r.name: r.system_prompt
            for r in self.registry.list_roles(tag="review")
        }

    # ── main entry point ──────────────────────────────────────────────

    def review_candidates(
        self,
        task: str,
        candidates: List[Dict[str, Any]],
        focus: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Run specialist reviews and return synthesized output."""
        normalized_candidates = self._normalize_candidates(candidates)
        if not normalized_candidates:
            return {
                "success": False,
                "error": "No valid candidates provided for delegation",
            }

        specialist_roles = self._select_roles(task, focus)
        specialist_reviews: List[SpecialistReview] = []

        for role in specialist_roles:
            review_text = self._run_specialist(role, task, normalized_candidates)
            specialist_reviews.append(SpecialistReview(role=role.name, content=review_text))

        synthesis_text = self._synthesize(task, normalized_candidates, specialist_reviews)
        return {
            "success": True,
            "specialists": [
                {"role": item.role, "review": item.content} for item in specialist_reviews
            ],
            "synthesis": synthesis_text,
        }

    # ── extraction helper (map-reduce page analysis) ──────────────────

    def extract_page(self, raw_content: str, task: str = "") -> str:
        """Run the extraction specialist on a single raw page.

        Useful for map-reduce: call this per page in a sub-agent, then
        only pass compact extractions into the main context.
        """
        extraction_role = self.registry.get("extraction")
        if extraction_role is None:
            # Fallback inline prompt
            prompt = (
                "Extract key facts, actionable steps, config snippets, "
                "and owner/contact info from the following documentation. "
                "Output a concise structured summary."
            )
        else:
            prompt = extraction_role.system_prompt

        user_msg = raw_content
        if task:
            user_msg = f"Task context: {task}\n\n---\n\n{raw_content}"

        messages = [
            ChatMessage(role="system", content=prompt),
            ChatMessage(role="user", content=user_msg[:6000]),
        ]
        response = self.client.chat(messages, model=self.model)
        return response.content

    # ── role selection ────────────────────────────────────────────────

    def _select_roles(self, task: str, focus: Optional[List[str]]) -> List[Role]:
        """Select specialist roles based on focus and task intent."""
        selected: List[Role] = []
        seen: set = set()

        if focus:
            for item in focus:
                key = str(item).strip().lower()
                role = self.registry.get(key)
                if role and key not in seen:
                    selected.append(role)
                    seen.add(key)

        task_lower = task.lower()
        if "security" in task_lower and "security" not in seen:
            role = self.registry.get("security")
            if role:
                selected.append(role)
                seen.add("security")

        if not selected:
            # Default to the three standard review roles
            for name in ("relevance", "freshness", "applicability"):
                role = self.registry.get(name)
                if role:
                    selected.append(role)

        return selected[: self.max_specialists]

    def _normalize_candidates(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        """Normalize candidate pages into compact review format."""
        normalized: List[Dict[str, str]] = []

        for index, candidate in enumerate(candidates, 1):
            if not isinstance(candidate, dict):
                continue

            title = str(candidate.get("title") or f"Candidate {index}").strip()
            content = str(candidate.get("content") or candidate.get("excerpt") or "").strip()
            if not content:
                continue

            owner = str(candidate.get("owner") or candidate.get("author") or "unknown").strip()
            url = str(candidate.get("url") or candidate.get("link") or "").strip()
            last_updated = str(
                candidate.get("last_updated")
                or candidate.get("lastModified")
                or candidate.get("updated")
                or "unknown"
            ).strip()

            normalized.append(
                {
                    "title": title,
                    "content": content[:2500],
                    "owner": owner,
                    "url": url,
                    "last_updated": last_updated,
                }
            )

        return normalized

    def _run_specialist(
        self,
        role: Role,
        task: str,
        candidates: List[Dict[str, str]],
    ) -> str:
        """Run one specialist review."""
        payload = {
            "task": task,
            "role": role.name,
            "candidates": candidates,
            "instructions": [
                "Rank top 3 candidates with rationale.",
                "Call out risks/uncertainties.",
                "Mention owner/contact signal if present.",
                "Keep response concise and structured.",
            ],
        }

        messages = [
            ChatMessage(role="system", content=role.system_prompt),
            ChatMessage(role="user", content=json.dumps(payload, ensure_ascii=False)),
        ]
        response = self.client.chat(messages, model=self.model)
        return response.content

    def _synthesize(
        self,
        task: str,
        candidates: List[Dict[str, str]],
        specialist_reviews: List[SpecialistReview],
    ) -> str:
        """Synthesize specialist outputs into one recommendation."""
        # Use the synthesizer role from the registry if available
        synth_role = self.registry.get("synthesizer")
        if synth_role:
            synthesis_prompt = synth_role.system_prompt
        else:
            synthesis_prompt = (
                "You are a lead engineer synthesizing specialist reviews. "
                "Return: best page(s), final recommended solution, confidence, risks, and owner/contact list."
            )

        review_payload = [{"role": item.role, "review": item.content} for item in specialist_reviews]
        synthesis_input = {
            "task": task,
            "candidates": candidates,
            "specialist_reviews": review_payload,
            "required_output": [
                "Top recommended page(s) with short reason",
                "Concrete solution summary",
                "Owner/contact info from candidates",
                "Confidence level and why",
                "Open risks",
            ],
        }
        messages = [
            ChatMessage(role="system", content=synthesis_prompt),
            ChatMessage(role="user", content=json.dumps(synthesis_input, ensure_ascii=False)),
        ]
        response = self.client.chat(messages, model=self.model)
        return response.content
