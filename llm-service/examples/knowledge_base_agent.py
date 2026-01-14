"""Example: Agent with knowledge base integration.

This example shows how to integrate the LLM Service with the knowledge-base
notebook system for RAG (Retrieval-Augmented Generation).
"""

import sys
from pathlib import Path
from typing import List, Optional

# Add knowledge-base to path (adjust path as needed)
kb_path = Path(__file__).parent.parent.parent / "knowledge-base" / "src"
sys.path.insert(0, str(kb_path))

from llm_service import LLMClient, Message, MessageRole, Config

try:
    from notebook.storage import get_store
    KNOWLEDGE_BASE_AVAILABLE = True
except ImportError:
    KNOWLEDGE_BASE_AVAILABLE = False
    print("Warning: Knowledge base not available. Install knowledge-base project.")


class KnowledgeAgent:
    """Agent that uses both LLM and knowledge base."""
    
    def __init__(self, system_prompt: Optional[str] = None):
        """Initialize agent.
        
        Args:
            system_prompt: Optional system prompt
        """
        # Create config with longer timeout for knowledge base operations
        config = Config.from_env()
        config.timeout = 120  # Increase timeout for knowledge base operations
        self.llm = LLMClient(config=config)
        self.conversation: List[Message] = []
        
        # Initialize knowledge base if available
        self.kb_store = None
        if KNOWLEDGE_BASE_AVAILABLE:
            try:
                self.kb_store = get_store()
                self.kb_store.ensure_collection()
            except Exception as e:
                print(f"Warning: Could not initialize knowledge base: {e}")
        
        # Set default system prompt
        if not system_prompt:
            system_prompt = (
                "You are a helpful assistant with access to a knowledge base. "
                "When provided with context from the knowledge base, use it to answer questions. "
                "Be accurate and cite the information when relevant."
            )
        
        self.conversation.append(
            Message(role=MessageRole.SYSTEM, content=system_prompt)
        )
    
    def search_knowledge_base(self, query: str, limit: int = 3) -> List[dict]:
        """Search knowledge base for relevant information.
        
        Args:
            query: Search query
            limit: Maximum number of results
            
        Returns:
            List of search results
        """
        if not self.kb_store:
            return []
        
        try:
            results = self.kb_store.search(query, limit=limit)
            return results
        except Exception as e:
            print(f"Warning: Knowledge base search failed: {e}")
            return []
    
    def process_with_context(self, user_input: str, search_kb: bool = True, show_context: bool = False) -> str:
        """Process user input with optional knowledge base context.
        
        Args:
            user_input: User's question/message
            search_kb: Whether to search knowledge base
            show_context: Whether to display retrieved context
            
        Returns:
            Agent's response
        """
        # Search knowledge base if enabled
        context_items = []
        if search_kb and self.kb_store:
            try:
                context_items = self.search_knowledge_base(user_input, limit=3)
                if show_context and context_items:
                    print(f"📚 Retrieved {len(context_items)} context item(s) from knowledge base:")
                    for i, item in enumerate(context_items, 1):
                        score = item.get('score', 0)
                        print(f"  {i}. {item.get('title', 'Untitled')} (score: {score:.3f})")
                    print()
            except Exception as e:
                print(f"Warning: Knowledge base search failed: {e}")
                context_items = []
        
        # Build enhanced prompt with context
        if context_items:
            context_text = "\n\n".join([
                f"[Context {i+1}] {item.get('title', 'Untitled')}\n{item.get('content', '')[:500]}..."
                for i, item in enumerate(context_items)
            ])
            
            enhanced_prompt = (
                f"[Knowledge Base Context]\n{context_text}\n\n"
                f"[User Question]\n{user_input}\n\n"
                f"Please answer the question using the provided context when relevant."
            )
        else:
            enhanced_prompt = user_input
        
        # Get LLM response
        response, self.conversation = self.llm.continue_conversation(
            self.conversation,
            enhanced_prompt
        )
        return response
    
    def add_to_knowledge_base(self, title: str, content: str, tags: List[str] = None) -> str:
        """Add information to knowledge base.
        
        Args:
            title: Note title
            content: Note content
            tags: Optional tags
            
        Returns:
            Note ID
        """
        if not self.kb_store:
            raise RuntimeError("Knowledge base not available")
        
        import uuid
        note_id = str(uuid.uuid4())
        
        self.kb_store.upsert_note_version(
            note_id=note_id,
            title=title,
            content=content,
            tags=tags or [],
            source_url=None,
            status="unverified",
            verified_at=None,
            version=1,
        )
        
        return note_id


