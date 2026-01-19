"""
Data models for the Dual-Worker+Judge framework.

Defines task schemas, worker responses, judge decisions, and execution state
using Pydantic for type safety and validation.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    """Task execution status"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED = "rejected"
    ESCALATED = "escalated"


class TaskCriticality(str, Enum):
    """Task criticality level - determines worker/judge routing"""
    SIMPLE = "simple"          # Single worker, no judge
    STANDARD = "standard"      # Dual worker, Grok judge
    IMPORTANT = "important"    # Dual worker, Grok judge
    CRITICAL = "critical"      # Dual worker, Opus judge


class TaskSchema(BaseModel):
    """
    Atomic task definition with clear input/output and verification criteria.
    
    Follows the principle: "A task is atomic for AI if it has one clear input,
    one measurable output, can be verified automatically, and requires no hidden context."
    """
    task_id: str = Field(..., description="Unique task identifier (e.g., T-001)")
    description: str = Field(..., description="Clear, actionable task description")
    input: Dict[str, Any] = Field(default_factory=dict, description="Task inputs and context")
    output: str = Field(..., description="Expected output specification")
    constraints: List[str] = Field(default_factory=list, description="Task constraints and requirements")
    dependencies: List[str] = Field(default_factory=list, description="Task IDs that must complete first")
    criticality: TaskCriticality = Field(default=TaskCriticality.STANDARD, description="Task importance level")
    estimated_lines: int = Field(default=50, description="Estimated code lines", ge=1)
    verification: str = Field(..., description="How to verify correctness")
    status: TaskStatus = Field(default=TaskStatus.PENDING, description="Current status")
    created_at: datetime = Field(default_factory=datetime.now)
    
    # Execution tracking
    attempts: int = Field(default=0, description="Number of execution attempts")
    max_attempts: int = Field(default=3, description="Maximum retry attempts")
    
    # Cost tracking
    token_budget: Optional[int] = Field(default=None, description="Token limit for this task")
    time_budget_seconds: Optional[int] = Field(default=None, description="Time limit in seconds")


class WorkerStrategy(str, Enum):
    """Worker execution strategy"""
    PRAGMATIC = "pragmatic"          # Fast, clean, idiomatic code
    SECURITY_FIRST = "security_first"  # Security and edge cases
    PERFORMANCE_FIRST = "performance_first"  # Optimization focused
    COMPREHENSIVE = "comprehensive"    # Deep reasoning, all considerations


class WorkerResponse(BaseModel):
    """Response from a worker execution"""
    worker_id: str = Field(..., description="Worker identifier (worker_1, worker_2)")
    model_name: str = Field(..., description="Model used (gpt-4.1, gpt-5-mini, etc.)")
    strategy: WorkerStrategy = Field(..., description="Strategy used")
    output: str = Field(..., description="Generated output (code, plan, etc.)")
    reasoning: Optional[str] = Field(default=None, description="Reasoning/thinking process")
    execution_time_seconds: float = Field(..., description="Execution duration")
    tokens_used: Optional[int] = Field(default=None, description="Token count")
    timestamp: datetime = Field(default_factory=datetime.now)
    
    # Automated verification results
    syntax_valid: Optional[bool] = Field(default=None, description="Syntax check result")
    tests_passed: Optional[bool] = Field(default=None, description="Test execution result")
    linter_score: Optional[float] = Field(default=None, description="Code quality score (0-100)")


class JudgeVerdict(str, Enum):
    """Judge decision outcome"""
    ACCEPT_A = "accept_a"        # Accept Worker A's output
    ACCEPT_B = "accept_b"        # Accept Worker B's output
    REJECT_BOTH = "reject_both"  # Neither is acceptable
    MERGE = "merge"              # Combine best parts


