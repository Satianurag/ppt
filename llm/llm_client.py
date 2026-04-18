"""LLM client abstraction with retry-with-feedback pattern.

Retry-with-feedback reused from PPTAgent agent.py:13-21 RETRY_TEMPLATE —
sends error + traceback back to LLM so it can self-correct.
"""

import re
import time
import traceback as tb_module
from abc import ABC, abstractmethod
from typing import Type, TypeVar, Optional
from pydantic import BaseModel

from jinja2 import Template

from .llm_config import LLMConfig, get_llm_config
from constants import MAX_RPM


T = TypeVar('T', bound=BaseModel)

# Reused from PPTAgent agent.py:13-21
RETRY_TEMPLATE = Template(
    "The previous output is invalid, please carefully analyze the traceback "
    "and feedback information, correct errors happened before.\n"
    "feedback:\n{{feedback}}\n"
    "traceback:\n{{traceback}}\n"
    "Give your corrected output in the same format without including the previous output:"
)


class LLMClient(ABC):
    """Abstract base class for LLM clients."""

    def __init__(self, config: Optional[LLMConfig] = None) -> None:
        self.config = config or get_llm_config()
        self.request_times: list[float] = []

    def _check_rate_limit(self) -> None:
        """Enforce MAX_RPM limit."""
        now = time.time()
        minute_ago = now - 60
        self.request_times = [t for t in self.request_times if t > minute_ago]

        if len(self.request_times) >= MAX_RPM:
            sleep_time = 60 - (now - self.request_times[0])
            if sleep_time > 0:
                time.sleep(sleep_time)

    @abstractmethod
    def invoke(self, prompt: str) -> str:
        """Simple text invocation."""

    @abstractmethod
    def with_structured_output(self, schema: Type[T]) -> "StructuredLLMClient[T]":
        """Return client configured for structured output."""

    def invoke_with_retry(
        self,
        prompt: str,
        max_retries: int = 3,
    ) -> str:
        """Invoke with PPTAgent-style retry-with-feedback.

        On failure, sends error + traceback back to LLM for self-correction.
        """
        last_error: Optional[Exception] = None
        conversation: list[str] = [prompt]

        for attempt in range(max_retries):
            try:
                current_prompt = "\n".join(conversation)
                return self.invoke(current_prompt)
            except Exception as e:
                last_error = e
                feedback = str(e)
                traceback_str = tb_module.format_exc()
                retry_prompt = RETRY_TEMPLATE.render(
                    feedback=feedback, traceback=traceback_str
                )
                conversation.append(retry_prompt)

        raise last_error


class StructuredLLMClient:
    """Wrapper for structured output clients with retry-with-feedback."""

    def __init__(self, client: LLMClient, schema: Type[T]) -> None:
        self.client = client
        self.schema = schema

    def invoke(self, prompt: str) -> T:
        """Invoke with structured output."""
        raise NotImplementedError("Subclasses must implement")

    def invoke_with_retry(
        self,
        prompt: str,
        max_retries: int = 3,
    ) -> T:
        """Invoke with PPTAgent-style retry-with-feedback for structured output."""
        last_error: Optional[Exception] = None
        conversation: list[str] = [prompt]

        for attempt in range(max_retries):
            try:
                current_prompt = "\n".join(conversation)
                return self.invoke(current_prompt)
            except Exception as e:
                last_error = e
                feedback = str(e)
                traceback_str = tb_module.format_exc()
                retry_prompt = RETRY_TEMPLATE.render(
                    feedback=feedback, traceback=traceback_str
                )
                conversation.append(retry_prompt)

        raise last_error


class GoogleGenAIClient(LLMClient):
    """Google GenAI (Gemini) implementation using LangChain."""

    def __init__(self, config: Optional[LLMConfig] = None) -> None:
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
            raise ValueError(
                f"Unknown provider: {config.provider}. "
                f"Available: {list(cls._providers.keys())}"
            )

        return provider_class(config)

    @classmethod
    def register_provider(cls, name: str, client_class: Type[LLMClient]) -> None:
        """Register a new provider."""
        cls._providers[name] = client_class


def get_llm_client() -> LLMClient:
    """Get configured LLM client."""
    return LLMClientFactory.create()
