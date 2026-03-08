"""Delegation engine for specialist sub-agent review."""

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ..copilot_client import ChatMessage, CopilotBridgeClient


@dataclass
class SpecialistReview:
    """Single specialist review output."""

    role: str
    content: str


class DelegationEngine:
    """Runs specialist reviews and synthesizes a recommendation."""

    ROLE_PROMPTS: Dict[str, str] = {
        "relevance": (
            "You are a relevance specialist. Rank candidate documentation pages by direct task fit. "
            "Prioritize practical fixability and task alignment."
        ),
        "freshness": (
            "You are a freshness specialist. Evaluate if candidate pages appear current and safe to trust. "
            "Use last-updated, version clues, and deprecation signals."
        ),
        "applicability": (
            "You are an implementation specialist. Evaluate whether each candidate solution can be applied quickly "
            "with low risk and clear steps."
        ),
        "security": (
            "You are a security specialist. Review candidate solutions for security pitfalls and safer alternatives."
        ),
    }

    def __init__(
        self,
        client: CopilotBridgeClient,
        model: str,
        max_specialists: int = 3,
        max_collab_rounds: int = 1,
    ):
        self.client = client
        self.model = model
        self.max_specialists = max(1, max_specialists)
        self.max_collab_rounds = max(1, max_collab_rounds)

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
            specialist_reviews.append(SpecialistReview(role=role, content=review_text))

        synthesis_text = self._synthesize(task, normalized_candidates, specialist_reviews)
        return {
            "success": True,
            "specialists": [
                {"role": item.role, "review": item.content} for item in specialist_reviews
            ],
            "synthesis": synthesis_text,
        }

    def _select_roles(self, task: str, focus: Optional[List[str]]) -> List[str]:
        """Select specialist roles based on focus and task intent."""
        selected: List[str] = []

        if focus:
            for item in focus:
                key = str(item).strip().lower()
                if key in self.ROLE_PROMPTS and key not in selected:
                    selected.append(key)

        task_lower = task.lower()
        if "security" in task_lower and "security" not in selected:
            selected.append("security")

        if not selected:
            selected = ["relevance", "freshness", "applicability"]

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
        role: str,
        task: str,
        candidates: List[Dict[str, str]],
    ) -> str:
        """Run one specialist review."""
        prompt = self.ROLE_PROMPTS.get(role, self.ROLE_PROMPTS["relevance"])
        payload = {
            "task": task,
            "role": role,
            "candidates": candidates,
            "instructions": [
                "Rank top 3 candidates with rationale.",
                "Call out risks/uncertainties.",
                "Mention owner/contact signal if present.",
                "Keep response concise and structured.",
            ],
        }

        messages = [
            ChatMessage(role="system", content=prompt),
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
        review_payload = [{"role": item.role, "review": item.content} for item in specialist_reviews]
        synthesis_prompt = (
            "You are a lead engineer synthesizing specialist reviews. "
            "Return: best page(s), final recommended solution, confidence, risks, and owner/contact list."
        )
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