def main():
    if not KNOWLEDGE_BASE_AVAILABLE:
        print("This example requires the knowledge-base project.")
        print("Please set up the knowledge-base first.")
        return
    
    print("=" * 70)
    print("🤖 Knowledge-Augmented Agent Demo (RAG)")
    print("=" * 70)
    print()
    
    # Create agent
    agent = KnowledgeAgent()
    
    # Step 1: Add knowledge to the knowledge base
    print("📝 Step 1: Populating Knowledge Base\n")
    
    knowledge_items = [
        {
            "title": "Python List Comprehensions",
            "content": (
                "List comprehensions provide a concise way to create lists in Python. "
                "The basic syntax is: [expression for item in iterable if condition]. "
                "For example, to create squares: squares = [x**2 for x in range(10)]. "
                "They're more readable and often faster than traditional for loops. "
                "You can also use nested comprehensions and multiple conditions."
            ),
            "tags": ["python", "programming", "tutorial", "basics"]
        },
        {
            "title": "Python Decorators",
            "content": (
                "Decorators are a powerful feature in Python that allow you to modify or "
                "enhance functions without changing their source code. They use the @decorator "
                "syntax placed above a function definition. Common use cases include: "
                "logging (@log_calls), authentication (@require_auth), caching "
                "(@functools.lru_cache), and timing (@timeit). A decorator is essentially "
                "a function that takes another function and extends its behavior."
            ),
            "tags": ["python", "programming", "advanced", "design-patterns"]
        },
        {
            "title": "Python Async/Await",
            "content": (
                "Async/await in Python enables asynchronous programming using coroutines. "
                "Use 'async def' to define an async function and 'await' to call it. "
                "This is perfect for I/O-bound operations like web requests or file operations. "
                "The asyncio library provides the event loop. Example: async def fetch(): "
                "data = await http_client.get(url). Async code is single-threaded but can "
                "handle many operations concurrently without blocking."
            ),
            "tags": ["python", "programming", "advanced", "concurrency"]
        }
    ]
    
    for item in knowledge_items:
        note_id = agent.add_to_knowledge_base(
            title=item["title"],
            content=item["content"],
            tags=item["tags"]
        )
        print(f"  ✓ Added: {item['title']}")
    
    print(f"\n✅ Added {len(knowledge_items)} items to knowledge base\n")
    print("-" * 70)
    
    # Step 2: Query with RAG - topic in knowledge base
    print("\n💡 Step 2: Query with RAG (Topic in Knowledge Base)\n")
    
    question = "What are list comprehensions in Python? Give me examples."
    print(f"👤 User: {question}\n")
    response = agent.process_with_context(question, search_kb=True, show_context=True)
    print(f"🤖 Agent: {response}\n")
    print("-" * 70)
    
    # Step 3: Follow-up question (uses conversation history)
    print("\n🔄 Step 3: Follow-Up Question (Conversation Context)\n")
    
    question = "Can you show me a nested list comprehension example?"
    print(f"👤 User: {question}\n")
    response = agent.process_with_context(question, search_kb=False)
    print(f"🤖 Agent: {response}\n")
    print("-" * 70)
    
    # Step 4: Query another topic from knowledge base
    print("\n🔍 Step 4: Query Different Topic (RAG Search)\n")
    
    question = "Explain decorators in Python"
    print(f"👤 User: {question}\n")
    response = agent.process_with_context(question, search_kb=True, show_context=True)
    print(f"🤖 Agent: {response}\n")
    print("-" * 70)
    
    # Step 5: Query without RAG (general knowledge)
    print("\n🌐 Step 5: General Question (No RAG, LLM Knowledge Only)\n")
    
    question = "What is the difference between a list and a tuple in Python?"
    print(f"👤 User: {question}\n")
    response = agent.process_with_context(question, search_kb=False)
    print(f"🤖 Agent: {response}\n")
    print("-" * 70)
    
    # Step 6: Complex query combining multiple knowledge items
    print("\n🎯 Step 6: Complex Query (Multiple Context Items)\n")
    
    question = "Compare list comprehensions with async/await - which is better for what?"
    print(f"👤 User: {question}\n")
    response = agent.process_with_context(question, search_kb=True, show_context=True)
    print(f"🤖 Agent: {response}\n")
    
    print("=" * 70)
    print("✅ Demo completed successfully!")
    print(f"📊 Total conversation messages: {len(agent.conversation)}")
    print("=" * 70)


if __name__ == "__main__":
    main()
