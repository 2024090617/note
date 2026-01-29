"""
Worker implementation for task execution.

Workers execute atomic tasks using specific strategies and models.
Supports both code generation and common tasks (writing, analysis, planning, etc.)
"""

import logging
from datetime import datetime
from typing import Optional

from llm_service.client import Message, MessageRole
from llm_service.dual_worker.async_client import AsyncLLMClient
from llm_service.dual_worker.config import ModelConfig
from llm_service.dual_worker.models import (
    TaskSchema,
    TaskType,
    WorkerResponse,
    WorkerStrategy,
)
from llm_service.dual_worker.prompts import (
    WORKER_PRAGMATIC_PROMPT,
    WORKER_SECURITY_FIRST_PROMPT,
    WORKER_PERFORMANCE_FIRST_PROMPT,
    WORKER_COMPREHENSIVE_PROMPT,
    WORKER_RETRY_PROMPT,
    get_worker_prompt,
)

logger = logging.getLogger(__name__)


class Worker:
    """
    Worker that executes tasks using a specific model and strategy.
    
    Each worker has:
    - A strategy (pragmatic, security-first, performance-first, comprehensive)
    - A model configuration (GPT-4.1, GPT-5 mini, etc.)
    - An execution approach optimized for that strategy
    """
    
    def __init__(
        self,
        worker_id: str,
        model_config: ModelConfig,
        strategy: WorkerStrategy,
    ):
        """
        Initialize worker.
        
        Args:
            worker_id: Unique identifier (e.g., "worker_1", "worker_2")
            model_config: Model configuration
            strategy: Execution strategy
        """
        self.worker_id = worker_id
        self.model_config = model_config
        self.strategy = strategy
        self.client = AsyncLLMClient(model_config)
        self.logger = logging.getLogger(f"{__name__}.{worker_id}")
    
    def _get_prompt_template(self, task: TaskSchema, is_retry: bool = False) -> str:
        """Get prompt template based on task type and strategy"""
        if is_retry:
            return WORKER_RETRY_PROMPT
        
        # Use task-type-aware prompt selector
        task_type = task.task_type.value if hasattr(task, 'task_type') else "code"
        strategy = self.strategy.value
        
        return get_worker_prompt(task_type, strategy)
    
    def _format_task_input(self, task: TaskSchema) -> str:
        """Format task input as readable text"""
        if not task.input:
            return "No specific input provided"
        
        lines = []
        for key, value in task.input.items():
            lines.append(f"- {key}: {value}")
        
        return "\n".join(lines) if lines else "No specific input provided"
    
    def _format_constraints(self, task: TaskSchema) -> str:
        """Format task constraints as readable text"""
        if not task.constraints:
            return "No specific constraints"
        
        return "\n".join(f"- {constraint}" for constraint in task.constraints)
    
    def _build_messages(
        self,
        task: TaskSchema,
        retry_feedback: Optional[dict] = None
    ) -> list[Message]:
        """
        Build message list for LLM.
        
        Args:
            task: Task to execute
            retry_feedback: Optional feedback from previous attempt
            
        Returns:
            List of messages
        """
        # System message defines the worker's role based on task type
        task_type = task.task_type.value if hasattr(task, 'task_type') else "code"
        
        role_descriptions = {
            "code": "a skilled software developer",
            "writing": "a professional technical writer",
            "analysis": "an expert analyst",
            "planning": "a strategic project planner",
            "qa": "a knowledgeable expert",
            "translation": "a skilled translator",
            "creative": "a creative content creator",
            "review": "a thorough reviewer",
            "general": "a capable assistant",
        }
        role = role_descriptions.get(task_type, "a capable assistant")
        
        system_content = f"You are {role} executing tasks with a {self.strategy.value} approach."
        
        # User message contains the task
        if retry_feedback:
            # Retry with feedback
            user_content = WORKER_RETRY_PROMPT.format(
                task_description=task.description,
                task_input=self._format_task_input(task),
                task_constraints=self._format_constraints(task),
                task_output=task.output,
                judge_concerns="\n".join(f"- {c}" for c in retry_feedback.get("concerns", [])),
                judge_recommendation=retry_feedback.get("recommendation", "Address the concerns above"),
            )
        else:
            # First attempt - use task-type-aware template
            template = self._get_prompt_template(task)
            
            # Build format kwargs based on task type
            format_kwargs = {
                "task_description": task.description,
                "task_input": self._format_task_input(task),
                "task_constraints": self._format_constraints(task),
                "task_output": task.output,
            }
            
            # Add optional fields for non-code tasks
            if hasattr(task, 'audience') and task.audience:
                format_kwargs["audience"] = task.audience
            else:
                format_kwargs["audience"] = "general audience"
            
            if hasattr(task, 'tone') and task.tone:
                format_kwargs["tone"] = task.tone
            else:
                format_kwargs["tone"] = "professional"
            
            user_content = template.format(**format_kwargs)
        
        return [
            Message(role=MessageRole.SYSTEM, content=system_content),
            Message(role=MessageRole.USER, content=user_content),
        ]
    
    async def execute(
        self,
        task: TaskSchema,
        retry_feedback: Optional[dict] = None,
    ) -> WorkerResponse:
        """
        Execute a task.
        
        Args:
            task: Task to execute
            retry_feedback: Optional feedback from judge for retry
            
        Returns:
            WorkerResponse with output and metadata
            
        Raises:
            APIError: If execution fails
        """
        self.logger.info(
            f"Worker {self.worker_id} ({self.model_config.model_name}) "
            f"executing task {task.task_id} with strategy {self.strategy.value}"
        )
        
        start_time = datetime.now()
        
        # Build messages
        messages = self._build_messages(task, retry_feedback)
        
        # Execute
        response = await self.client.execute_with_retry(
            messages,
            max_retries=2,
            retry_delay=5,
        )
        
        execution_time = (datetime.now() - start_time).total_seconds()
        
        # Extract token usage if available
        tokens_used = None
        if response.usage:
            tokens_used = response.usage.get("total_tokens")
        
        worker_response = WorkerResponse(
            worker_id=self.worker_id,
            model_name=self.model_config.model_name,
            strategy=self.strategy,
            output=response.content,
            reasoning=None,  # Some models provide reasoning separately
            execution_time_seconds=execution_time,
            tokens_used=tokens_used,
        )
        
        self.logger.info(
            f"Worker {self.worker_id} completed task {task.task_id} in {execution_time:.2f}s"
        )
        
        return worker_response
    
    async def verify_output(self, output: str, task: TaskSchema) -> dict:
        """
        Run automated verification on output.
        
        Args:
            output: Generated output
            task: Original task
            
        Returns:
            Dictionary with verification results
        """
        results = {
            "syntax_valid": None,
            "tests_passed": None,
            "linter_score": None,
        }
        
        # Syntax check (for code outputs)
        if "```python" in output or "def " in output or "class " in output:
            try:
                # Extract code blocks
                code_blocks = []
                if "```python" in output:
                    parts = output.split("```python")
                    for part in parts[1:]:
                        code = part.split("```")[0].strip()
                        code_blocks.append(code)
                else:
                    # Assume entire output is code
                    code_blocks.append(output)
                
                # Try to compile each block
                all_valid = True
                for code in code_blocks:
                    try:
                        compile(code, "<string>", "exec")
                    except SyntaxError:
                        all_valid = False
                        break
                
                results["syntax_valid"] = all_valid
                
            except Exception as e:
                self.logger.warning(f"Syntax validation failed: {str(e)}")
                results["syntax_valid"] = False
        
        # TODO: Run actual tests if test framework available
        # TODO: Run linter if available
        
        return results


