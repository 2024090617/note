# LLM Service

A Python library for accessing LLM APIs via command-line and programmatic interfaces. Uses **GitHub Models** (free for GitHub users) - no OpenAI key required!

## Features

- 🚀 **Simple CLI** - Query LLMs directly from your terminal
- 💬 **Interactive Chat** - Full conversation mode with history
- 🔧 **Python API** - Easy integration into your code
- 🆓 **Free** - Uses GitHub Models (no cost with GitHub account)
- 💾 **Conversation History** - Save and load chat sessions
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

## License

MIT License

## Notes

- Uses GitHub Models API (free for GitHub users)
- Default model: `gpt-4o-mini`
- No OpenAI key required!
