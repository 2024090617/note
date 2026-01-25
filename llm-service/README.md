# LLM Service

A Python library for accessing LLM APIs via command-line and programmatic interfaces. Includes a **Developer Agent** for autonomous software development tasks.

## Features

- 🚀 **Simple CLI** - Query LLMs directly from your terminal
- 💬 **Interactive Chat** - Full conversation mode with history
- 🤖 **Developer Agent** - Autonomous agent for coding tasks (ReAct pattern)
- 🔧 **Python API** - Easy integration into your code
- 🆓 **Free** - Uses GitHub Models (no cost with GitHub account)
- 🔌 **Copilot Bridge** - Access VS Code Copilot models via HTTP
- 💾 **Conversation History** - Save and load chat sessions
- 📝 **Detailed Logging** - Track all agent interactions
- 🎨 **Rich Output** - Beautiful markdown rendering

## Installation

```bash
cd llm-service
pip install -e .
```

## Quick Start

### 1. Setup Your GitHub Token

Get a Personal Access Token from: https://github.com/settings/tokens

Create a `.env` file:
```bash
GITHUB_TOKEN=your_github_token_here
```

### 2. Test It

```bash
source .env
llm test
```

### 3. Start Using

```bash
# Simple query
llm query "What is Python?"

# Interactive chat
llm chat
```

**Simple queries:**

```bash
# Basic query
llm query "What is Python?"

# With system prompt
llm query "Explain async/await" --system "You are a Python expert"

# From stdin
echo "What is Rust?" | llm query

# JSON output
llm query "List 3 Python frameworks" --json-output
```

**Interactive chat:**

```bash
# Start a chat session
llm chat

# With system prompt
llm chat --system "You are a helpful coding assistant"

# Save/load conversations
llm chat --load previous.json --save conversation.json
```

**Chat commands:**
- `/quit` - Exit chat
- `/clear` - Clear conversation history
- `/save [path]` - Save conversation
- `/help` - Show help

### 3. Python API Usage

**Simple queries:**

```python
from llm_service import LLMClient

# Initialize client (uses GITHUB_TOKEN from environment)
client = LLMClient()

# Simple query
response = client.simple_query("What is Python?")
print(response)

# With system prompt
response = client.simple_query(
    "Explain decorators",
    system_prompt="You are a Python expert. Be concise."
)
print(response)
```

**Conversations:**

```python
from llm_service import LLMClient, Message, MessageRole

client = LLMClient()

# Start conversation
conversation = [
    Message(role=MessageRole.SYSTEM, content="You are a helpful assistant")
]

# Continue conversation
response, conversation = client.continue_conversation(
    conversation,
    "What is machine learning?"
)
print(response)

# Keep chatting
response, conversation = client.continue_conversation(
    conversation,
    "Give me a simple example"
)
print(response)
```

**Advanced usage:**

```python
from llm_service import LLMClient, Message, MessageRole, Config

# Custom configuration
config = Config(
    github_token="your_token",
    model="gpt-4o-mini",
    temperature=0.7,
    max_tokens=2000
)

client = LLMClient(config)

# Manual message construction
messages = [
    Message(role=MessageRole.SYSTEM, content="You are a code reviewer"),
    Message(role=MessageRole.USER, content="Review this code: def foo(): pass")
]

response = client.chat(messages, temperature=0.3)
print(response.content)
```

**Integration with your agent:**

```python
from llm_service import LLMClient, Message, MessageRole

class MyAgent:
    def __init__(self):
        self.llm = LLMClient()
        self.conversation = [
            Message(
                role=MessageRole.SYSTEM,
                content="You are an AI agent assistant."
            )
        ]
    
    def process(self, user_input: str) -> str:
        response, self.conversation = self.llm.continue_conversation(
            self.conversation,
            user_input
        )
        return response

# Use the agent
agent = MyAgent()
response = agent.process("Hello!")
print(response)
```

## Configuration

Create a `.env` file:

```bash
GITHUB_TOKEN=your_github_token_here
```

Or set environment variables:

```bash
export GITHUB_TOKEN='your_token'
```

View current configuration:

```bash
llm config
```

## Examples

Check the `examples/` directory:

- `simple_query.py` - Basic queries
- `conversation.py` - Multi-turn conversations
- `agent_integration.py` - Simple agent pattern
- `knowledge_base_agent.py` - Integration with knowledge base for RAG

---

## Developer Agent

The Developer Agent is an autonomous coding assistant that can read requirements, create/modify files, run tests, and fix issues using a ReAct (Reason + Act) loop.

### Prerequisites: Copilot Bridge

The agent uses VS Code's Copilot models via the Copilot Bridge:

1. **Install the Bridge Extension** (first time only):
   ```bash
   python copilot_bridge.py
   ```

