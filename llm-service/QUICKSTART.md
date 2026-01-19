# Quick Start Guide - Dual-Worker+Judge Framework

## 5-Minute Setup

### 1. Prerequisites

Ensure you have:
- Python 3.9+ installed
- GitHub Copilot subscription (for unlimited model access)
- GitHub token with appropriate permissions

### 2. Set Up Authentication

```bash
export GITHUB_TOKEN="ghp_your_github_token_here"
```

To get your GitHub token:
1. Go to https://github.com/settings/tokens
2. Generate a new token with appropriate scopes
3. Copy and export it as shown above

### 3. Install Dependencies

The framework uses existing llm-service dependencies. If needed:

```bash
cd llm-service
pip install -e .
```

### 4. Verify Installation

```bash
python -m llm_service.dual_worker.cli config
```

You should see model assignments and configuration.

## Your First Task

### Option A: Quick Single Task

```bash
python -m llm_service.dual_worker.cli quick \
  "Write a Python function to validate email addresses with regex"
```

This will:
- Execute with dual workers (GPT-4.1 + GPT-5 mini)
- Judge outputs with Grok
- Show results in ~60 seconds

### Option B: Complete Planning Workflow

```bash
python -m llm_service.dual_worker.cli plan \
  "Build a REST API endpoint for user registration" \
  --execute
```

This will:
1. Create two plans (pragmatic + comprehensive)
2. Judge evaluates and merges them
3. Execute all tasks in the plan
4. Save results and generate report

### Option C: Programmatic Usage

Create a file `test_dual_worker.py`:

```python
import asyncio
from llm_service.dual_worker import (
    DualWorkerConfig,
    DualWorkerOrchestrator,
    TaskSchema,
    TaskCriticality,
)

async def main():
    config = DualWorkerConfig.create_default()
    orchestrator = DualWorkerOrchestrator(config)
    
    task = TaskSchema(
        task_id="TEST-1",
        description="Create a function to hash passwords with bcrypt",
        input={"language": "Python"},
        output="Complete function with error handling",
        verification="Syntax check",
        criticality=TaskCriticality.IMPORTANT,
    )
    
    result = await orchestrator.execute_with_retry(task)
    
    print(f"Status: {result.status.value}")
    print(f"Output:\n{result.final_output}")

asyncio.run(main())
```

Run it:
```bash
python test_dual_worker.py
```

## Common Commands

### Planning
```bash
# Create plan only (no execution)
python -m llm_service.dual_worker.cli plan "Your goal" --output plan.json

# Execute saved plan
python -m llm_service.dual_worker.cli execute ~/.dual_worker_state/plans/plan_*.json
```

### History
```bash
# View recent executions
python -m llm_service.dual_worker.cli history -n 10

# List saved plans
python -m llm_service.dual_worker.cli plans
```

### Configuration
```bash
# Show current config
python -m llm_service.dual_worker.cli config
```

## Results Location

All outputs are saved to: `~/.dual_worker_state/`

```
~/.dual_worker_state/
├── executions/          # Individual execution results (JSON)
├── plans/               # Task plans (JSON)
├── traces/              # Execution traces (JSON)
├── summary_*.json       # Session summaries
└── report_*.md          # Markdown reports
```

## Understanding Output

### Status Values
- ✅ `completed` - Task succeeded
- ❌ `failed` - Task failed (after retries)
- ⚠️  `escalated` - Needs human decision
- 🚫 `rejected` - Both workers rejected by judge

### Judge Verdict
- `ACCEPT_A` - Worker A's output chosen
- `ACCEPT_B` - Worker B's output chosen
- `REJECT_BOTH` - Neither acceptable (triggers retry)
- `MERGE` - Combine both (triggers escalation)

## Troubleshooting

### "No API key configured"
```bash
echo $GITHUB_TOKEN  # Should show your token
# If empty, set it:
export GITHUB_TOKEN="your_token"
```

### "All endpoints failed"
- Check internet connection
- Verify GitHub token is valid
- Check if GitHub Models API is accessible

### "Planning failed"
- Goal may be too vague - be more specific
- Increase max_retries in config
- Check logs for detailed error

### Slow execution
This is normal! Quality takes time:
- Simple tasks: ~15 seconds
- Standard tasks: ~60 seconds  
- Planning: ~2-3 minutes

Parallel execution is enabled by default to minimize wait time.

## Next Steps

1. **Try the full demo**:
   ```bash
   python examples/dual_worker_demo.py
   ```

2. **Read the full documentation**:
   - [DUAL_WORKER_README.md](DUAL_WORKER_README.md) - Complete guide
   - [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md) - Technical details

3. **Customize configuration**:
   ```python
   config = DualWorkerConfig.create_default()
   config.max_retries = 3
   config.rejection_threshold = 90.0
   ```

4. **Explore examples**:
   - `examples/quick_dual_worker.py` - Simple task
   - `examples/dual_worker_demo.py` - Full workflow

## Tips for Best Results

1. **Be specific in task descriptions**
   - ❌ "Build a website"
   - ✅ "Create a Flask endpoint that accepts POST /users with email and password fields"

2. **Use appropriate criticality**
   - `simple` - Boilerplate, formatting
   - `standard` - Business logic
   - `important` - Complex algorithms
   - `critical` - Security, authentication, payments

3. **Leverage retry mechanism**
   - Don't worry if first attempt is rejected
   - Judge feedback improves next attempt
   - Max 3 attempts by default

4. **Review markdown reports**
   - Generated after execution
   - Shows all worker outputs and judge reasoning
   - Great for learning and debugging

## Getting Help

- Check logs: Set `--debug` flag for verbose output
- Review execution traces in `~/.dual_worker_state/traces/`
- Read the comprehensive [README](DUAL_WORKER_README.md)

## Success! 🎉

You're now ready to use the dual-worker framework for high-quality AI task execution!

Try it:
```bash
python -m llm_service.dual_worker.cli quick "Your task here"
```
