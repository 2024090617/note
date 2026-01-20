"""
Async multi-model LLM client for dual-worker framework.

Extends the base LLMClient with async support and model-specific configurations.
"""

import asyncio
import json
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime

import requests

from llm_service.client import Message, MessageRole, ChatResponse, APIError
from llm_service.auth import GitHubAuthenticator
from llm_service.dual_worker.config import ModelConfig
from llm_service.dual_worker.models import WorkerStrategy
from llm_service.dual_worker.debug_logger import get_debug_logger, is_debug_enabled

logger = logging.getLogger(__name__)


class AsyncLLMClient:
    """
    Async wrapper for LLM API calls with model-specific configurations.
    
    Supports:
    - Parallel execution of multiple models
    - Model-specific prompt strategies
    - Retry logic with exponential backoff
    - Token usage tracking
    """
    
    def __init__(self, model_config: ModelConfig):
        """
        Initialize async LLM client.
        
        Args:
            model_config: Configuration for specific model
        """
        self.config = model_config
        self.logger = logging.getLogger(f"{__name__}.{model_config.model_name}")
        
        # Initialize GitHub authenticator for Copilot API token management
        github_token = model_config.get_api_key()
        self.auth = GitHubAuthenticator(github_token)
    
    async def chat_async(
        self,
        messages: List[Message],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        timeout: Optional[int] = None,
    ) -> ChatResponse:
        """
        Send async chat completion request.
        
        Args:
            messages: Conversation messages
            temperature: Override default temperature
            max_tokens: Override default max tokens
            timeout: Override default timeout
            
        Returns:
            ChatResponse with completion
            
        Raises:
            APIError: If API request fails
        """
        # Run blocking HTTP request in thread pool
        loop = asyncio.get_event_loop()
        
        return await loop.run_in_executor(
            None,  # Use default executor
            self._chat_blocking,
            messages,
            temperature,
            max_tokens,
            timeout,
        )
    
    def _chat_blocking(
        self,
        messages: List[Message],
        temperature: Optional[float],
        max_tokens: Optional[int],
        timeout: Optional[int],
    ) -> ChatResponse:
        """Blocking chat completion (runs in thread pool)"""
        
        payload = {
            "model": self.config.model_name,
            "messages": [msg.to_dict() for msg in messages],
            "max_tokens": max_tokens or self.config.max_tokens,
            "temperature": temperature if temperature is not None else self.config.temperature,
        }
        
        # Debug logging - log request
        if is_debug_enabled():
            debug_logger = get_debug_logger()
            debug_logger.log_request(
                model_name=self.config.model_name,
                messages=messages,
                temperature=payload["temperature"],
                max_tokens=payload["max_tokens"],
                request_metadata={
                    "endpoint": self.config.api_endpoint,
                }
            )
        
        # Use appropriate headers based on endpoint
        if "inference.ai.azure.com" in self.config.api_endpoint:
            # GitHub Models API - use direct token
            headers = {
                "Authorization": f"Bearer {self.config.get_api_key()}",
                "Content-Type": "application/json",
            }
        elif "githubcopilot.com" in self.config.api_endpoint:
            # Copilot API - use token from authenticator with special headers
            headers = self.auth.get_headers()
            headers.update({
                "Editor-Version": "vscode/1.85.0",
                "Editor-Plugin-Version": "copilot/1.150.0",
                "OpenAI-Organization": "github-copilot",
            })
        else:
            # Default - direct token
            headers = {
                "Authorization": f"Bearer {self.config.get_api_key()}",
                "Content-Type": "application/json",
            }
        
        # Add model-specific headers
        if "claude" in self.config.model_name.lower():
            headers["anthropic-version"] = "2023-06-01"
        
        try:
            start_time = datetime.now()
            
            response = requests.post(
                self.config.api_endpoint,
                headers=headers,
                json=payload,
                timeout=timeout or self.config.timeout,
            )
            response.raise_for_status()
            
            data = response.json()
            
            # Check if we got a valid response
            if not data:
                raise APIError(f"Empty response from {self.config.model_name}")
            
            chat_response = ChatResponse.from_api_response(data)
            
            execution_time = (datetime.now() - start_time).total_seconds()
            
            # Safely get token count (might be null in response)
            token_count = "unknown"
            if data.get('usage') and isinstance(data['usage'], dict):
                token_count = data['usage'].get('total_tokens', 'unknown')
            
            self.logger.info(
                f"Model {self.config.model_name} completed in {execution_time:.2f}s "
                f"(tokens: {token_count})"
            )
            
            # Debug logging - log response
            if is_debug_enabled():
                debug_logger = get_debug_logger()
                debug_logger.log_response(
                    model_name=self.config.model_name,
                    response_content=chat_response.content,
                    execution_time=execution_time,
                    token_usage=data.get('usage') if isinstance(data.get('usage'), dict) else None,
                )
            
            return chat_response
            
        except requests.exceptions.RequestException as e:
            error_msg = str(e)
            error_details = None
            # Try to extract error details from response
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_data = e.response.json()
                    if 'error' in error_data:
                        error_details = str(error_data['error'])
                        error_msg = f"{error_msg}. Details: {error_details}"
                except:
                    pass
            self.logger.error(f"API request failed for {self.config.model_name}: {error_msg}")
            
            # Debug logging - log error
            if is_debug_enabled():
                debug_logger = get_debug_logger()
                debug_logger.log_error(
                    model_name=self.config.model_name,
                    error_message=error_msg,
                    error_details=error_details
                )
            
            raise APIError(f"Model {self.config.model_name} failed: {error_msg}")
        except (ValueError, KeyError) as e:
            self.logger.error(f"Failed to parse response from {self.config.model_name}: {str(e)}")
            raise APIError(f"Parse error for {self.config.model_name}: {str(e)}")
    
    async def execute_with_retry(
        self,
        messages: List[Message],
        max_retries: int = 2,
        retry_delay: int = 5,
        **kwargs
    ) -> ChatResponse:
        """
        Execute with automatic retry on failure.
        
        Args:
            messages: Conversation messages
            max_retries: Maximum retry attempts
            retry_delay: Delay between retries (seconds)
            **kwargs: Additional arguments for chat_async
            
        Returns:
            ChatResponse
            
        Raises:
            APIError: If all retries fail
        """
        last_error = None
        
        for attempt in range(max_retries + 1):
            try:
                return await self.chat_async(messages, **kwargs)
            except APIError as e:
                last_error = e
                if attempt < max_retries:
                    self.logger.warning(
                        f"Attempt {attempt + 1}/{max_retries + 1} failed for {self.config.model_name}, "
                        f"retrying in {retry_delay}s: {str(e)}"
                    )
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    self.logger.error(
                        f"All {max_retries + 1} attempts failed for {self.config.model_name}"
                    )
        
        raise last_error


