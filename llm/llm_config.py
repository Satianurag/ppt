"""Centralized LLM configuration - Mistral only.

Per hackathon constraint C5: this project uses Mistral as the sole LLM
provider. No Google/Gemini fallbacks, no OpenAI, no Anthropic.
"""

import os
from dataclasses import dataclass
from typing import Optional


DEFAULT_MISTRAL_MODEL: str = "mistral-large-latest"


@dataclass
class LLMConfig:
    """Mistral LLM configuration."""
    model: str
    api_key: str
    temperature: float = 0.3
    max_output_tokens: Optional[int] = None


def load_config() -> LLMConfig:
    """Load Mistral configuration from environment.

    Reads ``MISTRAL_API_KEY`` (required) and optional
    ``LLM_MODEL`` / ``LLM_TEMPERATURE`` / ``LLM_MAX_TOKENS``.
    """
    api_key = os.getenv("MISTRAL_API_KEY")
    if not api_key:
        raise ValueError(
            "MISTRAL_API_KEY not set. This project uses Mistral as the sole LLM "
            "provider. Set MISTRAL_API_KEY in your environment or .env file."
        )

    model = os.getenv("LLM_MODEL", DEFAULT_MISTRAL_MODEL)
    temperature = float(os.getenv("LLM_TEMPERATURE", "0.3"))
    max_tokens_env = os.getenv("LLM_MAX_TOKENS")
    max_tokens = int(max_tokens_env) if max_tokens_env else None

    return LLMConfig(
        model=model,
        api_key=api_key,
        temperature=temperature,
        max_output_tokens=max_tokens,
    )


_llm_config: Optional[LLMConfig] = None


def get_llm_config() -> LLMConfig:
    """Get singleton Mistral configuration."""
    global _llm_config
    if _llm_config is None:
        _llm_config = load_config()
    return _llm_config


def reset_llm_config() -> None:
    """Reset singleton."""
    global _llm_config
    _llm_config = None
