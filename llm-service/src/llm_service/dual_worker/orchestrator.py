"""
Task orchestrator for dual-worker+judge system.

Coordinates execution of tasks with parallel workers and judge evaluation.
Handles DAG execution, retries, and human escalation.
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any, Callable

from llm_service.dual_worker.config import DualWorkerConfig
from llm_service.dual_worker.models import (
    TaskSchema,
    TaskStatus,
    TaskCriticality,
    WorkerResponse,
    JudgeDecision,
    JudgeVerdict,
    ExecutionResult,
    TaskGraph,
)
from llm_service.dual_worker.worker import Worker, create_dual_workers
from llm_service.dual_worker.judge import Judge

logger = logging.getLogger(__name__)


class DualWorkerOrchestrator:
    """
    Orchestrates dual-worker+judge execution workflow.
    
    Main responsibilities:
    - Route tasks to appropriate workers based on criticality
    - Execute workers in parallel when enabled
    - Coordinate judge evaluation
    - Handle retries with feedback
    - Escalate to human when needed
    - Track execution state and artifacts
    """
    
    def __init__(
        self,
        config: Optional[DualWorkerConfig] = None,
        human_callback: Optional[Callable] = None,
    ):
        """
        Initialize orchestrator.
        
        Args:
            config: Configuration (uses defaults if not provided)
            human_callback: Async function to call for human decisions
                           Should accept (task, decision) and return chosen output
        """
        self.config = config or DualWorkerConfig.create_default()
        self.human_callback = human_callback
        
        # Import ModelRole here to avoid circular dependency
        from llm_service.dual_worker.config import ModelRole
        
        # Create workers
        worker_1_config, worker_2_config = self.config.get_worker_configs()
        self.worker_1, self.worker_2 = create_dual_workers(
            worker_1_config,
            worker_2_config,
        )
        
        # Create judges
        self.judge_standard = Judge(
            self.config.models[ModelRole.JUDGE_STANDARD]
        )
        self.judge_premium = Judge(
            self.config.models[ModelRole.JUDGE_PREMIUM]
        )
        
        # Execution state
        self.execution_history: List[ExecutionResult] = []
        
        self.logger = logging.getLogger(__name__)
    
    def _get_judge_for_task(self, task: TaskSchema) -> Judge:
        """Select appropriate judge based on task criticality"""
        if task.criticality == TaskCriticality.CRITICAL:
            return self.judge_premium
        else:
            return self.judge_standard
    
    async def execute_single_worker(
        self,
        task: TaskSchema,
        retry_feedback: Optional[dict] = None,
    ) -> ExecutionResult:
        """
        Execute task with single worker (for simple tasks).
        
        Args:
            task: Task to execute
            retry_feedback: Optional feedback from previous attempt
            
        Returns:
            ExecutionResult
        """
        self.logger.info(f"Executing task {task.task_id} with single worker")
        
        start_time = datetime.now()
        
        # Use worker 1 (pragmatic/fast) for simple tasks
        try:
            worker_response = await self.worker_1.execute(task, retry_feedback)
            
            # Run verification
            verification = await self.worker_1.verify_output(worker_response.output, task)
            worker_response.syntax_valid = verification.get("syntax_valid")
            worker_response.tests_passed = verification.get("tests_passed")
            worker_response.linter_score = verification.get("linter_score")
            
            # Accept if syntax is valid (simple tasks don't need judge)
            if verification.get("syntax_valid") is not False:
                total_time = (datetime.now() - start_time).total_seconds()
                
                return ExecutionResult(
                    task_id=task.task_id,
                    status=TaskStatus.COMPLETED,
                    worker_a_response=worker_response,
                    final_output=worker_response.output,
                    final_metadata={
                        "mode": "single_worker",
                        "worker": self.worker_1.worker_id,
                    },
                    attempts=task.attempts + 1,
                    total_time_seconds=total_time,
                    completed_at=datetime.now(),
                )
            else:
                # Syntax error - escalate or retry
                total_time = (datetime.now() - start_time).total_seconds()
                
                return ExecutionResult(
                    task_id=task.task_id,
                    status=TaskStatus.FAILED,
                    worker_a_response=worker_response,
                    escalated=True,
                    escalation_reason="Syntax validation failed",
                    attempts=task.attempts + 1,
                    total_time_seconds=total_time,
                )
                
        except Exception as e:
            self.logger.error(f"Single worker execution failed: {str(e)}")
            total_time = (datetime.now() - start_time).total_seconds()
            
            return ExecutionResult(
                task_id=task.task_id,
                status=TaskStatus.FAILED,
                escalated=True,
                escalation_reason=f"Worker failed: {str(e)}",
                attempts=task.attempts + 1,
                total_time_seconds=total_time,
            )
    
    async def execute_dual_worker(
        self,
        task: TaskSchema,
        retry_feedback: Optional[dict] = None,
    ) -> ExecutionResult:
        """
        Execute task with dual workers + judge.
        
        Args:
            task: Task to execute
            retry_feedback: Optional feedback from previous attempt
            
        Returns:
            ExecutionResult
        """
        self.logger.info(
            f"Executing task {task.task_id} with dual workers + "
            f"{'premium' if task.criticality == TaskCriticality.CRITICAL else 'standard'} judge"
        )
        
        start_time = datetime.now()
        
        try:
            # Execute both workers in parallel
            if self.config.enable_parallel_workers:
                worker_1_task = self.worker_1.execute(task, retry_feedback)
                worker_2_task = self.worker_2.execute(task, retry_feedback)
                
                worker_1_response, worker_2_response = await asyncio.gather(
                    worker_1_task,
                    worker_2_task,
                )
            else:
                # Sequential execution (for debugging or rate limit management)
                worker_1_response = await self.worker_1.execute(task, retry_feedback)
                worker_2_response = await self.worker_2.execute(task, retry_feedback)
            
            # Run verification on both outputs
            verify_1_task = self.worker_1.verify_output(worker_1_response.output, task)
            verify_2_task = self.worker_2.verify_output(worker_2_response.output, task)
            
            verify_1, verify_2 = await asyncio.gather(verify_1_task, verify_2_task)
            
            worker_1_response.syntax_valid = verify_1.get("syntax_valid")
            worker_1_response.tests_passed = verify_1.get("tests_passed")
            worker_1_response.linter_score = verify_1.get("linter_score")
            
            worker_2_response.syntax_valid = verify_2.get("syntax_valid")
            worker_2_response.tests_passed = verify_2.get("tests_passed")
            worker_2_response.linter_score = verify_2.get("linter_score")
            
            # Judge evaluation
            judge = self._get_judge_for_task(task)
            decision = await judge.evaluate(
                task,
                worker_1_response,
                worker_2_response,
                auto_verify=True,
            )
            
            total_time = (datetime.now() - start_time).total_seconds()
            
            # Process decision
            final_output = None
            final_status = TaskStatus.COMPLETED
            escalated = False
            escalation_reason = None
            
            if decision.verdict == JudgeVerdict.ACCEPT_A:
                final_output = worker_1_response.output
            elif decision.verdict == JudgeVerdict.ACCEPT_B:
                final_output = worker_2_response.output
            elif decision.verdict == JudgeVerdict.REJECT_BOTH:
                final_status = TaskStatus.REJECTED
                escalated = True
                escalation_reason = "Both outputs rejected by judge"
            elif decision.verdict == JudgeVerdict.MERGE:
                # For now, treat merge as escalation (human needed to merge)
                final_status = TaskStatus.ESCALATED
                escalated = True
                escalation_reason = "Judge recommends merging outputs - human decision needed"
            
            # Check if should escalate despite acceptance
            if not escalated:
                should_escalate, reason = judge.should_escalate(
                    decision,
                    self.config.auto_escalate_threshold,
                    self.config.rejection_threshold,
                )
                if should_escalate:
                    final_status = TaskStatus.ESCALATED
                    escalated = True
                    escalation_reason = reason
            
            return ExecutionResult(
                task_id=task.task_id,
                status=final_status,
                worker_a_response=worker_1_response,
                worker_b_response=worker_2_response,
                judge_decision=decision,
                final_output=final_output,
                final_metadata={
                    "mode": "dual_worker",
                    "judge_model": judge.model_config.model_name,
                },
                attempts=task.attempts + 1,
                total_time_seconds=total_time,
                escalated=escalated,
                escalation_reason=escalation_reason,
                completed_at=datetime.now() if not escalated else None,
            )
            
        except Exception as e:
            self.logger.error(f"Dual worker execution failed: {str(e)}")
            total_time = (datetime.now() - start_time).total_seconds()
            
            return ExecutionResult(
                task_id=task.task_id,
                status=TaskStatus.FAILED,
                escalated=True,
                escalation_reason=f"Execution failed: {str(e)}",
                attempts=task.attempts + 1,
                total_time_seconds=total_time,
            )
    
    async def execute_task(
        self,
        task: TaskSchema,
        retry_feedback: Optional[dict] = None,
    ) -> ExecutionResult:
        """
        Execute a single task with appropriate strategy.
        
        Args:
            task: Task to execute
            retry_feedback: Optional feedback for retry
            
        Returns:
            ExecutionResult
        """
        # Route based on criticality
        if task.criticality == TaskCriticality.SIMPLE:
            result = await self.execute_single_worker(task, retry_feedback)
        else:
            result = await self.execute_dual_worker(task, retry_feedback)
        
        # Store in history
        self.execution_history.append(result)
        
        return result
    
    async def execute_with_retry(
        self,
        task: TaskSchema,
    ) -> ExecutionResult:
        """
        Execute task with automatic retry on rejection.
        
        Args:
            task: Task to execute
            
        Returns:
            Final ExecutionResult
        """
        result = await self.execute_task(task)
        
        # If rejected and retries available, try again with feedback
        if (
            self.config.enable_auto_retry
            and result.status == TaskStatus.REJECTED
            and task.attempts < task.max_attempts
        ):
            self.logger.info(
                f"Task {task.task_id} rejected, retrying with feedback "
                f"(attempt {task.attempts + 1}/{task.max_attempts})"
            )
            
            # Prepare retry feedback from judge
            retry_feedback = None
            if result.judge_decision:
                retry_feedback = {
                    "concerns": result.judge_decision.concerns,
                    "recommendation": result.judge_decision.recommendation,
                }
            
            # Increment attempt counter
            task.attempts += 1
            
            # Retry
            result = await self.execute_task(task, retry_feedback)
        
        return result
    
    async def execute_graph(
        self,
        task_graph: TaskGraph,
        progress_callback: Optional[Callable] = None,
    ) -> Dict[str, ExecutionResult]:
        """
        Execute tasks in topological order based on dependency graph.
        
        Args:
            task_graph: Task graph with dependencies
            progress_callback: Optional async callback(task_id, result) for progress updates
            
        Returns:
            Dictionary mapping task_id to ExecutionResult
        """
        # Validate graph
        is_valid, issues = task_graph.validate_dag()
        if not is_valid:
            raise ValueError(f"Invalid task graph: {'; '.join(issues)}")
        
        # Get topological order
        task_order = task_graph.topological_sort()
        
        self.logger.info(
            f"Executing task graph with {len(task_graph.tasks)} tasks "
            f"in topological order: {task_order}"
        )
        
        # Create task lookup
        task_lookup = {t.id: t for t in task_graph.tasks}
        
        # Convert PlanTask to TaskSchema
        task_schemas = {}
        for plan_task in task_graph.tasks:
            task_schemas[plan_task.id] = TaskSchema(
                task_id=plan_task.id,
                description=plan_task.description,
                input={"specification": plan_task.input},
                output=plan_task.output,
                dependencies=plan_task.dependencies,
                criticality=plan_task.criticality,
                estimated_lines=plan_task.estimated_lines,
                verification="Automated syntax and test verification",
            )
        
        # Execute in order
        results = {}
        
        for task_id in task_order:
            task = task_schemas[task_id]
            
            self.logger.info(f"Executing task {task_id} ({len(results)}/{len(task_order)} complete)")
            
            # Execute with retry
            result = await self.execute_with_retry(task)
            results[task_id] = result
            
            # Call progress callback
            if progress_callback:
                await progress_callback(task_id, result)
            
            # Stop if task failed or escalated
            if result.status in [TaskStatus.FAILED, TaskStatus.ESCALATED]:
                self.logger.warning(
                    f"Task {task_id} {result.status.value} - "
                    f"stopping graph execution"
                )
                
                # Mark remaining tasks as pending
                for remaining_id in task_order[task_order.index(task_id) + 1:]:
                    results[remaining_id] = ExecutionResult(
                        task_id=remaining_id,
                        status=TaskStatus.PENDING,
                        attempts=0,
                        total_time_seconds=0.0,
                    )
                
                break
        
        return results
    
    async def handle_escalation(
        self,
        task: TaskSchema,
        result: ExecutionResult,
    ) -> ExecutionResult:
        """
        Handle human escalation for a task.
        
        Args:
            task: Original task
            result: ExecutionResult requiring escalation
            
        Returns:
            Updated ExecutionResult with human decision
        """
        if not self.human_callback:
            self.logger.error("Human escalation needed but no callback provided")
            result.human_decision = "No human callback available"
            return result
        
        self.logger.info(f"Escalating task {task.task_id} to human")
        
        # Call human callback
        human_output = await self.human_callback(task, result)
        
        # Update result
        result.final_output = human_output
        result.human_decision = human_output
        result.status = TaskStatus.COMPLETED
        result.completed_at = datetime.now()
        
        return result
