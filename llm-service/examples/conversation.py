"""Example: Multi-turn conversation."""

from llm_service import LLMClient, Message, MessageRole

def main():
    client = LLMClient()
    
    # Start with system prompt
    conversation = [
        Message(
            role=MessageRole.SYSTEM,
            content="You are a helpful coding tutor. Explain concepts clearly and provide examples."
        )
    ]
    
    # Turn 1
    print("User: What is a Python decorator?")
    response, conversation = client.continue_conversation(
        conversation,
        "What is a Python decorator?"
    )
    print(f"Assistant: {response}\n")
    
    # Turn 2
    print("User: Can you show me a simple example?")
    response, conversation = client.continue_conversation(
        conversation,
        "Can you show me a simple example?"
    )
    print(f"Assistant: {response}\n")
    
    # Turn 3
    print("User: What are common use cases?")
    response, conversation = client.continue_conversation(
        conversation,
        "What are common use cases?"
    )
    print(f"Assistant: {response}\n")
    
    print(f"Total messages in conversation: {len(conversation)}")


if __name__ == "__main__":
    main()