class JudgeCriteria(BaseModel):
    """Evaluation criteria scores"""
    correctness: float = Field(..., ge=0, le=100, description="Does it work correctly?")
    edge_cases: float = Field(..., ge=0, le=100, description="Handles errors/edge cases?")
    security: float = Field(..., ge=0, le=100, description="Security considerations?")
    code_quality: float = Field(..., ge=0, le=100, description="Readable/maintainable?")
    performance: float = Field(..., ge=0, le=100, description="Efficient implementation?")
    completeness: float = Field(..., ge=0, le=100, description="Meets all requirements?")
    
    @property
    def total(self) -> float:
        """Weighted total score"""
        weights = {
            "correctness": 0.30,
            "edge_cases": 0.20,
            "security": 0.20,
            "code_quality": 0.15,
            "performance": 0.10,
            "completeness": 0.05,
        }
        return (
            self.correctness * weights["correctness"] +
            self.edge_cases * weights["edge_cases"] +
            self.security * weights["security"] +
            self.code_quality * weights["code_quality"] +
            self.performance * weights["performance"] +
            self.completeness * weights["completeness"]
        )


class JudgeDecision(BaseModel):
    """Judge's evaluation and decision"""
    verdict: JudgeVerdict = Field(..., description="Final decision")
    confidence: float = Field(..., ge=0, le=1, description="Confidence in decision")
    
    worker_a_scores: JudgeCriteria = Field(..., description="Worker A evaluation")
    worker_b_scores: JudgeCriteria = Field(..., description="Worker B evaluation")
    
    reasoning: str = Field(..., description="Step-by-step analysis")
    concerns: List[str] = Field(default_factory=list, description="Issues identified")
    winner_justification: str = Field(..., description="Why this choice was made")
    
    # For reject_both scenarios
    recommendation: Optional[str] = Field(default=None, description="Guidance for retry")
    missing_requirements: List[str] = Field(default_factory=list, description="What's missing")
    
    # For merge scenarios
    merge_strategy: Optional[Dict[str, Any]] = Field(default=None, description="How to merge outputs")
    
    model_name: str = Field(..., description="Judge model used")
    execution_time_seconds: float = Field(..., description="Evaluation duration")
    timestamp: datetime = Field(default_factory=datetime.now)


class ExecutionResult(BaseModel):
    """Final result of task execution"""
    task_id: str = Field(..., description="Task identifier")
    status: TaskStatus = Field(..., description="Final status")
    
    worker_a_response: Optional[WorkerResponse] = Field(default=None)
    worker_b_response: Optional[WorkerResponse] = Field(default=None)
    judge_decision: Optional[JudgeDecision] = Field(default=None)
    
    final_output: Optional[str] = Field(default=None, description="Accepted output")
    final_metadata: Dict[str, Any] = Field(default_factory=dict, description="Execution metadata")
    
    attempts: int = Field(default=1, description="Number of attempts")
    total_time_seconds: float = Field(..., description="Total execution time")
    
    # Human escalation data
    escalated: bool = Field(default=False)
    escalation_reason: Optional[str] = Field(default=None)
    human_decision: Optional[str] = Field(default=None)
    
    created_at: datetime = Field(default_factory=datetime.now)
    completed_at: Optional[datetime] = Field(default=None)


class PlanTask(BaseModel):
    """Task definition for planning phase"""
    id: str = Field(..., description="Task ID (T1, T2, etc.)")
    description: str = Field(..., description="Task description")
    input: str = Field(..., description="What it needs")
    output: str = Field(..., description="What it produces")
    estimated_lines: int = Field(..., description="Estimated LOC")
    dependencies: List[str] = Field(default_factory=list, description="Dependency task IDs")
    criticality: TaskCriticality = Field(default=TaskCriticality.STANDARD)


