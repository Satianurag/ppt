"""Centralized LLM configuration - single source of truth."""

import os
from dataclasses import dataclass
from typing import Optional, Dict, Any


@dataclass
class LLMConfig:
    """LLM configuration dataclass."""
    provider: str  # "google", "openai", "anthropic", etc.
    model: str
    api_key: str
    temperature: float = 0.3
    max_output_tokens: Optional[int] = None
    extra_params: Optional[Dict[str, Any]] = None


class LLMConfigLoader:
    """Load LLM configuration from environment variables."""
    
    # Environment variable names (standardized)
    ENV_PROVIDER = "LLM_PROVIDER"
    ENV_MODEL = "LLM_MODEL"
    ENV_API_KEY = "LLM_API_KEY"
    ENV_TEMPERATURE = "LLM_TEMPERATURE"
    ENV_MAX_TOKENS = "LLM_MAX_TOKENS"
    
    # Fallback for backward compatibility
    LEGACY_API_KEY = "GOOGLE_API_KEY"
    
    @classmethod
    def load(cls) -> LLMConfig:
        """Load configuration from environment."""
        provider = os.getenv(cls.ENV_PROVIDER, "google")
        
        # Try new env var first, then legacy
        api_key = os.getenv(cls.ENV_API_KEY) or os.getenv(cls.LEGACY_API_KEY)
        
        if not api_key:
            raise ValueError(
                f"API key not found. Set {cls.ENV_API_KEY} or {cls.LEGACY_API_KEY}"
            )
        
        # Default models by provider
        default_models = {
            "google": "gemini-3.1-flash-lite-preview",
            "openai": "gpt-4o-mini",
            "anthropic": "claude-3-haiku-20240307",
            "mistral": "mistral-large-latest",
        }
        
        model = os.getenv(cls.ENV_MODEL, default_models.get(provider, "gemini-3.1-flash-lite-preview"))
        
        temperature = float(os.getenv(cls.ENV_TEMPERATURE, "0.3"))
        max_tokens = os.getenv(cls.ENV_MAX_TOKENS)
        
        return LLMConfig(
            provider=provider,
            model=model,
            api_key=api_key,
            temperature=temperature,
            max_output_tokens=int(max_tokens) if max_tokens else None
        )


# Singleton instance for easy access
_llm_config: Optional[LLMConfig] = None

def get_llm_config() -> LLMConfig:
    """Get singleton LLM configuration."""
    global _llm_config
    if _llm_config is None:
        _llm_config = LLMConfigLoader.load()
    return _llm_config

def reset_llm_config():
    """Reset singleton (useful for testing)."""
    global _llm_config
    _llm_config = None
