"""
Dual-Worker+Judge AI Framework

A production-ready multi-model orchestration system that runs two AI workers
in parallel with intelligent judging for high-quality task execution.
"""

from llm_service.dual_worker.models import (
    TaskSchema,
    TaskStatus,
    TaskCriticality,
    WorkerResponse,
    JudgeDecision,
    JudgeVerdict,
    ExecutionResult,
    PlanTask,
    TaskGraph,
)
from llm_service.dual_worker.config import DualWorkerConfig, ModelRole
from llm_service.dual_worker.worker import Worker
from llm_service.dual_worker.judge import Judge
from llm_service.dual_worker.orchestrator import DualWorkerOrchestrator

__all__ = [
    "TaskSchema",
    "TaskStatus",
    "TaskCriticality",
    "WorkerResponse",
    "JudgeDecision",
    "JudgeVerdict",
    "ExecutionResult",
    "PlanTask",
    "TaskGraph",
    "DualWorkerConfig",
    "ModelRole",
    "Worker",
    "Judge",
    "DualWorkerOrchestrator",
]