def get_worker_strategies_for_task_type(task_type: TaskType) -> tuple[WorkerStrategy, WorkerStrategy]:
    """
    Get appropriate worker strategies based on task type.
    
    Different task types benefit from different evaluation perspectives:
    - Code tasks: pragmatic vs security_first (focuses on edge cases, vulnerabilities)
    - Writing/Creative: pragmatic vs comprehensive (focuses on depth, polish)
    - Analysis/Planning: pragmatic vs comprehensive (focuses on thoroughness)
    - QA/Review: pragmatic vs security_first (focuses on finding issues)
    
    Args:
        task_type: The type of task being executed
        
    Returns:
        Tuple of (worker_1_strategy, worker_2_strategy)
    """
    # Code and review tasks benefit from security-focused second opinion
    code_like_tasks = {TaskType.CODE, TaskType.REVIEW, TaskType.QA}
    
    if task_type in code_like_tasks:
        return WorkerStrategy.PRAGMATIC, WorkerStrategy.SECURITY_FIRST
    else:
        # Writing, analysis, planning, translation, creative, general
        # Benefit from comprehensive second opinion
        return WorkerStrategy.PRAGMATIC, WorkerStrategy.COMPREHENSIVE


def create_dual_workers(
    pragmatic_config: ModelConfig,
    reasoning_config: ModelConfig,
    task_type: TaskType = TaskType.CODE,
) -> tuple["Worker", "Worker"]:
    """
    Create two workers with complementary strategies based on task type.
    
    Args:
        pragmatic_config: Config for pragmatic worker
        reasoning_config: Config for reasoning worker
        task_type: Type of task to determine strategy selection
        
    Returns:
        Tuple of (worker_1, worker_2)
    """
    strategy_1, strategy_2 = get_worker_strategies_for_task_type(task_type)
    
    worker_1 = Worker(
        worker_id="worker_1",
        model_config=pragmatic_config,
        strategy=strategy_1,
    )
    
    worker_2 = Worker(
        worker_id="worker_2",
        model_config=reasoning_config,
        strategy=strategy_2,
    )
    
    logger.info(
        f"Created workers for task_type={task_type.value}: "
        f"worker_1={strategy_1.value}, worker_2={strategy_2.value}"
    )
    
    return worker_1, worker_2
