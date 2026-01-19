"""
Demo: Complete workflow with dual-worker+judge framework

Demonstrates:
1. Creating a plan with dual planners
2. Executing the plan with dual workers
3. Saving results and generating reports
"""

import asyncio
import logging
from pathlib import Path

from llm_service.dual_worker import DualWorkerConfig
from llm_service.dual_worker.planner import DualPlannerOrchestrator
from llm_service.dual_worker.orchestrator import DualWorkerOrchestrator
from llm_service.dual_worker.storage import create_state_store
from llm_service.dual_worker.models import TaskStatus

# Enable logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def human_escalation_handler(task, result):
    """
    Handle human escalation (for demo, auto-select based on scores)
    
    In production, this would prompt the human for input
    """
    logger.info(f"\n{'='*60}")
    logger.info(f"🚨 HUMAN ESCALATION NEEDED")
    logger.info(f"Task: {task.task_id} - {task.description}")
    logger.info(f"Reason: {result.escalation_reason}")
    
    if result.judge_decision:
        logger.info(f"\nJudge Scores:")
        logger.info(f"  Worker A: {result.judge_decision.worker_a_scores.total:.1f}")
        logger.info(f"  Worker B: {result.judge_decision.worker_b_scores.total:.1f}")
        logger.info(f"  Confidence: {result.judge_decision.confidence:.2f}")
        
        logger.info(f"\nJudge Concerns:")
        for concern in result.judge_decision.concerns:
            logger.info(f"  - {concern}")
        
        # Auto-select higher-scored output for demo
        if result.judge_decision.worker_a_scores.total >= result.judge_decision.worker_b_scores.total:
            logger.info(f"\n✓ Auto-selecting Worker A (higher score)")
            return result.worker_a_response.output if result.worker_a_response else None
        else:
            logger.info(f"\n✓ Auto-selecting Worker B (higher score)")
            return result.worker_b_response.output if result.worker_b_response else None
    
    logger.info(f"{'='*60}\n")
    
    # Fallback
    return result.final_output or "Manual implementation needed"


async def progress_tracker(task_id: str, result):
    """Track execution progress"""
    status_emoji = {
        TaskStatus.COMPLETED: "✅",
        TaskStatus.FAILED: "❌",
        TaskStatus.ESCALATED: "⚠️",
        TaskStatus.REJECTED: "🚫",
    }
    
    emoji = status_emoji.get(result.status, "❓")
    logger.info(
        f"{emoji} Task {task_id}: {result.status.value} "
        f"({result.total_time_seconds:.2f}s, {result.attempts} attempts)"
    )
    
    if result.judge_decision:
        logger.info(
            f"   Judge: {result.judge_decision.verdict.value} "
            f"(confidence: {result.judge_decision.confidence:.2f})"
        )


