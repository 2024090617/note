"""Example: Simple query usage."""

from llm_service import LLMClient

def main():
    # Initialize client
    client = LLMClient()
    
    # Simple query
    print("Example 1: Simple query")
    response = client.simple_query("What is Python in one sentence?")
    print(f"Response: {response}\n")
    
    # With system prompt
    print("Example 2: With system prompt")
    response = client.simple_query(
        "Explain list comprehensions",
        system_prompt="You are a Python expert. Be very concise."
    )
    print(f"Response: {response}\n")
    
    # With custom parameters
    print("Example 3: Custom parameters")
    response = client.simple_query(
        "Write a haiku about coding",
        temperature=1.0,  # More creative
        max_tokens=100
    )
    print(f"Response: {response}\n")


if __name__ == "__main__":
    main()
