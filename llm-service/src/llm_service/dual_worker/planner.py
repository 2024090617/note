"""
Planning module for dual-planner workflow.

Implements task decomposition using two planners with different strategies
and a judge to evaluate and merge plans.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any

from llm_service.client import Message, MessageRole
from llm_service.dual_worker.async_client import AsyncLLMClient
from llm_service.dual_worker.config import DualWorkerConfig, ModelRole
from llm_service.dual_worker.models import (
    PlanTask,
    TaskGraph,
    PlanComparison,
    TaskCriticality,
)
from llm_service.dual_worker.prompts import (
    PLANNER_PRAGMATIC_PROMPT,
    PLANNER_COMPREHENSIVE_PROMPT,
    JUDGE_PLANNING_PROMPT,
)

logger = logging.getLogger(__name__)


class Planner:
    """
    Planner that decomposes goals into atomic tasks.
    
    Two strategies:
    - Pragmatic: Focused on actionable, practical tasks
    - Comprehensive: Deep reasoning, edge cases, completeness
    """
    
    def __init__(self, model_config, strategy: str = "pragmatic"):
        """
        Initialize planner.
        
        Args:
            model_config: Model configuration
            strategy: "pragmatic" or "comprehensive"
        """
        self.model_config = model_config
        self.strategy = strategy
        self.client = AsyncLLMClient(model_config)
        self.logger = logging.getLogger(f"{__name__}.{strategy}")
    
    def _get_prompt_template(self) -> str:
        """Get prompt template based on strategy"""
        if self.strategy == "comprehensive":
            return PLANNER_COMPREHENSIVE_PROMPT
        else:
            return PLANNER_PRAGMATIC_PROMPT
    
    async def create_plan(
        self,
        user_goal: str,
        additional_context: Optional[str] = None,
    ) -> TaskGraph:
        """
        Create task decomposition plan.
        
        Args:
            user_goal: High-level goal to decompose
            additional_context: Optional additional requirements/feedback
            
        Returns:
            TaskGraph with tasks and dependencies
            
        Raises:
            ValueError: If plan parsing fails
        """
        self.logger.info(f"Creating {self.strategy} plan for goal: {user_goal[:100]}...")
        
        start_time = datetime.now()
        
        # Build prompt
        prompt_template = self._get_prompt_template()
        
        full_goal = user_goal
        if additional_context:
            full_goal = f"{user_goal}\n\nAdditional context:\n{additional_context}"
        
        prompt = prompt_template.format(user_goal=full_goal)
        
        messages = [
            Message(
                role=MessageRole.SYSTEM,
                content=f"You are a {self.strategy} task planner. "
                        "Decompose goals into atomic, executable tasks."
            ),
            Message(role=MessageRole.USER, content=prompt),
        ]
        
        # Get plan
        response = await self.client.execute_with_retry(messages, max_retries=2)
        
        execution_time = (datetime.now() - start_time).total_seconds()
        
        # Parse JSON response
        try:
            plan_data = self._parse_plan_response(response.content)
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            self.logger.error(f"Failed to parse plan: {str(e)}")
            raise ValueError(f"Planner failed to produce valid plan: {str(e)}")
        
        # Convert to TaskGraph
        tasks = []
        for task_data in plan_data.get("tasks", []):
            # Normalize criticality
            criticality_str = task_data.get("criticality", "standard")
            try:
                criticality = TaskCriticality(criticality_str.lower())
            except ValueError:
                criticality = TaskCriticality.STANDARD
            
            tasks.append(PlanTask(
                id=task_data["id"],
                description=task_data["description"],
                input=task_data.get("input", ""),
                output=task_data.get("output", ""),
                estimated_lines=task_data.get("estimated_lines", 50),
                dependencies=task_data.get("dependencies", []),
                criticality=criticality,
            ))
        
        edges = [tuple(edge) for edge in plan_data.get("edges", [])]
        
        task_graph = TaskGraph(tasks=tasks, edges=edges)
        
        self.logger.info(
            f"Created {self.strategy} plan with {len(tasks)} tasks "
            f"in {execution_time:.2f}s"
        )
        
        return task_graph
    
    def _parse_plan_response(self, content: str) -> Dict[str, Any]:
        """Parse JSON plan from response"""
        # Extract JSON from markdown blocks
        if "```json" in content:
            json_start = content.find("```json") + 7
            json_end = content.find("```", json_start)
            json_str = content[json_start:json_end].strip()
        elif "```" in content:
            json_start = content.find("```") + 3
            json_end = content.find("```", json_start)
            json_str = content[json_start:json_end].strip()
        else:
            json_str = content.strip()
        
        return json.loads(json_str)


class PlanningJudge:
    """
    Judge that evaluates and merges planning outputs.
    """
    
    def __init__(self, model_config):
        """
        Initialize planning judge.
        
        Args:
            model_config: Model configuration (premium judge recommended)
        """
        self.model_config = model_config
        self.client = AsyncLLMClient(model_config)
        self.logger = logging.getLogger(__name__)
    
    async def evaluate_plans(
        self,
        user_goal: str,
        plan_a: TaskGraph,
        plan_b: TaskGraph,
        planner_a_model: str,
        planner_b_model: str,
    ) -> Dict[str, Any]:
        """
        Evaluate two plans and decide which to use or how to merge.
        
        Args:
            user_goal: Original goal
            plan_a: First plan (pragmatic)
            plan_b: Second plan (comprehensive)
            planner_a_model: Model name for planner A
            planner_b_model: Model name for planner B
            
        Returns:
            Dictionary with verdict, scores, and merge strategy
        """
        self.logger.info("Evaluating two planning approaches")
        
        start_time = datetime.now()
        
        # Prepare plans as JSON for comparison
        plan_a_json = json.dumps({
            "tasks": [
                {
                    "id": t.id,
                    "description": t.description,
                    "input": t.input,
                    "output": t.output,
                    "estimated_lines": t.estimated_lines,
                    "dependencies": t.dependencies,
                    "criticality": t.criticality.value,
                }
                for t in plan_a.tasks
            ],
            "edges": plan_a.edges,
        }, indent=2)
        
        plan_b_json = json.dumps({
            "tasks": [
                {
                    "id": t.id,
                    "description": t.description,
                    "input": t.input,
                    "output": t.output,
                    "estimated_lines": t.estimated_lines,
                    "dependencies": t.dependencies,
                    "criticality": t.criticality.value,
                }
                for t in plan_b.tasks
            ],
            "edges": plan_b.edges,
        }, indent=2)
        
        # Build evaluation prompt
        prompt = JUDGE_PLANNING_PROMPT.format(
            user_goal=user_goal,
            planner_a_model=planner_a_model,
            planner_b_model=planner_b_model,
            plan_a_json=plan_a_json,
            plan_b_json=plan_b_json,
        )
        
        messages = [
            Message(
                role=MessageRole.SYSTEM,
                content="You are an expert at evaluating software development plans. "
                        "Compare plans objectively using structured criteria."
            ),
            Message(role=MessageRole.USER, content=prompt),
        ]
        
        # Get evaluation
        response = await self.client.execute_with_retry(messages, max_retries=2)
        
        execution_time = (datetime.now() - start_time).total_seconds()
        
        # Parse response
        try:
            evaluation = self._parse_judge_response(response.content)
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            self.logger.error(f"Failed to parse judge evaluation: {str(e)}")
            # Return default: reject both for safety
            return {
                "verdict": "REJECT_BOTH",
                "confidence": 0.0,
                "plan_a_score": 50.0,
                "plan_b_score": 50.0,
                "recommendation": "Judge failed to evaluate - review plans manually",
            }
        
        self.logger.info(
            f"Planning judge decision: {evaluation.get('verdict')} "
            f"(A: {evaluation.get('plan_a_score')}%, B: {evaluation.get('plan_b_score')}%)"
        )
        
        return evaluation
    
    def _parse_judge_response(self, content: str) -> Dict[str, Any]:
        """Parse JSON evaluation from response"""
        # Extract JSON from markdown blocks
        if "```json" in content:
            json_start = content.find("```json") + 7
            json_end = content.find("```", json_start)
            json_str = content[json_start:json_end].strip()
        elif "```" in content:
            json_start = content.find("```") + 3
            json_end = content.find("```", json_start)
            json_str = content[json_start:json_end].strip()
        else:
            json_str = content.strip()
        
        return json.loads(json_str)
    
    def merge_plans(
        self,
        plan_a: TaskGraph,
        plan_b: TaskGraph,
        merge_strategy: Dict[str, Any],
    ) -> TaskGraph:
        """
        Merge two plans based on judge's strategy.
        
        Args:
            plan_a: First plan
            plan_b: Second plan
            merge_strategy: Judge's merge instructions
            
        Returns:
            Merged TaskGraph
        """
        self.logger.info("Merging plans based on judge strategy")
        
        take_from_a = set(merge_strategy.get("take_from_a", []))
        take_from_b = set(merge_strategy.get("take_from_b", []))
        
        # Build task lookup
        tasks_a = {t.id: t for t in plan_a.tasks}
        tasks_b = {t.id: t for t in plan_b.tasks}
        
        # Collect merged tasks
        merged_tasks = []
        
        for task_id in take_from_a:
            if task_id in tasks_a:
                merged_tasks.append(tasks_a[task_id])
        
        for task_id in take_from_b:
            if task_id in tasks_b:
                merged_tasks.append(tasks_b[task_id])
        
        # Rebuild edges based on merged tasks
        merged_task_ids = {t.id for t in merged_tasks}
        merged_edges = []
        
        # Include edges from both plans if both nodes are in merged set
        for from_id, to_id in plan_a.edges:
            if from_id in merged_task_ids and to_id in merged_task_ids:
                merged_edges.append((from_id, to_id))
        
        for from_id, to_id in plan_b.edges:
            edge = (from_id, to_id)
            if (from_id in merged_task_ids and
                to_id in merged_task_ids and
                edge not in merged_edges):
                merged_edges.append(edge)
        
        merged_graph = TaskGraph(tasks=merged_tasks, edges=merged_edges)
        
        self.logger.info(f"Merged plan has {len(merged_tasks)} tasks")
        
        return merged_graph


class DualPlannerOrchestrator:
    """
    Orchestrates dual-planner workflow with judge evaluation.
    """
    
    def __init__(self, config: Optional[DualWorkerConfig] = None):
        """
        Initialize dual-planner orchestrator.
        
        Args:
            config: Configuration (uses defaults if not provided)
        """
        self.config = config or DualWorkerConfig.create_default()
        
        # Create planners
        pragmatic_config, comprehensive_config = self.config.get_planner_configs()
        
        self.planner_pragmatic = Planner(pragmatic_config, strategy="pragmatic")
        self.planner_comprehensive = Planner(comprehensive_config, strategy="comprehensive")
        
        # Create judge (use premium for planning)
        judge_config = self.config.models[ModelRole.JUDGE_PREMIUM]
        self.judge = PlanningJudge(judge_config)
        
        self.logger = logging.getLogger(__name__)
    
    async def create_validated_plan(
        self,
        user_goal: str,
        max_retries: int = 2,
    ) -> tuple[TaskGraph, Dict[str, Any]]:
        """
        Create and validate task decomposition plan using dual planners.
        
        Args:
            user_goal: High-level goal to decompose
            max_retries: Maximum retry attempts
            
        Returns:
            Tuple of (final_plan, metadata)
            
        Raises:
            ValueError: If planning fails after retries
        """
        additional_context = None
        
        for attempt in range(max_retries + 1):
            self.logger.info(f"Planning attempt {attempt + 1}/{max_retries + 1}")
            
            # Create two plans in parallel
            plan_a_task = self.planner_pragmatic.create_plan(user_goal, additional_context)
            plan_b_task = self.planner_comprehensive.create_plan(user_goal, additional_context)
            
            plan_a, plan_b = await asyncio.gather(plan_a_task, plan_b_task)
            
            # Validate DAGs
            valid_a, issues_a = plan_a.validate_dag()
            valid_b, issues_b = plan_b.validate_dag()
            
            if not valid_a and not valid_b:
                self.logger.warning("Both plans have invalid DAGs, retrying...")
                additional_context = (
                    f"Previous attempts had these DAG issues:\n"
                    f"Plan A: {'; '.join(issues_a)}\n"
                    f"Plan B: {'; '.join(issues_b)}\n"
                    f"Ensure the new plan has no cycles and all references are valid."
                )
                continue
            
            # Judge evaluation
            evaluation = await self.judge.evaluate_plans(
                user_goal,
                plan_a,
                plan_b,
                self.planner_pragmatic.model_config.model_name,
                self.planner_comprehensive.model_config.model_name,
            )
            
            verdict = evaluation.get("verdict", "").upper()
            
            # Process verdict
            if verdict == "ACCEPT_A":
                if valid_a:
                    return plan_a, {
                        "verdict": "ACCEPT_A",
                        "plan_a_score": evaluation.get("plan_a_score"),
                        "plan_b_score": evaluation.get("plan_b_score"),
                        "attempts": attempt + 1,
                    }
                else:
                    # Plan A chosen but invalid, try B
                    verdict = "ACCEPT_B"
            
            if verdict == "ACCEPT_B":
                if valid_b:
                    return plan_b, {
                        "verdict": "ACCEPT_B",
                        "plan_a_score": evaluation.get("plan_a_score"),
                        "plan_b_score": evaluation.get("plan_b_score"),
                        "attempts": attempt + 1,
                    }
                else:
                    # Plan B chosen but invalid
                    if valid_a:
                        return plan_a, {"verdict": "ACCEPT_A (fallback)", "attempts": attempt + 1}
            
            elif verdict == "MERGE":
                merge_strategy = evaluation.get("merge_strategy", {})
                try:
                    merged_plan = self.judge.merge_plans(plan_a, plan_b, merge_strategy)
                    
                    # Validate merged plan
                    valid_merged, issues_merged = merged_plan.validate_dag()
                    if valid_merged:
                        return merged_plan, {
                            "verdict": "MERGE",
                            "merge_strategy": merge_strategy,
                            "attempts": attempt + 1,
                        }
                    else:
                        self.logger.warning(f"Merged plan invalid: {issues_merged}")
                except Exception as e:
                    self.logger.error(f"Merge failed: {str(e)}")
            
            # REJECT_BOTH or failed merge - retry with feedback
            if attempt < max_retries:
                additional_context = evaluation.get("recommendation", "")
                if evaluation.get("missing_tasks"):
                    additional_context += f"\n\nMissing tasks: {', '.join(evaluation['missing_tasks'])}"
                if evaluation.get("dependency_issues"):
                    additional_context += f"\n\nFix dependencies: {', '.join(evaluation['dependency_issues'])}"
        
        # All attempts failed
        raise ValueError(
            f"Failed to create valid plan after {max_retries + 1} attempts. "
            "Please provide more specific requirements."
        )