async def main():
    """Main demo workflow"""
    
    # Goal for demonstration
    goal = """
    Create a simple REST API endpoint for user registration with these requirements:
    - Accept email and password
    - Validate email format
    - Hash password with bcrypt
    - Return success/error response
    - Include basic error handling
    """
    
    session_id = "demo_001"
    
    logger.info("="*60)
    logger.info("Dual-Worker+Judge Framework Demo")
    logger.info("="*60)
    
    # Step 1: Create configuration
    logger.info("\n📋 Step 1: Loading configuration...")
    config = DualWorkerConfig.create_default()
    
    logger.info("Configuration:")
    logger.info(f"  Worker 1: {config.models[config.ModelRole.WORKER_PRAGMATIC].model_name}")
    logger.info(f"  Worker 2: {config.models[config.ModelRole.WORKER_REASONING].model_name}")
    logger.info(f"  Standard Judge: {config.models[config.ModelRole.JUDGE_STANDARD].model_name}")
    logger.info(f"  Premium Judge: {config.models[config.ModelRole.JUDGE_PREMIUM].model_name}")
    logger.info(f"  Max Retries: {config.max_retries}")
    logger.info(f"  Auto Escalate Threshold: {config.auto_escalate_threshold}")
    
    # Step 2: Create plan with dual planners
    logger.info("\n📝 Step 2: Creating task plan with dual planners...")
    planner = DualPlannerOrchestrator(config)
    
    try:
        task_graph, metadata = await planner.create_validated_plan(goal, max_retries=2)
        
        logger.info(f"\n✅ Plan created successfully!")
        logger.info(f"  Verdict: {metadata.get('verdict')}")
        logger.info(f"  Plan A Score: {metadata.get('plan_a_score', 'N/A')}")
        logger.info(f"  Plan B Score: {metadata.get('plan_b_score', 'N/A')}")
        logger.info(f"  Total Tasks: {len(task_graph.tasks)}")
        
        logger.info(f"\nTask Breakdown:")
        for i, task in enumerate(task_graph.tasks, 1):
            deps = f" (depends on: {', '.join(task.dependencies)})" if task.dependencies else ""
            logger.info(f"  {i}. {task.id}: {task.description}{deps}")
        
    except Exception as e:
        logger.error(f"❌ Planning failed: {str(e)}")
        return
    
    # Step 3: Save plan
    logger.info("\n💾 Step 3: Saving plan...")
    store = create_state_store()
    plan_path = store.save_task_graph(task_graph, goal, metadata)
    logger.info(f"  Saved to: {plan_path}")
    
    # Step 4: Execute plan
    logger.info("\n🚀 Step 4: Executing plan with dual workers...")
    orchestrator = DualWorkerOrchestrator(config, human_callback=human_escalation_handler)
    
    try:
        results = await orchestrator.execute_graph(
            task_graph,
            progress_callback=progress_tracker,
        )
        
        logger.info(f"\n✅ Execution complete!")
        
    except Exception as e:
        logger.error(f"❌ Execution failed: {str(e)}")
        return
    
    # Step 5: Analyze results
    logger.info("\n📊 Step 5: Analyzing results...")
    
    completed = sum(1 for r in results.values() if r.status == TaskStatus.COMPLETED)
    failed = sum(1 for r in results.values() if r.status == TaskStatus.FAILED)
    escalated = sum(1 for r in results.values() if r.escalated)
    
    total_time = sum(r.total_time_seconds for r in results.values())
    total_attempts = sum(r.attempts for r in results.values())
    
    logger.info(f"\nExecution Summary:")
    logger.info(f"  ✅ Completed: {completed}/{len(results)}")
    logger.info(f"  ❌ Failed: {failed}/{len(results)}")
    logger.info(f"  ⚠️  Escalated: {escalated}/{len(results)}")
    logger.info(f"  ⏱️  Total Time: {total_time:.2f}s")
    logger.info(f"  🔄 Total Attempts: {total_attempts}")
    logger.info(f"  📈 Avg Time/Task: {total_time/len(results):.2f}s")
    
    # Step 6: Save results
    logger.info("\n💾 Step 6: Saving results...")
    
    # Save individual results
    for result in results.values():
        store.save_execution_result(result, session_id)
    
    # Create summary
    result_list = list(results.values())
    summary_path = store.create_session_summary(session_id, result_list, task_graph, goal)
    logger.info(f"  Summary: {summary_path}")
    
    # Export markdown report
    md_path = store.export_to_markdown(session_id, result_list, task_graph, goal)
    logger.info(f"  Report: {md_path}")
    
    # Step 7: Display sample output
    logger.info("\n📄 Step 7: Sample output from first completed task...")
    
    for task_id, result in results.items():
        if result.status == TaskStatus.COMPLETED and result.final_output:
            logger.info(f"\nTask {task_id}:")
            logger.info(f"{'='*60}")
            
            # Show first 500 chars of output
            output_preview = result.final_output[:500]
            if len(result.final_output) > 500:
                output_preview += "\n... (truncated)"
            
            logger.info(output_preview)
            logger.info(f"{'='*60}")
            break
    
    logger.info("\n" + "="*60)
    logger.info("Demo completed! 🎉")
    logger.info("="*60)
    logger.info(f"\nResults saved to: {store.storage_dir}")
    logger.info(f"View the full report at: {md_path}")


if __name__ == "__main__":
    print("\n" + "="*60)
    print("Dual-Worker+Judge Framework - Complete Demo")
    print("="*60)
    print("\nThis demo will:")
    print("1. Create a task plan using dual planners (GPT-4.1 + GPT-5 mini)")
    print("2. Have a judge (Claude Opus) evaluate and merge the plans")
    print("3. Execute tasks with dual workers in parallel")
    print("4. Judge outputs and retry with feedback if needed")
    print("5. Save all results, traces, and generate a markdown report")
    print("\nPress Ctrl+C to cancel, or wait 3 seconds to continue...")
    print("="*60 + "\n")
    
    try:
        import time
        time.sleep(3)
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nDemo cancelled by user.")
    except Exception as e:
        print(f"\n\n❌ Demo failed: {str(e)}")
        import traceback
        traceback.print_exc()
