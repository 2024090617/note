from __future__ import annotations

from typing import Dict, List, Optional
from pydantic import BaseModel


class Category(BaseModel):
    id: str
    label: str
    color: str
    icon: str
    subcategories: List[str] = []
    description: Optional[str] = None


CATEGORIES: Dict[str, Category] = {
    "ai": Category(
        id="ai",
        label="Artificial Intelligence",
        color="#3B82F6",
        icon="🤖",
        subcategories=["machine-learning", "deep-learning", "nlp", "computer-vision", "reinforcement-learning"],
        description="AI, ML, neural networks, and related topics"
    ),
    "psychology": Category(
        id="psychology",
        label="Psychology",
        color="#8B5CF6",
        icon="🧠",
        subcategories=["cognitive-psychology", "social-psychology", "developmental-psychology", "behavioral"],
        description="Psychology theories, experiments, and applications"
    ),
    "computer-science": Category(
        id="computer-science",
        label="Computer Science",
        color="#10B981",
        icon="💻",
        subcategories=["algorithms", "data-structures", "distributed-systems", "databases", "networking"],
        description="CS fundamentals, algorithms, and systems"
    ),
    "research": Category(
        id="research",
        label="Research Papers",
        color="#F59E0B",
        icon="📄",
        subcategories=["paper-notes", "experiments", "theories"],
        description="Academic papers and research notes"
    ),
    "code": Category(
        id="code",
        label="Code & Implementation",
        color="#EF4444",
        icon="⚡",
        subcategories=["tutorial", "implementation", "practical"],
        description="Code snippets, tutorials, and implementations"
    ),
    "reference": Category(
        id="reference",
        label="Reference & Documentation",
        color="#6366F1",
        icon="📚",
        subcategories=["api-docs", "cheatsheet", "guide"],
        description="Reference materials and documentation"
    ),
}

# Tag status/workflow states
TAG_STATUS = {
    "unverified": {"label": "Unverified", "color": "#9CA3AF"},
    "verified": {"label": "Verified", "color": "#10B981"},
    "needs_review": {"label": "Needs Review", "color": "#F59E0B"},
}

# Tag priorities
TAG_PRIORITY = {
    "important": {"label": "Important", "color": "#EF4444", "icon": "⭐"},
    "review-needed": {"label": "Review Needed", "color": "#F59E0B", "icon": "🔍"},
    "draft": {"label": "Draft", "color": "#9CA3AF", "icon": "📝"},
}


def get_category(tag: str) -> Optional[Category]:
    """Get category for a tag"""
    # Direct match
    if tag in CATEGORIES:
        return CATEGORIES[tag]
    
    # Check subcategories
    for cat_id, category in CATEGORIES.items():
        if tag in category.subcategories:
            return category
    
    return None


def get_all_tags_for_category(category_id: str) -> List[str]:
    """Get all tags (parent + subcategories) for a category"""
    if category_id not in CATEGORIES:
        return []
    
    category = CATEGORIES[category_id]
    return [category_id] + category.subcategories


def suggest_tags(content: str, existing_tags: List[str] = []) -> List[str]:
    """Suggest additional tags based on content"""
    suggestions = []
    lower_content = content.lower()
    
    # AI keywords
    if any(word in lower_content for word in ["neural", "model", "training", "learning", "transformer"]):
        if "ai" not in existing_tags:
            suggestions.append("ai")
    
    # Psychology keywords
    if any(word in lower_content for word in ["cognitive", "behavior", "psychology", "perception"]):
        if "psychology" not in existing_tags:
            suggestions.append("psychology")
    
    # CS keywords
    if any(word in lower_content for word in ["algorithm", "complexity", "distributed", "database"]):
        if "computer-science" not in existing_tags:
            suggestions.append("computer-science")
    
    return suggestions
