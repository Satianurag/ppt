"""LLM client abstraction - easy to swap SDKs."""

from abc import ABC, abstractmethod
from typing import Type, TypeVar, Optional
from pydantic import BaseModel
import time

from .llm_config import LLMConfig, get_llm_config


T = TypeVar('T', bound=BaseModel)


class LLMClient(ABC):
    """Abstract base class for LLM clients."""
    
    MAX_RPM = 8  # Default rate limit
    
    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or get_llm_config()
        self.request_times = []  # For rate limiting
    
    def _check_rate_limit(self):
        """Enforce MAX_RPM limit."""
        now = time.time()
        minute_ago = now - 60
        
        self.request_times = [t for t in self.request_times if t > minute_ago]
        
        if len(self.request_times) >= self.MAX_RPM:
            sleep_time = 60 - (now - self.request_times[0])
            if sleep_time > 0:
                time.sleep(sleep_time)
    
    @abstractmethod
    def invoke(self, prompt: str) -> str:
        """Simple text invocation."""
        pass
    
    @abstractmethod
    def with_structured_output(self, schema: Type[T]) -> "StructuredLLMClient[T]":
        """Return client configured for structured output."""
        pass


class StructuredLLMClient:
    """Wrapper for structured output clients."""
    
    def __init__(self, client: LLMClient, schema: Type[T]):
        self.client = client
        self.schema = schema
    
    def invoke(self, prompt: str) -> T:
        """Invoke with structured output."""
        raise NotImplementedError("Subclasses must implement")


class GoogleGenAIClient(LLMClient):
    """Google GenAI (Gemini) implementation using LangChain."""
    
    def __init__(self, config: Optional[LLMConfig] = None):
        super().__init__(config)
        from langchain_google_genai import ChatGoogleGenerativeAI
        
        kwargs = {
            "model": self.config.model,
            "google_api_key": self.config.api_key,
            "temperature": self.config.temperature,
        }
        
        if self.config.max_output_tokens:
            kwargs["max_output_tokens"] = self.config.max_output_tokens
        
        self.model = ChatGoogleGenerativeAI(**kwargs)
    
    def invoke(self, prompt: str) -> str:
        self._check_rate_limit()
        response = self.model.invoke(prompt)
        self.request_times.append(time.time())
        return response.content
    
    def with_structured_output(self, schema: Type[T]) -> "GoogleStructuredClient[T]":
        """Return structured output client."""
        return GoogleStructuredClient(self, schema)


class GoogleStructuredClient(StructuredLLMClient):
    """Google GenAI with structured output."""
    
    def invoke(self, prompt: str) -> T:
        self.client._check_rate_limit()
        
        structured_model = self.client.model.with_structured_output(
            schema=self.schema,
            method="json_schema"
        )
        
        result = structured_model.invoke(prompt)
        self.client.request_times.append(time.time())
        return result


class LLMClientFactory:
    """Factory for creating LLM clients."""
    
    _providers = {
        "google": GoogleGenAIClient,
    }
    
    @classmethod
    def create(cls, config: Optional[LLMConfig] = None) -> LLMClient:
        """Create LLM client from config."""
        config = config or get_llm_config()
        
        provider_class = cls._providers.get(config.provider)
        if not provider_class:
            raise ValueError(f"Unknown provider: {config.provider}. "
                           f"Available: {list(cls._providers.keys())}")
        
        return provider_class(config)
    
    @classmethod
    def register_provider(cls, name: str, client_class: Type[LLMClient]):
        """Register a new provider (for extensibility)."""
        cls._providers[name] = client_class


# Convenience function
def get_llm_client() -> LLMClient:
    """Get configured LLM client."""
    return LLMClientFactory.create()
