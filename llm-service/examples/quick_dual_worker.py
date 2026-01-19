"""
Quick example: Single task execution with dual workers

Shows the simplest usage of the framework for one-off tasks.
"""

import asyncio
from llm_service.dual_worker import (
    DualWorkerConfig,
    DualWorkerOrchestrator,
    TaskSchema,
    TaskCriticality,
)


async def main():
    # Create configuration (uses defaults based on available models)
    config = DualWorkerConfig.create_default()
    
    # Create orchestrator
    orchestrator = DualWorkerOrchestrator(config)
    
    # Define a task
    task = TaskSchema(
        task_id="DEMO-1",
        description="Write a Python function to validate email addresses using regex",
        input={
            "language": "Python",
            "requirements": [
                "Use re module",
                "Handle None/empty inputs",
                "Return True/False",
                "Include docstring"
            ]
        },
        output="A complete Python function with error handling",
        constraints=[
            "Must handle edge cases (None, empty string, invalid format)",
            "Include type hints",
            "Add comprehensive docstring"
        ],
        verification="Syntax check and basic validation",
        criticality=TaskCriticality.IMPORTANT,  # Uses dual workers + Grok judge
    )
    
    print(f"\n{'='*60}")
    print(f"Task: {task.description}")
    print(f"Criticality: {task.criticality.value}")
    print(f"{'='*60}\n")
    
    print("Executing with dual workers...")
    print(f"  Worker 1: {config.models[config.ModelRole.WORKER_PRAGMATIC].model_name} (pragmatic)")
    print(f"  Worker 2: {config.models[config.ModelRole.WORKER_REASONING].model_name} (security-first)")
    print(f"  Judge: {config.models[config.ModelRole.JUDGE_STANDARD].model_name}")
    print()
    
    # Execute with automatic retry on rejection
    result = await orchestrator.execute_with_retry(task)
    
    # Display results
    print(f"\n{'='*60}")
    print(f"Status: {result.status.value}")
    print(f"Attempts: {result.attempts}")
    print(f"Total Time: {result.total_time_seconds:.2f}s")
    
    if result.judge_decision:
        print(f"\nJudge Decision:")
        print(f"  Verdict: {result.judge_decision.verdict.value}")
        print(f"  Confidence: {result.judge_decision.confidence:.2f}")
        print(f"  Worker A Score: {result.judge_decision.worker_a_scores.total:.1f}/100")
        print(f"  Worker B Score: {result.judge_decision.worker_b_scores.total:.1f}/100")
    
    if result.final_output:
        print(f"\n{'='*60}")
        print("Final Output:")
        print(f"{'='*60}")
        print(result.final_output)
        print(f"{'='*60}\n")
    
    if result.escalated:
        print(f"\n⚠️  Task was escalated: {result.escalation_reason}")


if __name__ == "__main__":
    asyncio.run(main())