class TaskGraph(BaseModel):
    """Task dependency graph (DAG)"""
    tasks: List[PlanTask] = Field(..., description="All tasks in the plan")
    edges: List[tuple[str, str]] = Field(default_factory=list, description="(from_task, to_task) edges")
    
    def validate_dag(self) -> tuple[bool, List[str]]:
        """
        Validate that graph is a valid DAG (no cycles, all references valid).
        Returns (is_valid, list_of_issues)
        """
        issues = []
        
        # Check all task IDs are unique
        task_ids = [t.id for t in self.tasks]
        if len(task_ids) != len(set(task_ids)):
            issues.append("Duplicate task IDs found")
        
        # Check all edge references are valid
        task_id_set = set(task_ids)
        for from_id, to_id in self.edges:
            if from_id not in task_id_set:
                issues.append(f"Edge references non-existent task: {from_id}")
            if to_id not in task_id_set:
                issues.append(f"Edge references non-existent task: {to_id}")
        
        # Check for cycles using DFS
        if not issues:
            adj_list = {task_id: [] for task_id in task_ids}
            for from_id, to_id in self.edges:
                adj_list[from_id].append(to_id)
            
            visited = set()
            rec_stack = set()
            
            def has_cycle(node):
                visited.add(node)
                rec_stack.add(node)
                for neighbor in adj_list.get(node, []):
                    if neighbor not in visited:
                        if has_cycle(neighbor):
                            return True
                    elif neighbor in rec_stack:
                        return True
                rec_stack.remove(node)
                return False
            
            for task_id in task_ids:
                if task_id not in visited:
                    if has_cycle(task_id):
                        issues.append("Circular dependency detected in task graph")
                        break
        
        # Check for orphan tasks (tasks with no dependencies and no dependents)
        if not issues:
            has_incoming = {task_id: False for task_id in task_ids}
            has_outgoing = {task_id: False for task_id in task_ids}
            
            for from_id, to_id in self.edges:
                has_outgoing[from_id] = True
                has_incoming[to_id] = True
            
            # Allow root tasks (no incoming) and leaf tasks (no outgoing)
            # but warn about completely isolated tasks
            for task_id in task_ids:
                if not has_incoming[task_id] and not has_outgoing[task_id] and len(self.tasks) > 1:
                    issues.append(f"Task {task_id} has no dependencies or dependents (isolated)")
        
        return (len(issues) == 0, issues)
    
    def topological_sort(self) -> List[str]:
        """
        Return tasks in topological order (dependencies first).
        Raises ValueError if graph has cycles.
        """
        is_valid, issues = self.validate_dag()
        if not is_valid:
            raise ValueError(f"Invalid DAG: {'; '.join(issues)}")
        
        # Build adjacency list and in-degree count
        task_ids = [t.id for t in self.tasks]
        adj_list = {task_id: [] for task_id in task_ids}
        in_degree = {task_id: 0 for task_id in task_ids}
        
        for from_id, to_id in self.edges:
            adj_list[from_id].append(to_id)
            in_degree[to_id] += 1
        
        # Kahn's algorithm
        queue = [task_id for task_id in task_ids if in_degree[task_id] == 0]
        result = []
        
        while queue:
            current = queue.pop(0)
            result.append(current)
            
            for neighbor in adj_list[current]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
        
        return result


class PlanComparison(BaseModel):
    """Comparison of two planning outputs"""
    plan_a_tasks: List[PlanTask] = Field(..., description="Plan A tasks")
    plan_b_tasks: List[PlanTask] = Field(..., description="Plan B tasks")
    
    plan_a_score: float = Field(..., ge=0, le=100, description="Plan A total score")
    plan_b_score: float = Field(..., ge=0, le=100, description="Plan B total score")
    
    plan_a_strengths: List[str] = Field(default_factory=list)
    plan_a_weaknesses: List[str] = Field(default_factory=list)
    plan_b_strengths: List[str] = Field(default_factory=list)
    plan_b_weaknesses: List[str] = Field(default_factory=list)
    
    missing_tasks: List[str] = Field(default_factory=list, description="Tasks neither plan included")
    dependency_issues: List[str] = Field(default_factory=list, description="DAG problems found")
