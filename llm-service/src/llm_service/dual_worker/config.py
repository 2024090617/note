"""
Configuration for dual-worker+judge framework.

Manages model routing, API credentials, and execution strategies
based on task criticality and available model resources.
"""

import os
from enum import Enum
from pathlib import Path
from typing import Dict, Optional

from pydantic import BaseModel, Field


class ModelRole(str, Enum):
    """Model role in the system"""
    WORKER_PRAGMATIC = "worker_pragmatic"      # Fast, clean implementation
    WORKER_REASONING = "worker_reasoning"      # Deep reasoning, edge cases
    JUDGE_STANDARD = "judge_standard"          # Standard quality judge
    JUDGE_PREMIUM = "judge_premium"            # Premium quality judge
    PLANNER_PRAGMATIC = "planner_pragmatic"    # Pragmatic planning
    PLANNER_REASONING = "planner_reasoning"    # Comprehensive planning


class ModelConfig(BaseModel):
    """Configuration for a specific model"""
    model_name: str = Field(..., description="Model identifier (gpt-4.1, etc.)")
    api_endpoint: str = Field(..., description="API endpoint URL")
    api_key_env: str = Field(..., description="Environment variable for API key")
    rate_limit: Optional[str] = Field(default=None, description="Rate limit (e.g., '3x', 'unlimited')")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, ge=1)
    timeout: int = Field(default=60, ge=1)
    
    def get_api_key(self) -> str:
        """Get API key from environment"""
        key = os.getenv(self.api_key_env, "")
        if not key:
            raise ValueError(f"API key not found in environment variable: {self.api_key_env}")
        return key


