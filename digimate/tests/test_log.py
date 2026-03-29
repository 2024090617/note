"""Tests for core/log.py — Tracer."""

import json
from pathlib import Path

from digimate.core.log import Tracer, create_tracer


def test_create_tracer_disabled():
    t = create_tracer(session_id="test", stderr=False, file=False)
    assert isinstance(t, Tracer)
    t.emit("test_event", key="val")  # should not raise


def test_tracer_jsonl(tmp_path):
    t = Tracer(stderr=False, file=True, trace_dir=str(tmp_path))
    t.emit("task_start", task="hello")
    t.emit("task_end", status="ok")
    files = list(tmp_path.glob("*.jsonl"))
    assert len(files) == 1
    lines = files[0].read_text().strip().split("\n")
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["event"] == "task_start"
    assert first["task"] == "hello"
