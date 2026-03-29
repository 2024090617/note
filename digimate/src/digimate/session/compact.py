"""Auto-compaction logic for sessions.

Extracted as a helper so the agent can trigger compaction
before sending the next LLM request.
"""

from __future__ import annotations

from digimate.session.budget import ContextBudgetManager, estimate_tokens
from digimate.session.session import Session


def maybe_compact(
    session: Session,
    budget: ContextBudgetManager,
    keep_recent: int = 4,
) -> str:
    """Compact the session if the budget is exceeded.

    Returns the summary text if compaction occurred, else "".
    """
    history_text = "\n".join(m.content for m in session.get_messages())
    budget.record("history", history_text)

    if not budget.is_over_budget():
        return ""

    summary = session.compact(keep_recent=keep_recent)

    # Re-record after compaction
    history_text = "\n".join(m.content for m in session.get_messages())
    budget.record("history", history_text)
    return summary