class ParallelLLMExecutor:
    """
    Executes multiple LLM calls in parallel.
    
    Useful for running two workers simultaneously or batch processing.
    """
    
    def __init__(self, model_configs: List[ModelConfig]):
        """
        Initialize parallel executor.
        
        Args:
            model_configs: List of model configurations
        """
        self.clients = [AsyncLLMClient(config) for config in model_configs]
        self.logger = logging.getLogger(__name__)
    
    async def execute_parallel(
        self,
        prompts: List[List[Message]],
        **kwargs
    ) -> List[ChatResponse]:
        """
        Execute multiple prompts in parallel across different models.
        
        Args:
            prompts: List of message lists (one per model)
            **kwargs: Additional arguments for chat_async
            
        Returns:
            List of ChatResponse objects (same order as prompts)
            
        Raises:
            APIError: If any model fails (partial results not returned)
        """
        if len(prompts) != len(self.clients):
            raise ValueError(
                f"Number of prompts ({len(prompts)}) must match "
                f"number of clients ({len(self.clients)})"
            )
        
        self.logger.info(
            f"Executing {len(prompts)} prompts in parallel across models: "
            f"{[c.config.model_name for c in self.clients]}"
        )
        
        start_time = datetime.now()
        
        # Create tasks for parallel execution
        tasks = [
            client.execute_with_retry(messages, **kwargs)
            for client, messages in zip(self.clients, prompts)
        ]
        
        # Wait for all to complete
        results = await asyncio.gather(*tasks, return_exceptions=False)
        
        execution_time = (datetime.now() - start_time).total_seconds()
        
        self.logger.info(
            f"Completed {len(prompts)} parallel executions in {execution_time:.2f}s "
            f"(avg: {execution_time/len(prompts):.2f}s per model)"
        )
        
        return results
    
    async def execute_with_fallback(
        self,
        messages: List[Message],
        **kwargs
    ) -> tuple[ChatResponse, str]:
        """
        Execute with fallback - try models in order until one succeeds.
        
        Args:
            messages: Conversation messages
            **kwargs: Additional arguments for chat_async
            
        Returns:
            Tuple of (ChatResponse, model_name_used)
            
        Raises:
            APIError: If all models fail
        """
        errors = []
        
        for client in self.clients:
            try:
                response = await client.execute_with_retry(messages, max_retries=1, **kwargs)
                self.logger.info(f"Succeeded with model: {client.config.model_name}")
                return response, client.config.model_name
            except APIError as e:
                errors.append(f"{client.config.model_name}: {str(e)}")
                self.logger.warning(f"Model {client.config.model_name} failed, trying next...")
        
        # All failed
        error_summary = "; ".join(errors)
        raise APIError(f"All models failed: {error_summary}")


def create_worker_clients(
    pragmatic_config: ModelConfig,
    reasoning_config: ModelConfig
) -> tuple[AsyncLLMClient, AsyncLLMClient]:
    """
    Create two worker clients with different model configurations.
    
    Args:
        pragmatic_config: Config for pragmatic worker (e.g., GPT-4.1)
        reasoning_config: Config for reasoning worker (e.g., GPT-5 mini)
        
    Returns:
        Tuple of (pragmatic_client, reasoning_client)
    """
    return (
        AsyncLLMClient(pragmatic_config),
        AsyncLLMClient(reasoning_config),
    )


def create_parallel_executor(
    model_configs: List[ModelConfig]
) -> ParallelLLMExecutor:
    """
    Create parallel executor for multiple models.
    
    Args:
        model_configs: List of model configurations
        
    Returns:
        ParallelLLMExecutor instance
    """
    return ParallelLLMExecutor(model_configs)
