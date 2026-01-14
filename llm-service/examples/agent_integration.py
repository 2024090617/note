"""Example: Simple agent using LLM Service."""

from llm_service import LLMClient, Message, MessageRole
from typing import List, Optional
import json


class SimpleAgent:
    """A simple conversational agent."""
    
    def __init__(self, system_prompt: Optional[str] = None):
        """Initialize agent.
        
        Args:
            system_prompt: Optional system prompt defining agent behavior
        """
        self.llm = LLMClient()
        self.conversation: List[Message] = []
        
        if system_prompt:
            self.conversation.append(
                Message(role=MessageRole.SYSTEM, content=system_prompt)
            )
    
    def process(self, user_input: str) -> str:
        """Process user input and return response.
        
        Args:
            user_input: User's message
            
        Returns:
            Agent's response
        """
        response, self.conversation = self.llm.continue_conversation(
            self.conversation,
            user_input
        )
        return response
    
    def reset(self):
        """Reset conversation, keeping only system prompt."""
        if self.conversation and self.conversation[0].role == MessageRole.SYSTEM:
            self.conversation = self.conversation[:1]
        else:
            self.conversation = []
    
    def save_conversation(self, filepath: str):
        """Save conversation to file.
        
        Args:
            filepath: Path to save conversation
        """
        data = {
            "messages": [msg.model_dump() for msg in self.conversation]
        }
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
    
    def load_conversation(self, filepath: str):
        """Load conversation from file.
        
        Args:
            filepath: Path to load conversation from
        """
        with open(filepath, "r") as f:
            data = json.load(f)
            self.conversation = [Message(**msg) for msg in data["messages"]]


def main():
    # Create agent with custom behavior
    agent = SimpleAgent(
        system_prompt=(
            "You are a helpful coding assistant. "
            "You provide clear, concise answers and code examples. "
            "Always explain your reasoning."
        )
    )
    
    print("=== Simple Agent Demo ===\n")
    
    # Interaction 1
    print("User: How do I read a file in Python?")
    response = agent.process("How do I read a file in Python?")
    print(f"Agent: {response}\n")
    
    # Interaction 2
    print("User: What about writing to a file?")
    response = agent.process("What about writing to a file?")
    print(f"Agent: {response}\n")
    
    # Interaction 3
    print("User: Show me error handling for file operations")
    response = agent.process("Show me error handling for file operations")
    print(f"Agent: {response}\n")
    
    # Save conversation
    agent.save_conversation("agent_conversation.json")
    print("Conversation saved to agent_conversation.json")
    
    # Show conversation stats
    print(f"\nTotal messages: {len(agent.conversation)}")


if __name__ == "__main__":
    main()