2. **Start the Bridge** in VS Code:
   - Open Command Palette (`Cmd+Shift+P` / `Ctrl+Shift+P`)
   - Run: `Start Copilot Bridge Server`
   - The bridge runs at `http://127.0.0.1:19823`

### Quick Start

```bash
# Interactive mode
agent

# Run a task directly
agent -n "Create a Python function to parse JSON files"

# With verbose logging
agent --verbose

# Use specific model
agent --model gpt-4o
```

### CLI Options

```
agent [options] [task]

Options:
  --mode, -m        Backend: copilot (default) or github-models
  --model           Model to use (default: gpt-4o-mini)
  --system, -s      System prompt (or @file to load from file)
  --workdir, -w     Working directory (default: current)
  --non-interactive, -n   Run task and exit
  --json            Output as JSON (with -n)
  --log-dir         Log directory (default: ./agent_logs)
  --verbose, -v     Enable verbose console logging
  --no-log-file     Disable file logging
```

### Interactive Commands

**General:**
| Command | Description |
|---------|-------------|
| `/help` | Show all commands |
| `/quit`, `/exit` | Exit the agent |
| `/status` | Show mode, model, workdir, git status |
| `/clear` | Clear conversation history |

**Configuration:**
| Command | Description |
|---------|-------------|
| `/mode <copilot\|github-models>` | Switch backend |
| `/model <name>` | Set model (gpt-4o, claude-3.5-sonnet, etc.) |
| `/system <text\|@file>` | Set system prompt |
| `/models` | List available Copilot models |

**Task Management:**
| Command | Description |
|---------|-------------|
| `/task <description\|@file>` | Start autonomous task |
| `/save <path>` | Save session to file |
| `/load <path>` | Load session from file |

**File Operations:**
| Command | Description |
|---------|-------------|
| `/open <path>` | Preview a file |
| `/search <pattern>` | Search workspace |
| `/diff` | Show pending git changes |

**Developer Tools:**
| Command | Description |
|---------|-------------|
| `/env` | Detect dev environment |
| `/lint [cmd]` | Run linter |
| `/test [cmd]` | Run tests |
| `/run <cmd>` | Run shell command |
| `/confirm` | Confirm risky action |
| `/rollback` | Revert uncommitted changes |
| `/logs [id]` | View interaction logs |

### Logging

The agent logs all interactions for debugging and auditing:

```bash
# View logs interactively
agent
> /logs                    # List all logs
> /logs 20260125_143022    # View specific session

# Log files location
ls agent_logs/
# interaction_<session_id>.jsonl       - Event stream
# interaction_<session_id>_complete.json - Full structured log
```

**Log contents:**
- LLM calls (model, messages, response, duration)
- Tool calls (action, params, result, success)
- ReAct iterations (thought, action, observation)
- Session summary (task, status, timestamps)

### Python API

```python
from llm_service.agent import Agent, AgentConfig

# Create agent
config = AgentConfig(
    mode="copilot",          # or "github-models"
    model="gpt-4o-mini",
    workdir="/path/to/project",
    log_to_file=True,
)
agent = Agent(config)

# Simple chat
response = agent.chat("What files are in this directory?")
print(response)

# Run autonomous task
result = agent.run_task("Create a Python script that lists all .py files")
print(result.summary)

# Check status
print(agent.status())

# Save/load session
agent.save_session("my_session.json")
agent.load_session("my_session.json")
```

### Agent Capabilities

The agent can perform these actions autonomously:

| Action | Description |
|--------|-------------|
| `read_file` | Read file contents |
| `write_file` | Write/update files |
| `create_file` | Create new files |
| `list_directory` | List directory contents |
| `search_files` | Search by glob pattern |
| `grep_search` | Search file contents |
| `run_command` | Execute shell commands |
| `detect_environment` | Inspect dev tools |
| `git_status` | Check git state |
| `plan` | Create execution plan |
| `complete` | Mark task done |

### Example Session

```
$ agent
╭─────────────────────────────────────────────────────╮
│ Developer Agent                                     │
│ Mode: copilot | Model: gpt-4o-mini                  │
│ Type /help for commands or just chat.               │
╰─────────────────────────────────────────────────────╯

[copilot] | model:gpt-4o-mini | dir:llm-service
> /task Create a utility function to format dates in ISO format

💭 I'll create a simple utility function for date formatting...
🔧 create_file
✓ create_file

╭──────────────────── Task Result ────────────────────╮
│ Created `utils/date_utils.py` with `format_iso()`   │
│ function that converts dates to ISO 8601 format.    │
╰─────────────────────────────────────────────────────╯

> /logs
┏━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━┓
┃ Session ID          ┃ Status    ┃ Iterations ┃
┡━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━┩
│ 20260125_150432     │ completed │ 2          │
└─────────────────────┴───────────┴────────────┘
```

---

## License

MIT License

## Notes

- Uses GitHub Models API (free for GitHub users)
- Default model: `gpt-4o-mini`
- No OpenAI key required!
