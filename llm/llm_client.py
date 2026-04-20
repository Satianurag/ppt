"""Mistral LLM client with retry-with-feedback.

Single-provider design. Retry template adapted from PPTAgent (EMNLP 2025)
agent.py:13-21 — sends error + traceback back to the model so it can
self-correct.
"""

from __future__ import annotations

import json as _json
import re
import time
import traceback as tb_module
from typing import Optional, Type, TypeVar

from jinja2 import Template
from pydantic import BaseModel

from constants import MAX_RPM

from .llm_config import LLMConfig, get_llm_config


T = TypeVar("T", bound=BaseModel)


RETRY_TEMPLATE = Template(
    "The previous output is invalid, please carefully analyze the traceback "
    "and feedback information, correct errors happened before.\n"
    "feedback:\n{{feedback}}\n"
    "traceback:\n{{traceback}}\n"
    "Give your corrected output in the same format without including the previous output:"
)


class LLMClient:
    """Mistral client wrapping ``langchain_mistralai.ChatMistralAI``."""

    def __init__(self, config: Optional[LLMConfig] = None) -> None:
        from langchain_mistralai import ChatMistralAI

        self.config = config or get_llm_config()
        self.request_times: list[float] = []

        kwargs: dict = {
            "model": self.config.model,
            "api_key": self.config.api_key,
            "temperature": self.config.temperature,
            "timeout": 120,
            "max_retries": 3,
        }
        if self.config.max_output_tokens:
            kwargs["max_tokens"] = self.config.max_output_tokens

        self.model = ChatMistralAI(**kwargs)

    def _check_rate_limit(self) -> None:
        now = time.time()
        minute_ago = now - 60
        self.request_times = [t for t in self.request_times if t > minute_ago]
        if len(self.request_times) >= MAX_RPM:
            sleep_time = 60 - (now - self.request_times[0])
            if sleep_time > 0:
                time.sleep(sleep_time)

    def _invoke_with_backoff(self, call_fn, max_attempts: int = 5):
        """Exponential backoff on 429/503/timeouts."""
        import httpx

        for attempt in range(max_attempts):
            try:
                return call_fn()
            except (httpx.HTTPStatusError, httpx.ReadTimeout) as e:
                retryable = isinstance(e, httpx.ReadTimeout) or (
                    hasattr(e, "response") and e.response.status_code in (429, 503)
                )
                if retryable and attempt < max_attempts - 1:
                    wait = min(2 ** attempt * 10, 120)
                    print(f"  [rate limit] waiting {wait}s before retry {attempt + 2}/{max_attempts}")
                    time.sleep(wait)
                else:
                    raise

    def invoke(self, prompt: str) -> str:
        self._check_rate_limit()
        response = self._invoke_with_backoff(lambda: self.model.invoke(prompt))
        self.request_times.append(time.time())
        return response.content

    def invoke_with_retry(self, prompt: str, max_retries: int = 3) -> str:
        """PPTAgent-style retry with error feedback appended to the conversation."""
        last_error: Optional[Exception] = None
        conversation: list[str] = [prompt]
        for _ in range(max_retries):
            try:
                return self.invoke("\n".join(conversation))
            except Exception as e:
                last_error = e
                conversation.append(
                    RETRY_TEMPLATE.render(
                        feedback=str(e), traceback=tb_module.format_exc()
                    )
                )
        assert last_error is not None
        raise last_error

    def with_structured_output(self, schema: Type[T]) -> "StructuredLLMClient[T]":
        return StructuredLLMClient(self, schema)


class StructuredLLMClient:
    """Structured-output wrapper that tolerates Mistral's schema drift.

    Mistral occasionally exceeds ``maxLength`` / ``maxItems`` constraints that
    LangChain's ``with_structured_output`` cannot gracefully handle. We use
    raw JSON mode and sanitize with Pydantic validation.
    """

    def __init__(self, client: LLMClient, schema: Type[T]) -> None:
        self.client = client
        self.schema = schema

    def invoke(self, prompt: str) -> T:
        schema_json = self.schema.model_json_schema()
        augmented = (
            f"{prompt}\n\nRespond with a single valid JSON object matching this schema. "
            f"Do NOT wrap in markdown code fences.\n{_json.dumps(schema_json, indent=2)}"
        )
        raw = self.client.invoke(augmented)

        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)

        data = _json.loads(text)
        data = self._sanitize(data, schema_json)
        return self.schema.model_validate(data)

    def invoke_with_retry(self, prompt: str, max_retries: int = 3) -> T:
        last_error: Optional[Exception] = None
        conversation: list[str] = [prompt]
        for _ in range(max_retries):
            try:
                return self.invoke("\n".join(conversation))
            except Exception as e:
                last_error = e
                conversation.append(
                    RETRY_TEMPLATE.render(
                        feedback=str(e), traceback=tb_module.format_exc()
                    )
                )
        assert last_error is not None
        raise last_error

    def _sanitize(self, data: dict, schema: dict) -> dict:
        props = schema.get("properties", {})
        for key, spec in props.items():
            if key not in data:
                continue
            val = data[key]
            if isinstance(val, str) and "maxLength" in spec:
                data[key] = val[: spec["maxLength"]]
            if isinstance(val, list) and "maxItems" in spec:
                data[key] = val[: spec["maxItems"]]
            if isinstance(val, list) and "items" in spec:
                item_schema = self._resolve_ref(spec["items"], schema)
                if item_schema:
                    data[key] = [
                        self._sanitize(item, item_schema) if isinstance(item, dict) else item
                        for item in data[key]
                    ]
            if isinstance(val, dict) and spec.get("type") == "object":
                data[key] = self._sanitize(val, spec)
        return data

    def _resolve_ref(self, ref_spec: dict, root_schema: dict) -> dict | None:
        if "$ref" in ref_spec:
            node = root_schema
            for part in ref_spec["$ref"].split("/"):
                if part == "#":
                    node = root_schema
                else:
                    node = node.get(part, {})
            return node if node else None
        if "properties" in ref_spec:
            return ref_spec
        return None


def get_llm_client() -> LLMClient:
    return LLMClient()
