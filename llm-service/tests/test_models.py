"""Tests for message and response models."""

import pytest
from llm_service.client import Message, MessageRole, ChatResponse


def test_message_creation():
    """Test message creation."""
    msg = Message(role=MessageRole.USER, content="Hello")
    
    assert msg.role == MessageRole.USER
    assert msg.content == "Hello"


def test_message_to_dict():
    """Test message serialization."""
    msg = Message(role=MessageRole.SYSTEM, content="You are helpful")
    
    data = msg.to_dict()
    assert data == {"role": "system", "content": "You are helpful"}


def test_chat_response_from_api():
    """Test parsing API response."""
    api_data = {
        "choices": [
            {
                "message": {"content": "Hello!"},
                "finish_reason": "stop"
            }
        ],
        "model": "gpt-4",
        "usage": {"total_tokens": 10}
    }
    
    response = ChatResponse.from_api_response(api_data)
    
    assert response.content == "Hello!"
    assert response.model == "gpt-4"
    assert response.finish_reason == "stop"
    assert response.usage == {"total_tokens": 10}


def test_chat_response_no_choices():
    """Test handling missing choices."""
    api_data = {"choices": []}
    
    with pytest.raises(ValueError, match="No choices"):
        ChatResponse.from_api_response(api_data)
