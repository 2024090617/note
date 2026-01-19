"""
State persistence for dual-worker framework.

Stores task execution history, worker outputs, judge decisions,
and execution traces for debugging and recovery.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

from llm_service.dual_worker.models import (
    ExecutionResult,
    TaskSchema,
    WorkerResponse,
    JudgeDecision,
    TaskGraph,
    PlanTask,
)

logger = logging.getLogger(__name__)


class StateStore:
    """
    Stores execution state to JSON files.
    
    Provides:
    - Task execution history
    - Worker outputs and metadata
    - Judge decisions
    - Execution traces
    - Plan artifacts
    """
    
    def __init__(self, storage_dir: Path):
        """
        Initialize state store.
        
        Args:
            storage_dir: Directory for storing state files
        """
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        # Create subdirectories
        self.executions_dir = self.storage_dir / "executions"
        self.plans_dir = self.storage_dir / "plans"
        self.traces_dir = self.storage_dir / "traces"
        
        for d in [self.executions_dir, self.plans_dir, self.traces_dir]:
            d.mkdir(exist_ok=True)
        
        self.logger = logging.getLogger(__name__)
    
    def _serialize_datetime(self, obj: Any) -> Any:
        """Serialize datetime objects to ISO format"""
        if isinstance(obj, datetime):
            return obj.isoformat()
        return obj
    
    def _to_serializable(self, data: Any) -> Any:
        """Convert Pydantic models to JSON-serializable dicts"""
        if hasattr(data, "model_dump"):
            # Pydantic v2
            return data.model_dump(mode="json")
        elif hasattr(data, "dict"):
            # Pydantic v1
            return data.dict()
        elif isinstance(data, dict):
            return {k: self._to_serializable(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._to_serializable(item) for item in data]
        elif isinstance(data, datetime):
            return data.isoformat()
        else:
            return data
    
    def save_execution_result(
        self,
        result: ExecutionResult,
        session_id: Optional[str] = None,
    ) -> Path:
        """
        Save execution result to file.
        
        Args:
            result: Execution result to save
            session_id: Optional session identifier
            
        Returns:
            Path to saved file
        """
        if session_id:
            filename = f"{session_id}_{result.task_id}.json"
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{result.task_id}_{timestamp}.json"
        
        filepath = self.executions_dir / filename
        
        # Convert to serializable format
        data = self._to_serializable(result)
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        
        self.logger.debug(f"Saved execution result to {filepath}")
        
        return filepath
    
    def load_execution_result(self, filepath: Path) -> Dict[str, Any]:
        """
        Load execution result from file.
        
        Args:
            filepath: Path to result file
            
        Returns:
            Dictionary with execution data
        """
        with open(filepath, 'r') as f:
            return json.load(f)
    
    def save_task_graph(
        self,
        task_graph: TaskGraph,
        goal: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Path:
        """
        Save task graph (plan) to file.
        
        Args:
            task_graph: Task graph to save
            goal: Original goal/description
            metadata: Optional metadata (scores, verdict, etc.)
            
        Returns:
            Path to saved file
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"plan_{timestamp}.json"
        filepath = self.plans_dir / filename
        
        data = {
            "goal": goal,
            "created_at": datetime.now().isoformat(),
            "task_graph": self._to_serializable(task_graph),
            "metadata": metadata or {},
        }
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        
        self.logger.info(f"Saved task graph to {filepath}")
        
        return filepath
    
    def load_task_graph(self, filepath: Path) -> tuple[TaskGraph, str, Dict[str, Any]]:
        """
        Load task graph from file.
        
        Args:
            filepath: Path to plan file
            
        Returns:
            Tuple of (TaskGraph, goal, metadata)
        """
        with open(filepath, 'r') as f:
            data = json.load(f)
        
        # Reconstruct TaskGraph
        graph_data = data["task_graph"]
        
        tasks = [PlanTask(**task_data) for task_data in graph_data["tasks"]]
        edges = [tuple(edge) for edge in graph_data["edges"]]
        
        task_graph = TaskGraph(tasks=tasks, edges=edges)
        
        return task_graph, data["goal"], data.get("metadata", {})
    
    def save_execution_trace(
        self,
        session_id: str,
        trace_data: Dict[str, Any],
    ) -> Path:
        """
        Save execution trace for debugging.
        
        Args:
            session_id: Session identifier
            trace_data: Trace information (prompts, responses, timing, etc.)
            
        Returns:
            Path to saved file
        """
        filename = f"trace_{session_id}.json"
        filepath = self.traces_dir / filename
        
        trace_data["session_id"] = session_id
        trace_data["saved_at"] = datetime.now().isoformat()
        
        with open(filepath, 'w') as f:
            json.dump(trace_data, f, indent=2, default=str)
        
        self.logger.debug(f"Saved execution trace to {filepath}")
        
        return filepath
    
    def list_executions(
        self,
        session_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Path]:
        """
        List execution result files.
        
        Args:
            session_id: Optional session filter
            limit: Maximum number of results
            
        Returns:
            List of file paths, most recent first
        """
        if session_id:
            pattern = f"{session_id}_*.json"
        else:
            pattern = "*.json"
        
        files = list(self.executions_dir.glob(pattern))
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        
        return files[:limit]
    
    def list_plans(self, limit: int = 50) -> List[Path]:
        """
        List plan files.
        
        Args:
            limit: Maximum number of results
            
        Returns:
            List of file paths, most recent first
        """
        files = list(self.plans_dir.glob("plan_*.json"))
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        
        return files[:limit]
    
    def create_session_summary(
        self,
        session_id: str,
        results: List[ExecutionResult],
        plan: Optional[TaskGraph] = None,
        goal: Optional[str] = None,
    ) -> Path:
        """
        Create summary file for a complete session.
        
        Args:
            session_id: Session identifier
            results: List of execution results
            plan: Optional task graph
            goal: Optional original goal
            
        Returns:
            Path to summary file
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"summary_{session_id}_{timestamp}.json"
        filepath = self.storage_dir / filename
        
        # Calculate statistics
        total_tasks = len(results)
        completed = sum(1 for r in results if r.status.value == "completed")
        failed = sum(1 for r in results if r.status.value == "failed")
        escalated = sum(1 for r in results if r.escalated)
        
        total_time = sum(r.total_time_seconds for r in results)
        
        summary = {
            "session_id": session_id,
            "goal": goal,
            "created_at": timestamp,
            "statistics": {
                "total_tasks": total_tasks,
                "completed": completed,
                "failed": failed,
                "escalated": escalated,
                "total_time_seconds": total_time,
                "average_time_per_task": total_time / total_tasks if total_tasks > 0 else 0,
            },
            "plan": self._to_serializable(plan) if plan else None,
            "results": [self._to_serializable(r) for r in results],
        }
        
        with open(filepath, 'w') as f:
            json.dump(summary, f, indent=2, default=str)
        
        self.logger.info(f"Saved session summary to {filepath}")
        
        return filepath
    
    def export_to_markdown(
        self,
        session_id: str,
        results: List[ExecutionResult],
        plan: Optional[TaskGraph] = None,
        goal: Optional[str] = None,
    ) -> Path:
        """
        Export session to human-readable Markdown.
        
        Args:
            session_id: Session identifier
            results: List of execution results
            plan: Optional task graph
            goal: Optional original goal
            
        Returns:
            Path to markdown file
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"report_{session_id}_{timestamp}.md"
        filepath = self.storage_dir / filename
        
        lines = [
            f"# Execution Report: {session_id}",
            "",
            f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
        ]
        
        if goal:
            lines.extend([
                f"## Goal",
                "",
                goal,
                "",
            ])
        
        if plan:
            lines.extend([
                f"## Task Plan",
                "",
                f"**Total Tasks:** {len(plan.tasks)}",
                "",
                "### Tasks",
                "",
            ])
            
            for task in plan.tasks:
                lines.extend([
                    f"- **{task.id}**: {task.description}",
                    f"  - Dependencies: {', '.join(task.dependencies) if task.dependencies else 'None'}",
                    f"  - Criticality: {task.criticality.value}",
                    "",
                ])
        
        # Execution results
        lines.extend([
            "## Execution Results",
            "",
        ])
        
        for result in results:
            status_emoji = {
                "completed": "✅",
                "failed": "❌",
                "escalated": "⚠️",
                "rejected": "🚫",
                "pending": "⏸️",
            }.get(result.status.value, "❓")
            
            lines.extend([
                f"### {status_emoji} Task {result.task_id}",
                "",
                f"**Status:** {result.status.value}",
                f"**Attempts:** {result.attempts}",
                f"**Time:** {result.total_time_seconds:.2f}s",
                "",
            ])
            
            if result.worker_a_response or result.worker_b_response:
                lines.append("#### Workers")
                lines.append("")
                
                if result.worker_a_response:
                    lines.extend([
                        f"**Worker A** ({result.worker_a_response.model_name}):",
                        f"```",
                        result.worker_a_response.output[:500] + ("..." if len(result.worker_a_response.output) > 500 else ""),
                        f"```",
                        "",
                    ])
                
                if result.worker_b_response:
                    lines.extend([
                        f"**Worker B** ({result.worker_b_response.model_name}):",
                        f"```",
                        result.worker_b_response.output[:500] + ("..." if len(result.worker_b_response.output) > 500 else ""),
                        f"```",
                        "",
                    ])
            
            if result.judge_decision:
                lines.extend([
                    "#### Judge Decision",
                    "",
                    f"**Verdict:** {result.judge_decision.verdict.value}",
                    f"**Confidence:** {result.judge_decision.confidence:.2f}",
                    f"**Reasoning:** {result.judge_decision.reasoning[:300]}...",
                    "",
                ])
            
            if result.escalated:
                lines.extend([
                    f"**⚠️ Escalated:** {result.escalation_reason}",
                    "",
                ])
            
            lines.append("---")
            lines.append("")
        
        with open(filepath, 'w') as f:
            f.write('\n'.join(lines))
        
        self.logger.info(f"Exported session report to {filepath}")
        
        return filepath


def create_state_store(storage_dir: Optional[Path] = None) -> StateStore:
    """
    Create state store with default location.
    
    Args:
        storage_dir: Optional custom storage directory
        
    Returns:
        StateStore instance
    """
    if storage_dir is None:
        # Default to ~/.dual_worker_state
        storage_dir = Path.home() / ".dual_worker_state"
    
    return StateStore(storage_dir)
