"""Lightweight process-flow tracer.

Two output channels:
- stderr: ANSI-colored one-liners for human observation.
- JSONL file: machine-readable events for replay / debugging.

Replaces the heavyweight AgentLogger hierarchy from llm-service.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


# ANSI colour codes (no third-party dep)
_RESET = "\033[0m"
_DIM = "\033[2m"
_BOLD = "\033[1m"
_GREEN = "\033[32m"
_RED = "\033[31m"
_YELLOW = "\033[33m"
_CYAN = "\033[36m"
_MAGENTA = "\033[35m"

_EVENT_STYLES = {
    "task_start": (_CYAN + _BOLD, "[task]"),
    "iter":       (_GREEN, ""),          # prefix built dynamically
    "budget":     (_DIM, "[budget]"),
    "compact":    (_YELLOW, "[compact]"),
    "truncate":   (_MAGENTA, "[truncate]"),
    "task_end":   (_CYAN + _BOLD, "[done]"),
}


class Tracer:
    """Minimal process-flow logger.

    Args:
        session_id: Used to name the JSONL file.
        stderr: Write coloured one-liners to stderr.
        file: Write JSONL events to `trace_dir/<session_id>.jsonl`.
        trace_dir: Directory for log files (created lazily).
    """

    def __init__(
        self,
        session_id: str = "",
        stderr: bool = True,
        file: bool = True,
        trace_dir: str = ".digimate/log",
    ) -> None:
        self._stderr = stderr
        self._file = file
        self._trace_dir = Path(trace_dir)
        self._session_id = session_id
        self._log_path: Optional[Path] = None

    # ── public API ───────────────────────────────────────────────────

    def emit(self, event: str, **kw: Any) -> None:
        """Emit a trace event to both channels."""
        ts = datetime.now(timezone.utc).isoformat(timespec="milliseconds")

        if self._stderr:
            self._write_stderr(event, kw)

        if self._file:
            self._write_jsonl(ts, event, kw)

    # ── stderr (human-readable) ──────────────────────────────────────

    def _write_stderr(self, event: str, kw: dict) -> None:
        style, prefix = _EVENT_STYLES.get(event, (_DIM, f"[{event}]"))
        msg = self._format_stderr(event, prefix, kw)
        sys.stderr.write(f"{style}{msg}{_RESET}\n")

    @staticmethod
    def _format_stderr(event: str, prefix: str, kw: dict) -> str:
        if event == "task_start":
            task = kw.get("task", "")
            if len(task) > 60:
                task = task[:57] + "..."
            return f'{prefix} "{task}"'

        if event == "iter":
            n = kw.get("n", "?")
            action = kw.get("action", "?")
            ok = kw.get("ok", True)
            tokens = kw.get("tokens", 0)
            thought = kw.get("thought", "")
            mark = "✓" if ok else "✗"
            err = kw.get("error", "")
            if not ok and err:
                detail = f'ERR "{err[:50]}"'
            elif tokens:
                detail = f"({tokens:,} tok)"
            else:
                detail = ""
            thought_hint = f"  💭 {thought[:60]}" if thought else ""
            return f"[{n}] → {action} {mark} {detail}{thought_hint}"

        if event == "budget":
            used = kw.get("used", 0)
            limit = kw.get("limit", 0)
            pct = int(used / limit * 100) if limit else 0
            return f"{prefix} {used:,} / {limit:,} tokens ({pct}%)"

        if event == "compact":
            msgs = kw.get("messages", 0)
            tokens = kw.get("tokens", 0)
            return f"{prefix} {msgs} messages → summary ({tokens:,} tok)"

        if event == "truncate":
            action = kw.get("action", "?")
            orig = kw.get("orig", 0)
            trunc = kw.get("trunc", 0)
            return f"{prefix} {action} {orig:,}→{trunc:,} tok"

        if event == "task_end":
            iters = kw.get("iters", 0)
            tokens = kw.get("tokens", 0)
            return f"{prefix} {iters} iterations, {tokens:,} tokens total"

        # Fallback
        return f"{prefix} {kw}" if kw else prefix

    # ── JSONL file ───────────────────────────────────────────────────

    def _write_jsonl(self, ts: str, event: str, kw: dict) -> None:
        if self._log_path is None:
            self._trace_dir.mkdir(parents=True, exist_ok=True)
            self._log_path = self._trace_dir / f"{self._session_id}.jsonl"

        record = {"ts": ts, "event": event, **kw}
        with open(self._log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


# ── Convenience factory ──────────────────────────────────────────────

def create_tracer(
    session_id: str,
    stderr: bool = True,
    file: bool = True,
    trace_dir: str = ".digimate/log",
) -> Tracer:
    """Create a Tracer from agent config values."""
    return Tracer(session_id=session_id, stderr=stderr, file=file, trace_dir=trace_dir)
