"""
Dual-Worker+Judge AI Framework

A production-ready multi-model orchestration system that runs two AI workers
in parallel with intelligent judging for high-quality task execution.

Supports both code generation and common tasks (writing, analysis, planning, etc.)
"""

from llm_service.dual_worker.models import (
    TaskSchema,
    TaskStatus,
    TaskType,
    TaskCriticality,
    WorkerResponse,
    JudgeDecision,
    JudgeVerdict,
    JudgeCriteria,
    ExecutionResult,
    PlanTask,
    TaskGraph,
)
from llm_service.dual_worker.config import DualWorkerConfig, ModelRole
from llm_service.dual_worker.worker import Worker, create_dual_workers, get_worker_strategies_for_task_type
from llm_service.dual_worker.judge import Judge
from llm_service.dual_worker.orchestrator import DualWorkerOrchestrator

__all__ = [
    "TaskSchema",
    "TaskStatus",
    "TaskType",
    "TaskCriticality",
    "WorkerResponse",
    "JudgeDecision",
    "JudgeVerdict",
    "JudgeCriteria",
    "ExecutionResult",
    "PlanTask",
    "TaskGraph",
    "DualWorkerConfig",
    "ModelRole",
    "Worker",
    "create_dual_workers",
    "get_worker_strategies_for_task_type",
    "Judge",
    "DualWorkerOrchestrator",
]
