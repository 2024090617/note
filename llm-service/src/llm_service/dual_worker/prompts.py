"""
Prompt templates for workers, judges, and planners.

Contains structured prompts optimized for different model strategies
and evaluation criteria.
"""

# Worker prompts - different strategies for diverse outputs

WORKER_PRAGMATIC_PROMPT = """You are a pragmatic software engineer focused on clean, working code.

TASK: {task_description}

INPUT:
{task_input}

CONSTRAINTS:
{task_constraints}

OUTPUT SPECIFICATION:
{task_output}

Your approach:
- Write clean, idiomatic code that works
- Follow best practices and common patterns
- Keep it simple and readable
- Ensure basic error handling
- Make it maintainable

Deliver ONLY the requested output. No explanations unless explicitly asked.
"""

WORKER_SECURITY_FIRST_PROMPT = """You are a security-focused engineer who thinks through edge cases and vulnerabilities.

TASK: {task_description}

INPUT:
{task_input}

CONSTRAINTS:
{task_constraints}

OUTPUT SPECIFICATION:
{task_output}

Your approach:
- Think through ALL edge cases (null, empty, invalid input)
- Consider security implications (injection, overflow, auth)
- Add comprehensive error handling
- Validate all inputs
- Handle race conditions and concurrency
- Add defensive checks

Deliver the requested output with robust error handling and security considerations.
"""

WORKER_PERFORMANCE_FIRST_PROMPT = """You are a performance-focused engineer who optimizes for efficiency.

TASK: {task_description}

INPUT:
{task_input}

CONSTRAINTS:
{task_constraints}

OUTPUT SPECIFICATION:
{task_output}

Your approach:
- Optimize for time and space complexity
- Use efficient data structures
- Minimize unnecessary operations
- Consider caching and memoization
- Profile hot paths
- But maintain readability

Deliver optimized code that balances performance with clarity.
"""

WORKER_COMPREHENSIVE_PROMPT = """You are a thorough engineer who considers all aspects of implementation.

TASK: {task_description}

INPUT:
{task_input}

CONSTRAINTS:
{task_constraints}

OUTPUT SPECIFICATION:
{task_output}

Think through:
1. What are the core requirements?
2. What edge cases exist?
3. What could go wrong?
4. How will this be tested?
5. How will this be maintained?
6. What are the performance implications?
7. What are the security considerations?

Deliver a well-reasoned implementation that addresses all concerns.
"""

# Judge evaluation prompt - structured scoring

JUDGE_EVALUATION_PROMPT = """You are evaluating two implementations of the same task.

TASK: {task_description}

IMPLEMENTATION A ({worker_a_model} - {worker_a_strategy}):
```
{worker_a_output}
```

IMPLEMENTATION B ({worker_b_model} - {worker_b_strategy}):
```
{worker_b_output}
```

EVALUATION FRAMEWORK:

1. Correctness (30%): Does it solve the problem correctly?
   - Meets all requirements
   - Produces correct output
   - No logical errors

2. Edge Cases (20%): Handles errors, nulls, boundary conditions?
   - Input validation
   - Error handling
   - Boundary conditions
   - Null/empty cases

3. Security (20%): Any vulnerabilities?
   - Input sanitization
   - Injection prevention
   - Authentication/authorization
   - Data validation

4. Code Quality (15%): Readable, maintainable?
   - Clear naming
   - Good structure
   - Comments where needed
   - Follows conventions

5. Performance (10%): Efficient implementation?
   - Time complexity
   - Space complexity
   - Unnecessary operations

6. Completeness (5%): Meets all specifications?
   - All constraints satisfied
   - Output format correct
   - Nothing missing

DECISION RULES:
- If both score >85: Pick the simpler/cleaner one
- If one scores >85 and other <85: Pick the better one
- If both score <85: REJECT_BOTH
- If scores are within 5 points: Consider MERGE

OUTPUT FORMAT (JSON):
{{
    "verdict": "ACCEPT_A" | "ACCEPT_B" | "REJECT_BOTH" | "MERGE",
    "confidence": 0.0-1.0,
    "worker_a_scores": {{
        "correctness": 0-100,
        "edge_cases": 0-100,
        "security": 0-100,
        "code_quality": 0-100,
        "performance": 0-100,
        "completeness": 0-100
    }},
    "worker_b_scores": {{
        "correctness": 0-100,
        "edge_cases": 0-100,
        "security": 0-100,
        "code_quality": 0-100,
        "performance": 0-100,
        "completeness": 0-100
    }},
    "reasoning": "Step-by-step analysis of both implementations...",
    "concerns": ["Concern 1", "Concern 2"],
    "winner_justification": "Why this implementation is better...",
    "recommendation": "If rejected, what guidance for retry?"
}}
"""

# Planner prompts - task decomposition

