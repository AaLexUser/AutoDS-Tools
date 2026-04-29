"""LLM implementations for neo4j-graphrag integration."""

import os
from typing import Any

import httpx
from neo4j_graphrag.llm import LLMInterface
from neo4j_graphrag.llm.types import LLMResponse
from neo4j_graphrag.message_history import MessageHistory
from neo4j_graphrag.types import LLMMessage

from pygrad.common.log import get_logger

logger = get_logger(__name__)


def _log_llm_request(endpoint: str, model: str, payload: dict[str, Any]) -> None:
    """Log outgoing chat-completions request (no API keys or auth headers)."""
    messages = payload.get("messages") or []
    for i, msg in enumerate(messages):
        role = msg.get("role", "?")
        content = msg.get("content") or ""
        logger.debug(
            "LLM message[{}] role={} ({} chars)\n{}",
            i,
            role,
            len(content),
            content,
        )


class CustomAPILLM(LLMInterface):
    """Custom LLM implementation for OpenRouter and OpenAI-compatible APIs.

    Implements the neo4j-graphrag LLMInterface for custom API endpoints.
    """

    def __init__(
        self,
        model: str,
        api_key: str,
        endpoint: str,
        temperature: float = 0.0,
        max_tokens: int = 2000,
        timeout: float = 120.0,
    ):
        """Initialize CustomAPILLM.

        Args:
            model: Model name/identifier
            api_key: API key for authentication
            endpoint: API endpoint URL
            temperature: Sampling temperature (default: 0.0)
            max_tokens: Maximum tokens in response (default: 2000)
            timeout: HTTP request timeout in seconds (default: 120.0)
        """
        self.model = model
        self.api_key = api_key
        self.endpoint = endpoint
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout

    def invoke(
        self,
        input: str,
        message_history: list[LLMMessage] | MessageHistory | None = None,
        system_instruction: str | None = None,
    ) -> LLMResponse:
        """Synchronous LLM invocation.

        Args:
            input: Input prompt text
            message_history: Optional prior messages (unused for this provider)
            system_instruction: Optional system message override (unused)

        Returns:
            Generated text response
        """
        del message_history, system_instruction
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": input}],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

        _log_llm_request(self.endpoint, self.model, payload)

        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(self.endpoint, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        message = data["choices"][0]["message"]
        content = message.get("content") or ""
        if (content_len := len(content)) == 0:
            logger.error("LLM returned empty response.")
        else:
            logger.debug("LLM response length: {} chars", content_len)
        return LLMResponse(content=content)

    async def ainvoke(
        self,
        input: str,
        message_history: list[LLMMessage] | MessageHistory | None = None,
        system_instruction: str | None = None,
    ) -> LLMResponse:
        """Asynchronous LLM invocation.

        Args:
            input: Input prompt text
            message_history: Optional prior messages (unused for this provider)
            system_instruction: Optional system message override (unused)

        Returns:
            Generated text response
        """
        del message_history, system_instruction
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": input}],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

        _log_llm_request(self.endpoint, self.model, payload)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(self.endpoint, json=payload, headers=headers)

            if response.status_code != 200:
                error_detail = response.text
                raise ValueError(f"API Error {response.status_code}: {error_detail}")

            data = response.json()

        message = data["choices"][0]["message"]
        content = message.get("content") or ""
        if (content_len := len(content)) == 0:
            logger.error("LLM returned empty response.")
        else:
            logger.debug("LLM response length: {} chars", content_len)
        return LLMResponse(content=content)


def create_llm_from_env() -> LLMInterface:
    """Create LLM instance from environment variables.

    Supports providers: custom, ollama, openai

    Environment variables:
        LLM_PROVIDER: Provider name (custom, ollama, openai)
        LLM_MODEL: Model name
        LLM_API_KEY: API key
        LLM_ENDPOINT: API endpoint URL

    Returns:
        LLMInterface implementation

    Raises:
        ValueError: If required environment variables are missing
        ImportError: If provider-specific package is not installed
    """
    provider = os.getenv("LLM_PROVIDER", "").lower()
    model = os.getenv("LLM_MODEL")
    api_key = os.getenv("LLM_API_KEY")
    endpoint = os.getenv("LLM_ENDPOINT")

    if not provider:
        raise ValueError("LLM_PROVIDER environment variable is required")
    if not model:
        raise ValueError("LLM_MODEL environment variable is required")

    if provider == "custom":
        if not api_key:
            raise ValueError("LLM_API_KEY environment variable is required for custom provider")
        if not endpoint:
            raise ValueError("LLM_ENDPOINT environment variable is required for custom provider")
        return CustomAPILLM(
            model=model,
            api_key=api_key,
            endpoint=endpoint,
        )

    elif provider == "ollama":
        try:
            from neo4j_graphrag.llm import OllamaLLM
        except ImportError as e:
            raise ImportError("Ollama support requires: pip install neo4j-graphrag[ollama]") from e

        if not endpoint:
            endpoint = "http://localhost:11434"

        return OllamaLLM(
            model_name=model,
            base_url=endpoint,
        )

    elif provider == "openai":
        try:
            from neo4j_graphrag.llm import OpenAILLM
        except ImportError as e:
            raise ImportError("OpenAI support requires: pip install neo4j-graphrag[openai]") from e

        if not api_key:
            raise ValueError("LLM_API_KEY environment variable is required for openai provider")

        return OpenAILLM(model_name=model, api_key=api_key, base_url=endpoint)

    else:
        raise ValueError(f"Unsupported LLM_PROVIDER: {provider}. Supported providers: custom, ollama, openai")
