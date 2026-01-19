"""
Observability and tracing for dual-worker framework.

Provides execution traces, debugging information, and performance metrics.
"""

import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, List, Optional
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class ExecutionTrace:
    """Trace of a single execution step"""
    step_name: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_seconds: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    
    def complete(self, error: Optional[str] = None):
        """Mark step as completed"""
        self.completed_at = datetime.now()
        self.duration_seconds = (self.completed_at - self.started_at).total_seconds()
        self.error = error


@dataclass
class TaskTrace:
    """Complete trace for a task execution"""
    task_id: str
    started_at: datetime
    steps: List[ExecutionTrace] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def add_step(self, step_name: str, metadata: Optional[Dict[str, Any]] = None) -> ExecutionTrace:
        """Add a new step to the trace"""
        step = ExecutionTrace(
            step_name=step_name,
            started_at=datetime.now(),
            metadata=metadata or {}
        )
        self.steps.append(step)
        return step
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "task_id": self.task_id,
            "started_at": self.started_at.isoformat(),
            "total_duration": sum(s.duration_seconds for s in self.steps),
            "step_count": len(self.steps),
            "steps": [
                {
                    "name": s.step_name,
                    "started_at": s.started_at.isoformat(),
                    "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                    "duration_seconds": s.duration_seconds,
                    "metadata": s.metadata,
                    "error": s.error,
                }
                for s in self.steps
            ],
            "metadata": self.metadata,
        }


class ExecutionTracer:
    """
    Collects execution traces for debugging and analysis.
    
    Usage:
        tracer = ExecutionTracer()
        
        with tracer.trace_task("T1") as task_trace:
            step = task_trace.add_step("worker_1_execution")
            # ... work ...
            step.complete()
    """
    
    def __init__(self):
        self.traces: Dict[str, TaskTrace] = {}
        self.current_task: Optional[str] = None
    
    @contextmanager
    def trace_task(self, task_id: str, metadata: Optional[Dict[str, Any]] = None):
        """Context manager for tracing a task"""
        task_trace = TaskTrace(
            task_id=task_id,
            started_at=datetime.now(),
            metadata=metadata or {}
        )
        
        self.traces[task_id] = task_trace
        self.current_task = task_id
        
        try:
            yield task_trace
        finally:
            self.current_task = None
    
    @contextmanager
    def trace_step(self, step_name: str, metadata: Optional[Dict[str, Any]] = None):
        """Context manager for tracing a step within current task"""
        if not self.current_task:
            logger.warning(f"trace_step called outside of trace_task context: {step_name}")
            yield None
            return
        
        task_trace = self.traces.get(self.current_task)
        if not task_trace:
            logger.warning(f"No task trace found for {self.current_task}")
            yield None
            return
        
        step = task_trace.add_step(step_name, metadata)
        
        try:
            yield step
        except Exception as e:
            step.complete(error=str(e))
            raise
        else:
            step.complete()
    
    def get_trace(self, task_id: str) -> Optional[TaskTrace]:
        """Get trace for a specific task"""
        return self.traces.get(task_id)
    
    def get_all_traces(self) -> List[TaskTrace]:
        """Get all traces"""
        return list(self.traces.values())
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get aggregate statistics across all traces"""
        if not self.traces:
            return {}
        
        step_times = defaultdict(list)
        step_counts = defaultdict(int)
        
        for trace in self.traces.values():
            for step in trace.steps:
                step_times[step.step_name].append(step.duration_seconds)
                step_counts[step.step_name] += 1
        
        step_stats = {}
        for step_name, times in step_times.items():
            step_stats[step_name] = {
                "count": step_counts[step_name],
                "total_time": sum(times),
                "avg_time": sum(times) / len(times),
                "min_time": min(times),
                "max_time": max(times),
            }
        
        return {
            "total_tasks": len(self.traces),
            "total_steps": sum(len(t.steps) for t in self.traces.values()),
            "step_statistics": step_stats,
        }
    
    def export_traces(self) -> Dict[str, Any]:
        """Export all traces as dictionary"""
        return {
            "traces": [trace.to_dict() for trace in self.traces.values()],
            "statistics": self.get_statistics(),
        }


class PerformanceMonitor:
    """
    Monitor performance metrics during execution.
    
    Tracks:
    - Token usage
    - Execution times
    - API call counts
    - Error rates
    """
    
    def __init__(self):
        self.metrics = defaultdict(lambda: defaultdict(int))
        self.timings = defaultdict(list)
    
    def record_tokens(self, model_name: str, tokens: int):
        """Record token usage"""
        self.metrics["tokens"][model_name] += tokens
        self.metrics["tokens"]["total"] += tokens
    
    def record_api_call(self, model_name: str, success: bool = True):
        """Record API call"""
        self.metrics["api_calls"][model_name] += 1
        self.metrics["api_calls"]["total"] += 1
        
        if not success:
            self.metrics["api_errors"][model_name] += 1
            self.metrics["api_errors"]["total"] += 1
    
    def record_timing(self, operation: str, duration_seconds: float):
        """Record operation timing"""
        self.timings[operation].append(duration_seconds)
    
    @contextmanager
    def measure(self, operation: str):
        """Context manager to measure operation duration"""
        start = time.time()
        try:
            yield
        finally:
            duration = time.time() - start
            self.record_timing(operation, duration)
    
    def get_summary(self) -> Dict[str, Any]:
        """Get performance summary"""
        summary = {
            "tokens": dict(self.metrics["tokens"]),
            "api_calls": dict(self.metrics["api_calls"]),
            "api_errors": dict(self.metrics["api_errors"]),
            "timings": {},
        }
        
        for operation, times in self.timings.items():
            summary["timings"][operation] = {
                "count": len(times),
                "total": sum(times),
                "average": sum(times) / len(times) if times else 0,
                "min": min(times) if times else 0,
                "max": max(times) if times else 0,
            }
        
        return summary
    
    def reset(self):
        """Reset all metrics"""
        self.metrics.clear()
        self.timings.clear()


# Global instances for convenience
_global_tracer = None
_global_monitor = None


def get_tracer() -> ExecutionTracer:
    """Get global tracer instance"""
    global _global_tracer
    if _global_tracer is None:
        _global_tracer = ExecutionTracer()
    return _global_tracer


def get_monitor() -> PerformanceMonitor:
    """Get global monitor instance"""
    global _global_monitor
    if _global_monitor is None:
        _global_monitor = PerformanceMonitor()
    return _global_monitor