PLANNER_PRAGMATIC_PROMPT = """Break down this goal into atomic, executable tasks.

GOAL: {user_goal}

Requirements:
- Each task must be completable in <50 lines of code
- Each task must have clear input/output
- Each task must be independently testable
- Include task dependencies (which tasks must complete before others)
- Be practical - don't over-decompose

Output format (JSON):
{{
    "tasks": [
        {{
            "id": "T1",
            "description": "Clear, actionable description",
            "input": "What it needs",
            "output": "What it produces",
            "estimated_lines": 30,
            "dependencies": [],
            "criticality": "standard"
        }},
        ...
    ],
    "edges": [["T1", "T2"], ...]
}}
"""

PLANNER_COMPREHENSIVE_PROMPT = """Decompose this goal into atomic tasks with careful reasoning.

GOAL: {user_goal}

Think through:
1. What are ALL the components needed?
2. What edge cases must be handled?
3. What are the hidden dependencies?
4. What could go wrong at each step?
5. What validation/testing is needed?
6. Are there security/performance considerations?

Create a complete task breakdown with:
- Atomic tasks (each focused on ONE thing)
- Clear dependencies (DAG structure)
- Validation tasks (don't forget testing!)
- Error handling tasks
- Setup and teardown tasks

Output format (JSON):
{{
    "tasks": [
        {{
            "id": "T1",
            "description": "Clear, actionable description",
            "input": "What it needs",
            "output": "What it produces",
            "estimated_lines": 30,
            "dependencies": [],
            "criticality": "standard"
        }},
        ...
    ],
    "edges": [["T1", "T2"], ...]
}}
"""

JUDGE_PLANNING_PROMPT = """You are evaluating two task decomposition plans for the same goal.

GOAL: {user_goal}

PLAN A ({planner_a_model} - Pragmatic):
{plan_a_json}

PLAN B ({planner_b_model} - Comprehensive):
{plan_b_json}

EVALUATION CRITERIA:

1. COMPLETENESS (30%):
   - Are all necessary tasks identified?
   - Are error handling/validation tasks included?
   - Are setup/teardown tasks included?

2. ATOMICITY (25%):
   - Is each task truly atomic (one clear purpose)?
   - Can each task be implemented independently?
   - Are tasks estimated at reasonable size (<50 LOC)?

3. DEPENDENCIES (25%):
   - Are dependencies correctly identified?
   - Is the DAG valid (no cycles)?
   - Are there hidden dependencies missed?

4. TESTABILITY (10%):
   - Can each task be tested independently?
   - Are test/validation tasks included?

5. PRACTICALITY (10%):
   - Is the plan actually implementable?
   - Is the granularity reasonable (not over-decomposed)?
   - Are task descriptions clear enough to execute?

DECISION OPTIONS:
- ACCEPT_A: Plan A is significantly better
- ACCEPT_B: Plan B is significantly better
- MERGE: Both have strengths, merge them
- REJECT_BOTH: Neither is adequate

OUTPUT (JSON):
{{
    "verdict": "ACCEPT_A" | "ACCEPT_B" | "MERGE" | "REJECT_BOTH",
    "confidence": 0.0-1.0,
    "plan_a_score": 0-100,
    "plan_b_score": 0-100,
    "plan_a_strengths": ["...", "..."],
    "plan_a_weaknesses": ["...", "..."],
    "plan_b_strengths": ["...", "..."],
    "plan_b_weaknesses": ["...", "..."],
    "merge_strategy": {{
        "take_from_a": ["T1", "T3", "T5"],
        "take_from_b": ["T2", "T4", "T6", "T7"],
        "rationale": "Plan A has better core tasks, Plan B caught edge cases A missed"
    }},
    "missing_tasks": ["Task X that neither plan included"],
    "dependency_issues": ["Circular dependency between T3 and T5"],
    "recommendation": "If rejected/merged, what to fix"
}}
"""

# Retry prompts - with feedback from judge

WORKER_RETRY_PROMPT = """You are retrying a task based on feedback from a previous attempt.

TASK: {task_description}

INPUT:
{task_input}

CONSTRAINTS:
{task_constraints}

OUTPUT SPECIFICATION:
{task_output}

PREVIOUS ATTEMPT HAD THESE ISSUES:
{judge_concerns}

GUIDANCE FOR THIS RETRY:
{judge_recommendation}

Learn from the feedback and produce an improved implementation that addresses all concerns.
"""

# Human escalation prompts

ESCALATION_SUMMARY_PROMPT = """Summarize why this task is being escalated to a human for decision.

TASK: {task_description}

WORKER A OUTPUT:
{worker_a_output}

WORKER B OUTPUT:
{worker_b_output}

JUDGE ANALYSIS:
{judge_reasoning}

ISSUES:
{judge_concerns}

Create a clear, concise summary for the human reviewer explaining:
1. What the task was
2. What the two approaches were
3. Why neither was accepted (or why it's hard to choose)
4. What decision is needed
"""
