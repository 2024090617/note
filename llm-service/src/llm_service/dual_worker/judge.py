"""
Judge implementation for evaluating worker outputs.

The judge compares two worker outputs and makes a decision on which to accept,
or whether to reject both and escalate to human.
"""

import json
import logging
from datetime import datetime
from typing import Optional

from llm_service.client import Message, MessageRole
from llm_service.dual_worker.async_client import AsyncLLMClient
from llm_service.dual_worker.config import ModelConfig
from llm_service.dual_worker.models import (
    TaskSchema,
    WorkerResponse,
    JudgeDecision,
    JudgeVerdict,
    JudgeCriteria,
)
from llm_service.dual_worker.prompts import JUDGE_EVALUATION_PROMPT

logger = logging.getLogger(__name__)


class Judge:
    """
    Judge that evaluates two worker outputs and makes decisions.
    
    Responsibilities:
    - Compare outputs using structured criteria
    - Score each output on multiple dimensions
    - Make verdict: ACCEPT_A, ACCEPT_B, REJECT_BOTH, or MERGE
    - Provide reasoning and recommendations
    """
    
    def __init__(self, model_config: ModelConfig):
        """
        Initialize judge.
        
        Args:
            model_config: Model configuration (e.g., Claude Opus 4.5 or Grok)
        """
        self.model_config = model_config
        self.client = AsyncLLMClient(model_config)
        self.logger = logging.getLogger(f"{__name__}.{model_config.model_name}")
    
    def _build_evaluation_prompt(
        self,
        task: TaskSchema,
        worker_a: WorkerResponse,
        worker_b: WorkerResponse,
    ) -> str:
        """
        Build evaluation prompt for judge.
        
        Args:
            task: Original task
            worker_a: Worker A's response
            worker_b: Worker B's response
            
        Returns:
            Formatted prompt
        """
        return JUDGE_EVALUATION_PROMPT.format(
            task_description=task.description,
            worker_a_model=worker_a.model_name,
            worker_a_strategy=worker_a.strategy.value,
            worker_a_output=worker_a.output,
            worker_b_model=worker_b.model_name,
            worker_b_strategy=worker_b.strategy.value,
            worker_b_output=worker_b.output,
        )
    
    def _parse_judge_response(self, content: str) -> dict:
        """
        Parse JSON response from judge.
        
        Args:
            content: Raw response content
            
        Returns:
            Parsed JSON dictionary
            
        Raises:
            ValueError: If parsing fails
        """
        # Try to extract JSON from markdown code blocks
        if "```json" in content:
            json_start = content.find("```json") + 7
            json_end = content.find("```", json_start)
            json_str = content[json_start:json_end].strip()
        elif "```" in content:
            json_start = content.find("```") + 3
            json_end = content.find("```", json_start)
            json_str = content[json_start:json_end].strip()
        else:
            # Assume entire content is JSON
            json_str = content.strip()
        
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse judge response as JSON: {str(e)}")
            self.logger.debug(f"Raw content: {content}")
            raise ValueError(f"Judge response is not valid JSON: {str(e)}")
    
    def _validate_and_normalize_verdict(self, verdict: str) -> JudgeVerdict:
        """
        Validate and normalize verdict string.
        
        Args:
            verdict: Verdict string from judge
            
        Returns:
            JudgeVerdict enum
            
        Raises:
            ValueError: If verdict is invalid
        """
        verdict_lower = verdict.lower().replace("_", "").replace("-", "")
        
        verdict_map = {
            "accepta": JudgeVerdict.ACCEPT_A,
            "acceptb": JudgeVerdict.ACCEPT_B,
            "rejectboth": JudgeVerdict.REJECT_BOTH,
            "merge": JudgeVerdict.MERGE,
        }
        
        for key, value in verdict_map.items():
            if key in verdict_lower:
                return value
        
        raise ValueError(f"Invalid verdict: {verdict}")
    
    async def evaluate(
        self,
        task: TaskSchema,
        worker_a_response: WorkerResponse,
        worker_b_response: WorkerResponse,
        auto_verify: bool = True,
    ) -> JudgeDecision:
        """
        Evaluate two worker outputs and make a decision.
        
        Args:
            task: Original task
            worker_a_response: Worker A's output
            worker_b_response: Worker B's output
            auto_verify: Run automated verification before judging
            
        Returns:
            JudgeDecision with verdict and analysis
            
        Raises:
            APIError: If evaluation fails
        """
        self.logger.info(
            f"Judge ({self.model_config.model_name}) evaluating task {task.task_id}"
        )
        
        start_time = datetime.now()
        
        # Build evaluation prompt
        prompt = self._build_evaluation_prompt(task, worker_a_response, worker_b_response)
        
        messages = [
            Message(
                role=MessageRole.SYSTEM,
                content="You are an expert code reviewer and technical judge. "
                        "Evaluate implementations objectively using the provided criteria."
            ),
            Message(role=MessageRole.USER, content=prompt),
        ]
        
        # Get judge's evaluation
        response = await self.client.execute_with_retry(
            messages,
            max_retries=2,
            retry_delay=5,
        )
        
        execution_time = (datetime.now() - start_time).total_seconds()
        
        # Parse response
        try:
            parsed = self._parse_judge_response(response.content)
        except ValueError as e:
            # Fallback: If judge can't produce valid JSON, reject both
            self.logger.error(f"Judge failed to produce valid response: {str(e)}")
            return JudgeDecision(
                verdict=JudgeVerdict.REJECT_BOTH,
                confidence=0.0,
                worker_a_scores=JudgeCriteria(
                    correctness=0, edge_cases=0, security=0,
                    code_quality=0, performance=0, completeness=0
                ),
                worker_b_scores=JudgeCriteria(
                    correctness=0, edge_cases=0, security=0,
                    code_quality=0, performance=0, completeness=0
                ),
                reasoning="Judge failed to produce valid evaluation",
                concerns=["Judge response parsing failed"],
                winner_justification="Unable to evaluate - rejecting both",
                recommendation="Review outputs manually and provide guidance",
                model_name=self.model_config.model_name,
                execution_time_seconds=execution_time,
            )
        
        # Extract and validate fields
        try:
            verdict = self._validate_and_normalize_verdict(parsed["verdict"])
            confidence = float(parsed["confidence"])
            
            worker_a_scores = JudgeCriteria(**parsed["worker_a_scores"])
            worker_b_scores = JudgeCriteria(**parsed["worker_b_scores"])
            
            reasoning = parsed.get("reasoning", "")
            concerns = parsed.get("concerns", [])
            winner_justification = parsed.get("winner_justification", "")
            recommendation = parsed.get("recommendation")
            merge_strategy = parsed.get("merge_strategy")
            
        except (KeyError, ValueError, TypeError) as e:
            self.logger.error(f"Judge response missing required fields: {str(e)}")
            # Fallback to rejection
            return JudgeDecision(
                verdict=JudgeVerdict.REJECT_BOTH,
                confidence=0.0,
                worker_a_scores=JudgeCriteria(
                    correctness=50, edge_cases=50, security=50,
                    code_quality=50, performance=50, completeness=50
                ),
                worker_b_scores=JudgeCriteria(
                    correctness=50, edge_cases=50, security=50,
                    code_quality=50, performance=50, completeness=50
                ),
                reasoning="Judge response incomplete",
                concerns=["Missing required evaluation fields"],
                winner_justification="Unable to complete evaluation",
                recommendation="Review outputs manually",
                model_name=self.model_config.model_name,
                execution_time_seconds=execution_time,
            )
        
        # Override based on automated verification if enabled
        if auto_verify:
            # Check syntax validity
            if worker_a_response.syntax_valid is False and worker_b_response.syntax_valid is False:
                verdict = JudgeVerdict.REJECT_BOTH
                concerns.append("Both outputs have syntax errors")
                recommendation = "Fix syntax errors and retry"
            elif worker_a_response.syntax_valid is False and worker_b_response.syntax_valid is True:
                verdict = JudgeVerdict.ACCEPT_B
                concerns.append("Worker A has syntax errors")
            elif worker_a_response.syntax_valid is True and worker_b_response.syntax_valid is False:
                verdict = JudgeVerdict.ACCEPT_A
                concerns.append("Worker B has syntax errors")
        
        decision = JudgeDecision(
            verdict=verdict,
            confidence=confidence,
            worker_a_scores=worker_a_scores,
            worker_b_scores=worker_b_scores,
            reasoning=reasoning,
            concerns=concerns,
            winner_justification=winner_justification,
            recommendation=recommendation,
            merge_strategy=merge_strategy,
            model_name=self.model_config.model_name,
            execution_time_seconds=execution_time,
        )
        
        self.logger.info(
            f"Judge decision: {verdict.value} (confidence: {confidence:.2f}, "
            f"scores: A={worker_a_scores.total:.1f} B={worker_b_scores.total:.1f})"
        )
        
        return decision
    
    def should_escalate(
        self,
        decision: JudgeDecision,
        auto_escalate_threshold: float = 0.6,
        rejection_threshold: float = 85.0,
    ) -> tuple[bool, Optional[str]]:
        """
        Determine if decision should be escalated to human.
        
        Args:
            decision: Judge's decision
            auto_escalate_threshold: Confidence threshold for auto-escalation
            rejection_threshold: Score threshold for acceptance
            
        Returns:
            Tuple of (should_escalate, reason)
        """
        # Always escalate rejections
        if decision.verdict == JudgeVerdict.REJECT_BOTH:
            return True, "Both outputs rejected by judge"
        
        # Escalate low confidence decisions
        if decision.confidence < auto_escalate_threshold:
            return True, f"Judge confidence too low: {decision.confidence:.2f}"
        
        # Escalate if winner score is below threshold
        if decision.verdict == JudgeVerdict.ACCEPT_A:
            if decision.worker_a_scores.total < rejection_threshold:
                return True, f"Winner score too low: {decision.worker_a_scores.total:.1f}"
        elif decision.verdict == JudgeVerdict.ACCEPT_B:
            if decision.worker_b_scores.total < rejection_threshold:
                return True, f"Winner score too low: {decision.worker_b_scores.total:.1f}"
        
        # Escalate if scores are very close (hard to decide)
        score_diff = abs(decision.worker_a_scores.total - decision.worker_b_scores.total)
        if score_diff < 5.0:
            return True, f"Scores too close to call: {score_diff:.1f} points difference"
        
        return False, None