class DualWorkerConfig(BaseModel):
    """
    Configuration for dual-worker+judge system.
    
    Defines which models to use for each role based on:
    - Available free models (GPT-4.1, GPT-5 mini unlimited)
    - Rate-limited premium models (Claude Opus 4.5 3x, Grok Code Fast 1 unlimited)
    - Task criticality routing
    """
    
    # Model assignments for different roles
    models: Dict[ModelRole, ModelConfig] = Field(default_factory=dict)
    
    # GitHub Models API (free tier)
    github_models_url: str = Field(
        default="https://models.inference.ai.azure.com",
        description="GitHub Models API endpoint"
    )
    
    # Copilot API (fallback)
    copilot_api_url: str = Field(
        default="https://api.githubcopilot.com",
        description="Copilot API endpoint"
    )
    
    # Default retry and timeout settings
    max_retries: int = Field(default=2, ge=0, description="Max retry attempts per task")
    retry_delay_seconds: int = Field(default=5, ge=0, description="Delay between retries")
    
    # Human escalation settings
    auto_escalate_threshold: float = Field(
        default=0.6, ge=0.0, le=1.0,
        description="Confidence threshold below which to escalate to human"
    )
    rejection_threshold: float = Field(
        default=85.0, ge=0.0, le=100.0,
        description="Score threshold for accepting outputs"
    )
    
    # Execution settings
    enable_parallel_workers: bool = Field(default=True, description="Run workers in parallel")
    enable_auto_retry: bool = Field(default=True, description="Auto-retry with feedback")
    enable_debate_mode: bool = Field(default=False, description="Workers critique each other")
    
    # Logging
    log_prompts: bool = Field(default=True, description="Log prompts and responses")
    log_level: str = Field(default="INFO", description="Logging level")
    
    @classmethod
    def create_default(cls) -> "DualWorkerConfig":
        """
        Create default configuration using GitHub Models API.
        
        Uses actual available models from GitHub Models API (accessible via Copilot):
        - gpt-4o-mini (unlimited) - Fast worker  
        - gpt-4o (unlimited) - Reasoning worker and judges
        
        Note: These are the same models available in Copilot Chat, accessed via 
        GitHub Models API which supports PAT authentication.
        """
        
        github_token_env = "GITHUB_TOKEN"
        # Use GitHub Models API (works with PAT tokens)
        api_endpoint = "https://models.inference.ai.azure.com/chat/completions"
        
        models = {
            # Workers: gpt-4o-mini (pragmatic) + gpt-4o (reasoning)
            ModelRole.WORKER_PRAGMATIC: ModelConfig(
                model_name="gpt-4o-mini",
                api_endpoint=api_endpoint,
                api_key_env=github_token_env,
                rate_limit="unlimited",
                temperature=0.7,
                max_tokens=4096,
                timeout=60,
            ),
            ModelRole.WORKER_REASONING: ModelConfig(
                model_name="gpt-4o",
                api_endpoint=api_endpoint,
                api_key_env=github_token_env,
                rate_limit="unlimited",
                temperature=0.7,
                max_tokens=4096,
                timeout=90,  # Reasoning takes longer
            ),
            
            # Standard judge: gpt-4o (unlimited, excellent reasoning)
            ModelRole.JUDGE_STANDARD: ModelConfig(
                model_name="gpt-4o",
                api_endpoint=api_endpoint,
                api_key_env=github_token_env,
                rate_limit="unlimited",
                temperature=0.3,  # More deterministic for judging
                max_tokens=4096,
                timeout=60,
            ),
            
            # Premium judge: gpt-4o (best available model for critical tasks)
            ModelRole.JUDGE_PREMIUM: ModelConfig(
                model_name="gpt-4o",
                api_endpoint=api_endpoint,
                api_key_env=github_token_env,
                rate_limit="unlimited",
                temperature=0.3,
                max_tokens=4096,
                timeout=90,
            ),
            
            # Planners: Same as workers but for planning tasks
            ModelRole.PLANNER_PRAGMATIC: ModelConfig(
                model_name="gpt-4o-mini",
                api_endpoint=api_endpoint,
                api_key_env=github_token_env,
                rate_limit="unlimited",
                temperature=0.5,  # Slightly more deterministic for planning
                max_tokens=8192,  # Larger for comprehensive plans
                timeout=90,
            ),
            ModelRole.PLANNER_REASONING: ModelConfig(
                model_name="gpt-4o",
                api_endpoint=api_endpoint,
                api_key_env=github_token_env,
                rate_limit="unlimited",
                temperature=0.5,
                max_tokens=8192,
                timeout=120,  # Planning can take longer
            ),
        }
        
        return cls(models=models)
    
    @classmethod
    def from_env(cls, env_file: Optional[Path] = None) -> "DualWorkerConfig":
        """
        Load configuration from environment variables.
        
        If env_file is provided, load from .env file first.
        """
        if env_file and env_file.exists():
            # Load .env file (would need python-dotenv dependency)
            # For now, just use environment variables
            pass
        
        # Start with defaults
        config = cls.create_default()
        
        # Override with environment variables if present
        if os.getenv("DW_MAX_RETRIES"):
            config.max_retries = int(os.getenv("DW_MAX_RETRIES"))
        
        if os.getenv("DW_AUTO_ESCALATE_THRESHOLD"):
            config.auto_escalate_threshold = float(os.getenv("DW_AUTO_ESCALATE_THRESHOLD"))
        
        if os.getenv("DW_REJECTION_THRESHOLD"):
            config.rejection_threshold = float(os.getenv("DW_REJECTION_THRESHOLD"))
        
        if os.getenv("DW_ENABLE_DEBATE_MODE"):
            config.enable_debate_mode = os.getenv("DW_ENABLE_DEBATE_MODE").lower() == "true"
        
        if os.getenv("DW_LOG_LEVEL"):
            config.log_level = os.getenv("DW_LOG_LEVEL")
        
        return config
    
    def get_judge_for_criticality(self, criticality) -> ModelConfig:
        """
        Get appropriate judge model based on task criticality.
        
        - CRITICAL/IMPORTANT → Premium judge (Opus 4.5)
        - STANDARD/SIMPLE → Standard judge (Grok Code Fast 1)
        """
        # Import here to avoid circular dependency
        try:
            from llm_service.dual_worker.models import TaskCriticality
            if criticality == TaskCriticality.CRITICAL:
                return self.models[ModelRole.JUDGE_PREMIUM]
        except:
            pass
        
        return self.models[ModelRole.JUDGE_STANDARD]
    
    def get_worker_configs(self) -> tuple[ModelConfig, ModelConfig]:
        """Get both worker configurations (pragmatic, reasoning)"""
        return (
            self.models[ModelRole.WORKER_PRAGMATIC],
            self.models[ModelRole.WORKER_REASONING]
        )
    
    def get_planner_configs(self) -> tuple[ModelConfig, ModelConfig]:
        """Get both planner configurations (pragmatic, reasoning)"""
        return (
            self.models[ModelRole.PLANNER_PRAGMATIC],
            self.models[ModelRole.PLANNER_REASONING]
        )

    @classmethod
    def create_copilot_bridge(cls) -> "DualWorkerConfig":
        """
        Create configuration using Copilot Bridge (VS Code extension).
        
        This configuration uses the full range of Copilot models:
        - gpt-5-mini - Fast worker
        - gpt-5.1 - Reasoning worker
        - claude-opus-4.5 - Premium judge
        - gpt-4o - Standard judge
        
        Requires the Copilot Bridge VS Code extension to be running.
        """
        
        # Copilot Bridge runs locally on port 19823
        copilot_bridge_endpoint = "http://127.0.0.1:19823/chat"
        
        # This is a dummy key - the bridge handles auth through VS Code
        dummy_key_env = "COPILOT_BRIDGE_KEY"
        os.environ.setdefault(dummy_key_env, "bridge-key")
        
        models = {
            # Workers: gpt-5-mini (fast) + gpt-5.2 (reasoning)
            ModelRole.WORKER_PRAGMATIC: ModelConfig(
                model_name="gpt-5-mini",
                api_endpoint=copilot_bridge_endpoint,
                api_key_env=dummy_key_env,
                rate_limit="unlimited",
                temperature=0.7,
                max_tokens=4096,
                timeout=60,
            ),
            ModelRole.WORKER_REASONING: ModelConfig(
                model_name="gpt-5.2",  # gpt-5.1 not supported, use gpt-5.2
                api_endpoint=copilot_bridge_endpoint,
                api_key_env=dummy_key_env,
                rate_limit="unlimited",
                temperature=0.7,
                max_tokens=4096,
                timeout=90,
            ),
            
            # Standard judge: claude-sonnet-4.5 (fast + quality)
            ModelRole.JUDGE_STANDARD: ModelConfig(
                model_name="claude-sonnet-4.5",
                api_endpoint=copilot_bridge_endpoint,
                api_key_env=dummy_key_env,
                rate_limit="unlimited",
                temperature=0.3,
                max_tokens=4096,
                timeout=60,
            ),
            
            # Premium judge: claude-sonnet-4.5 (opus not always available)
            ModelRole.JUDGE_PREMIUM: ModelConfig(
                model_name="claude-sonnet-4.5",
                api_endpoint=copilot_bridge_endpoint,
                api_key_env=dummy_key_env,
                rate_limit="limited",
                temperature=0.3,
                max_tokens=4096,
                timeout=90,
            ),
            
            # Planners
            ModelRole.PLANNER_PRAGMATIC: ModelConfig(
                model_name="gpt-5-mini",
                api_endpoint=copilot_bridge_endpoint,
                api_key_env=dummy_key_env,
                rate_limit="unlimited",
                temperature=0.5,
                max_tokens=8192,
                timeout=90,
            ),
            ModelRole.PLANNER_REASONING: ModelConfig(
                model_name="gpt-5.2",  # gpt-5.1 not supported, use gpt-5.2
                api_endpoint=copilot_bridge_endpoint,
                api_key_env=dummy_key_env,
                rate_limit="unlimited",
                temperature=0.5,
                max_tokens=8192,
                timeout=120,
            ),
        }
        
        return cls(models=models)
