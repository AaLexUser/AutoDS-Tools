import asyncio
import logging
import re
from copy import deepcopy
from datetime import timedelta
from enum import Enum
from typing import (
    Any,
    AsyncIterator,
    Awaitable,
    Callable,
    Coroutine,
    Iterable,
    List,
    Sequence,
    TypeVar,
    cast,
)

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatResult
from langchain_core.runnables import Runnable
from langchain_core.runnables.base import RunnableConfig
from langchain_core.tools import BaseTool
from pydantic import PrivateAttr

from autods.utils.config import ModelConfig
from autods.utils.retry_utils import async_retry, retry_with

logger = logging.getLogger(__name__)

OpenAINotFoundError: type[Exception] | None
try:  # pragma: no cover - optional dependency detail
    from openai import NotFoundError as _ImportedOpenAINotFoundError
except Exception:  # pragma: no cover - safety while running without openai package
    OpenAINotFoundError = None
else:
    OpenAINotFoundError = cast(type[Exception], _ImportedOpenAINotFoundError)

ResourceExhausted: type[Exception] | None
try:  # pragma: no cover - optional dependency detail
    from google.api_core.exceptions import (
        ResourceExhausted as _ImportedResourceExhausted,
    )
except Exception:  # pragma: no cover - keep optional dependency optional
    ResourceExhausted = None
else:
    ResourceExhausted = cast(type[Exception], _ImportedResourceExhausted)

HTTPX_RETRYABLE_EXCEPTIONS: tuple[type[Exception], ...]
try:  # pragma: no cover - optional dependency detail
    import httpx
except Exception:  # pragma: no cover - allow running without httpx installed
    HTTPX_RETRYABLE_EXCEPTIONS = tuple()
else:
    HTTPX_RETRYABLE_EXCEPTIONS = (
        cast(type[Exception], httpx.ReadError),
        cast(type[Exception], httpx.RemoteProtocolError),
        cast(type[Exception], httpx.ConnectError),
        cast(type[Exception], httpx.WriteTimeout),
        cast(type[Exception], httpx.ReadTimeout),
        cast(type[Exception], httpx.PoolTimeout),
        cast(type[Exception], httpx.TimeoutException),
        cast(type[Exception], httpx.NetworkError),
    )

OPENAI_RETRYABLE_EXCEPTIONS: tuple[type[Exception], ...]
try:  # pragma: no cover - optional dependency detail
    import openai
except Exception:  # pragma: no cover - allow running without openai installed
    OPENAI_RETRYABLE_EXCEPTIONS = tuple()
else:
    OPENAI_RETRYABLE_EXCEPTIONS = (
        cast(type[Exception], openai.APIConnectionError),
        cast(type[Exception], openai.APITimeoutError),
        cast(type[Exception], openai.RateLimitError),
    )


T = TypeVar("T")


_async_retryable_exceptions: list[type[Exception]] = []
if ResourceExhausted is not None:
    _async_retryable_exceptions.append(ResourceExhausted)

_async_retryable_exceptions.extend(HTTPX_RETRYABLE_EXCEPTIONS)
_async_retryable_exceptions.extend(OPENAI_RETRYABLE_EXCEPTIONS)
_async_retryable_exceptions.append(asyncio.TimeoutError)

ASYNC_RETRYABLE_EXCEPTIONS: tuple[type[Exception], ...] = tuple(
    dict.fromkeys(_async_retryable_exceptions)
)

ASYNC_BASE_DELAY_SECONDS = 1.0
ASYNC_MAX_BACKOFF_SECONDS = 60.0
ASYNC_BACKOFF_FACTOR = 2.0


IMAGE_PLACEHOLDER_TEXT = "[image omitted due to model limitations]"
IMAGE_REMOVAL_NOTICE = (
    "Image output omitted because the current endpoint does not support image inputs."
)


class LLMProvider(Enum):
    """Supported LLM providers."""

    OPENAI = "openai"
    GOOGLE = "google"


class LLMClient(BaseChatModel):
    """Main LLM client that supports multiple providers."""

    # Private attributes to avoid Pydantic field validation
    _provider: LLMProvider = PrivateAttr()
    _llm_config: ModelConfig = PrivateAttr()
    _client: BaseChatModel | None = PrivateAttr(default=None)

    def __init__(self, llm_config: ModelConfig):
        # Initialize provider and config before calling super().__init__()
        provider = LLMProvider(llm_config.model_provider.provider)

        super().__init__()

        # Set private attributes after super() call
        self._provider = provider
        self._llm_config = llm_config
        self._client = None

        match provider:
            case LLMProvider.OPENAI:
                from langchain_openai import ChatOpenAI

                # NOTE:
                # Pass a plain string API key to ChatOpenAI.
                # Using pydantic SecretStr here leaks an object representation
                # into the underlying OpenAI client and may corrupt request
                # headers/payloads for some proxies, resulting in 400 errors
                # like "Your request contains invalid JSON syntax.".
                from pydantic import SecretStr

                client: BaseChatModel = ChatOpenAI(
                    model=llm_config.model,
                    api_key=SecretStr(llm_config.model_provider.api_key)
                    if llm_config.model_provider.api_key
                    else None,
                    base_url=llm_config.model_provider.base_url,
                    max_retries=llm_config.max_retries,
                    model_kwargs=llm_config.model_kwargs or {},
                    extra_body=llm_config.extra_body,
                    default_headers=llm_config.default_headers,
                )
            case LLMProvider.GOOGLE:
                from langchain_google_genai import ChatGoogleGenerativeAI

                # Build kwargs for Google provider
                google_kwargs: dict[str, Any] = {}
                if llm_config.model_kwargs:
                    google_kwargs.update(llm_config.model_kwargs)

                client = ChatGoogleGenerativeAI(
                    model=llm_config.model,
                    google_api_key=llm_config.model_provider.api_key,
                    max_retries=llm_config.max_retries,
                    additional_headers=llm_config.default_headers,
                    **google_kwargs,
                )
            case _:
                raise ValueError(f"Unsupported LLM provider: {provider.value}")

        self._client = client

    def _require_client(self) -> BaseChatModel:
        client = self._client
        if client is None:
            raise ValueError("Client not initialized")
        return client

    # --------------------------------------------------------------------- #
    # Capability helpers
    # --------------------------------------------------------------------- #

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: List[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Generate response using the underlying client with retries.

        Note: This method is used by the async-fallback path when the upstream
        client returns an empty stream. That scenario is often not improved by
        additional retries (and the sync retry emits noisy warnings). To avoid
        long sleeps in that narrow case, ``ainvoke`` now calls the underlying
        client's ``_generate`` directly instead of routing through this method.
        """
        client = self._require_client()

        def _call() -> ChatResult:
            return client._generate(messages, stop, run_manager, **kwargs)

        retry_fn = retry_with(
            _call,
            provider_name=self._provider.value,
            max_retries=self._llm_config.max_retries,
        )
        return retry_fn()

    @property
    def _llm_type(self) -> str:
        """Return type of llm."""
        return f"autods_{self._provider.value}"

    async def _async_call_with_retry(self, func: Callable[[], Awaitable[T]]) -> T:
        max_retries = max(self._llm_config.max_retries, 0)
        return await _call_async_with_retry(
            func,
            provider_name=self._provider.value,
            max_retries=max_retries,
        )

    def _async_stream_with_retry(
        self, generator_factory: Callable[[], AsyncIterator[Any]]
    ) -> AsyncIterator[Any]:
        max_retries = max(self._llm_config.max_retries, 0)
        return _stream_async_with_retry(
            generator_factory,
            provider_name=self._provider.value,
            max_retries=max_retries,
        )

    def invoke(
        self,
        input: Any,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> Any:
        try:
            client = self._require_client()
            return client.invoke(input, config=config, **kwargs)
        except Exception as exc:
            fallback = _prepare_fallback_input(exc, input)
            if fallback is None:
                raise
        client = self._require_client()
        return client.invoke(fallback, config=config, **kwargs)

    async def ainvoke(
        self,
        input: Any,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> Any:
        async def _run(payload: Any) -> Any:
            client = self._require_client()

            async def _call() -> Any:
                return await client.ainvoke(payload, config=config, **kwargs)

            return await self._async_call_with_retry(_call)

        def _is_empty_stream_error(exc: Exception) -> bool:
            msg = str(exc).lower()
            # Stream produced no chunks or client returned an empty response
            if "no generations found" in msg and "stream" in msg:
                return True
            if "response missing `choices`" in msg:
                return True
            if "null value for `choices`" in msg:
                return True
            if "noneType" in msg and "model_dump" in msg:
                return True
            return False

        try:
            return await _run(input)
        except Exception as exc:
            # 1) Image input error: strip images and retry async
            fallback = _prepare_fallback_input(exc, input)
            if fallback is not None:
                return await _run(fallback)

            # 2) Empty-stream error: fallback to sync invoke; if that fails too,
            # try the low-level _generate path when we have messages.
            if _is_empty_stream_error(exc):
                client = self._require_client()
                try:
                    # Try a sync invoke first (provider usually has its own retries)
                    return client.invoke(input, config=config, **kwargs)
                except Exception as exc2:
                    if _is_empty_stream_error(exc2):
                        # Attempt a quick, low-latency generate when messages are available
                        messages = None
                        if isinstance(input, list):
                            messages = input
                        elif isinstance(input, dict):
                            messages = input.get("messages")

                        def _quick_generate(attempts: int = 2):
                            # Guard: not every client exposes a private _generate
                            gen_fn = getattr(client, "_generate", None)
                            if gen_fn is None:
                                return None
                            last_err: Exception | None = None
                            for _ in range(max(1, attempts)):
                                try:
                                    result = gen_fn(  # type: ignore[misc]
                                        messages,  # type: ignore[arg-type]
                                        None,
                                        None,
                                    )
                                    if hasattr(result, "generations") and getattr(
                                        result, "generations"
                                    ):
                                        return result
                                except Exception as e:  # keep it tight and quick
                                    last_err = e
                                    continue
                            if last_err is not None:
                                logger.debug(
                                    "Quick _generate attempts failed with %s",
                                    type(last_err).__name__,
                                )
                            return None

                        if messages is not None:
                            chat_result = _quick_generate()
                            if chat_result is not None:
                                return chat_result.generations[0].message  # type: ignore[no-any-return]

                        # Final resort: return a visible notice so graph state isn't empty
                        from langchain_core.messages import AIMessage

                        logger.warning(
                            "_generate fallback also failed (%s). Returning notice AIMessage.",
                            type(exc2).__name__,
                            exc_info=True,
                        )
                        return AIMessage(
                            content=(
                                "Model returned no output after fallback attempts. "
                                "No tool calls extracted. You can retry this step."
                            )
                        )
                    raise
            # 3) Unknown error: re-raise
            raise

    def stream(
        self,
        input: Any,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ):
        try:
            client = self._require_client()
            for chunk in client.stream(input, config=config, **kwargs):
                yield chunk
            return
        except Exception as exc:
            fallback = _prepare_fallback_input(exc, input)
            if fallback is None:
                raise
        client = self._require_client()
        for chunk in client.stream(fallback, config=config, **kwargs):
            yield chunk

    async def astream(
        self,
        input: Any,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ):
        current_input = input
        image_fallback_applied = False
        client = self._require_client()

        while True:
            try:
                async for chunk in self._async_stream_with_retry(
                    lambda: client.astream(current_input, config=config, **kwargs)
                ):
                    yield chunk
                return
            except Exception as exc:
                if not image_fallback_applied:
                    fallback = _prepare_fallback_input(exc, current_input)
                    if fallback is not None:
                        current_input = fallback
                        image_fallback_applied = True
                        continue
                raise

    def batch(
        self,
        inputs: list[Any],
        config: RunnableConfig | list[RunnableConfig] | None = None,
        *,
        return_exceptions: bool = False,
        **kwargs: Any,
    ) -> list[Any]:
        client = self._require_client()
        inputs_list = list(inputs)
        try:
            return client.batch(
                inputs_list,
                config=config,
                return_exceptions=return_exceptions,
                **kwargs,
            )
        except Exception as exc:
            fallback_batch = _prepare_fallback_batch_input(exc, inputs_list)
            if fallback_batch is None:
                raise
        return client.batch(
            fallback_batch,
            config=config,
            return_exceptions=return_exceptions,
            **kwargs,
        )

    def abatch(
        self,
        inputs: list[Any],
        config: RunnableConfig | list[RunnableConfig] | None = None,
        *,
        return_exceptions: bool = False,
        **kwargs: Any,
    ) -> Coroutine[Any, Any, list[Any]]:
        inputs_list = list(inputs)

        async def _execute(batch: list[Any]) -> list[Any]:
            client = self._require_client()

            async def _call() -> list[Any]:
                return await client.abatch(
                    batch,
                    config=config,
                    return_exceptions=return_exceptions,
                    **kwargs,
                )

            return await self._async_call_with_retry(_call)

        async def _runner() -> list[Any]:
            try:
                return await _execute(inputs_list)
            except Exception as exc:
                fallback_batch = _prepare_fallback_batch_input(exc, inputs_list)
                if fallback_batch is None:
                    raise
            return await _execute(fallback_batch)

        return _runner()

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Callable[..., Any] | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable[Any, Any]:
        client = self._require_client()
        bound = client.bind_tools(tools, tool_choice=tool_choice, **kwargs)
        return _ImageRetryRunnable(bound, self)


class _ImageRetryRunnable(Runnable[Any, Any]):
    """Wrapper runnable that retries without image inputs on 404 errors."""

    def __init__(self, inner: Runnable[Any, Any], client: "LLMClient"):
        super().__init__()
        self._inner = inner
        self._client = client

    def __getattr__(self, item: str) -> Any:  # pragma: no cover - passthrough
        return getattr(self._inner, item)

    def invoke(
        self,
        input: Any,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> Any:
        try:
            return self._inner.invoke(input, config=config, **kwargs)
        except Exception as exc:
            fallback = _prepare_fallback_input(exc, input)
            if fallback is None:
                raise
        return self._inner.invoke(fallback, config=config, **kwargs)

    async def ainvoke(
        self,
        input: Any,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> Any:
        async def _run(payload: Any) -> Any:
            async def _call() -> Any:
                return await self._inner.ainvoke(payload, config=config, **kwargs)

            return await self._client._async_call_with_retry(_call)

        try:
            return await _run(input)
        except Exception as exc:
            fallback = _prepare_fallback_input(exc, input)
            if fallback is None:
                raise
        return await _run(fallback)

    def stream(
        self,
        input: Any,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ):
        try:
            for chunk in self._inner.stream(input, config=config, **kwargs):
                yield chunk
            return
        except Exception as exc:
            fallback = _prepare_fallback_input(exc, input)
            if fallback is None:
                raise
        for chunk in self._inner.stream(fallback, config=config, **kwargs):
            yield chunk

    async def astream(
        self,
        input: Any,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ):
        current_input = input
        image_fallback_applied = False

        while True:
            try:
                async for chunk in self._client._async_stream_with_retry(
                    lambda: self._inner.astream(current_input, config=config, **kwargs)
                ):
                    yield chunk
                return
            except Exception as exc:
                if not image_fallback_applied:
                    fallback = _prepare_fallback_input(exc, current_input)
                    if fallback is not None:
                        current_input = fallback
                        image_fallback_applied = True
                        continue
                raise

    def batch(
        self,
        inputs: list[Any],
        config: RunnableConfig | list[RunnableConfig] | None = None,
        *,
        return_exceptions: bool = False,
        **kwargs: Any,
    ) -> list[Any]:
        inputs_list = list(inputs)
        try:
            return self._inner.batch(
                inputs_list,
                config=config,
                return_exceptions=return_exceptions,
                **kwargs,
            )
        except Exception as exc:
            fallback_batch = _prepare_fallback_batch_input(exc, inputs_list)
            if fallback_batch is None:
                raise
        return self._inner.batch(
            fallback_batch,
            config=config,
            return_exceptions=return_exceptions,
            **kwargs,
        )

    def abatch(
        self,
        inputs: list[Any],
        config: RunnableConfig | list[RunnableConfig] | None = None,
        *,
        return_exceptions: bool = False,
        **kwargs: Any,
    ) -> Coroutine[Any, Any, list[Any]]:
        inputs_list = list(inputs)

        async def _execute(batch: list[Any]) -> list[Any]:
            async def _call() -> list[Any]:
                return await self._inner.abatch(
                    batch,
                    config=config,
                    return_exceptions=return_exceptions,
                    **kwargs,
                )

            return await self._client._async_call_with_retry(_call)

        async def _runner() -> list[Any]:
            try:
                return await _execute(inputs_list)
            except Exception as exc:
                fallback_batch = _prepare_fallback_batch_input(exc, inputs_list)
                if fallback_batch is None:
                    raise
            return await _execute(fallback_batch)

        return _runner()


async def _call_async_with_retry(
    func: Callable[[], Awaitable[T]],
    *,
    provider_name: str,
    max_retries: int,
) -> T:
    if not ASYNC_RETRYABLE_EXCEPTIONS or max_retries <= 0:
        return await func()

    attempt = 0

    async def _runner() -> T:
        nonlocal attempt
        try:
            return await func()
        except Exception as exc:
            if not _matches_retryable_exception(exc) or not _is_retryable_error(exc):
                raise
            if attempt >= max_retries:
                raise
            attempt += 1
            delay = _extract_retry_after_seconds(exc)
            if delay is not None and delay > 0:
                logger.warning(
                    "%s API call failed with %s. Retrying in %.2fs (attempt %s/%s).",
                    provider_name,
                    type(exc).__name__,
                    delay,
                    attempt,
                    max_retries,
                )
                await asyncio.sleep(delay)
            else:
                backoff_delay = _compute_backoff_delay(attempt)
                logger.warning(
                    "%s API call failed with %s. Applying backoff %.2fs (attempt %s/%s).",
                    provider_name,
                    type(exc).__name__,
                    backoff_delay,
                    attempt,
                    max_retries,
                )
                if backoff_delay > 0:
                    await asyncio.sleep(backoff_delay)
            raise

    return await async_retry(
        _runner,
        max_attempts=max_retries + 1,
        base_delay=0.0,
        backoff_factor=1.0,
        exceptions=ASYNC_RETRYABLE_EXCEPTIONS,
    )


def _stream_async_with_retry(
    generator_factory: Callable[[], AsyncIterator[Any]],
    *,
    provider_name: str,
    max_retries: int,
) -> AsyncIterator[Any]:
    async def _iterator() -> AsyncIterator[Any]:
        if not ASYNC_RETRYABLE_EXCEPTIONS or max_retries <= 0:
            async for item in generator_factory():
                yield item
            return

        attempt = 0
        while True:
            stream = generator_factory()
            try:
                async for item in stream:
                    yield item
                return
            except Exception as exc:
                if isinstance(exc, asyncio.CancelledError):
                    raise
                if not _matches_retryable_exception(exc) or not _is_retryable_error(
                    exc
                ):
                    raise
                if attempt >= max_retries:
                    raise
                attempt += 1
                delay = _extract_retry_after_seconds(exc)
                if delay is not None and delay > 0:
                    logger.warning(
                        "%s API call failed with %s during stream. Retrying in %.2fs (attempt %s/%s).",
                        provider_name,
                        type(exc).__name__,
                        delay,
                        attempt,
                        max_retries,
                    )
                    await asyncio.sleep(delay)
                else:
                    backoff_delay = _compute_backoff_delay(attempt)
                    logger.warning(
                        "%s API call failed with %s during stream. Applying backoff %.2fs (attempt %s/%s).",
                        provider_name,
                        type(exc).__name__,
                        backoff_delay,
                        attempt,
                        max_retries,
                    )
                    if backoff_delay > 0:
                        await asyncio.sleep(backoff_delay)

    return _iterator()


def _matches_retryable_exception(error: Exception) -> bool:
    return any(isinstance(error, exc_type) for exc_type in ASYNC_RETRYABLE_EXCEPTIONS)


def _is_retryable_error(error: Exception) -> bool:
    if HTTPX_RETRYABLE_EXCEPTIONS and isinstance(error, HTTPX_RETRYABLE_EXCEPTIONS):
        return True
    if OPENAI_RETRYABLE_EXCEPTIONS and isinstance(error, OPENAI_RETRYABLE_EXCEPTIONS):
        return True
    if isinstance(error, asyncio.TimeoutError):
        return True
    if ResourceExhausted is not None and isinstance(error, ResourceExhausted):
        return True
    status_code = getattr(error, "status_code", None)
    if status_code == 429:
        return True
    code = getattr(error, "code", None)
    if isinstance(code, int) and code == 429:
        return True
    if isinstance(code, str) and code == "429":
        return True
    if code is not None and "RESOURCE_EXHAUSTED" in str(code).upper():
        return True
    message = str(error).lower()
    return "rate limit" in message or "quota exceeded" in message


def _extract_retry_after_seconds(error: Exception) -> float | None:
    retry_after = getattr(error, "retry_after", None)
    if retry_after is not None:
        if isinstance(retry_after, timedelta):
            return max(retry_after.total_seconds(), 0.0)
        try:
            value = float(retry_after)
            if value >= 0:
                return value
        except (TypeError, ValueError):
            pass

    response = getattr(error, "response", None)
    if response is not None:
        headers = getattr(response, "headers", None)
        if headers and "Retry-After" in headers:
            try:
                header_val = headers["Retry-After"]
                value = float(header_val)
                if value >= 0:
                    return value
            except (TypeError, ValueError):
                pass

    match = re.search(r"retry in\s+([0-9]+(?:\.[0-9]+)?)s", str(error).lower())
    if match:
        try:
            return float(match.group(1))
        except ValueError:  # pragma: no cover - defensive parsing
            return None

    return None


def _compute_backoff_delay(attempt: int) -> float:
    if attempt <= 0:
        return 0.0
    delay = ASYNC_BASE_DELAY_SECONDS * (ASYNC_BACKOFF_FACTOR ** (attempt - 1))
    return min(delay, ASYNC_MAX_BACKOFF_SECONDS)


def _prepare_fallback_input(error: Exception, original_input: Any) -> Any | None:
    if not _should_retry_image_error(error):
        return None
    sanitized, changed = _strip_images_from_input(original_input)
    if not changed:
        return None
    return sanitized


def _prepare_fallback_batch_input(
    error: Exception, inputs: list[Any]
) -> list[Any] | None:
    if not _should_retry_image_error(error):
        return None
    sanitized_inputs: list[Any] = []
    changed_any = False
    for item in inputs:
        sanitized, changed = _strip_images_from_input(item)
        sanitized_inputs.append(sanitized)
        changed_any = changed_any or changed
    if not changed_any:
        return None
    return sanitized_inputs


def _should_retry_image_error(error: Exception) -> bool:
    message = str(error).lower()
    # Specific signals that content-list payloads are not supported by the endpoint
    if "no endpoints found that support image input" in message:
        return True
    if "not a multimodal model" in message:
        return True
    if "expected string, but got array instead" in message:
        return True
    # Generic image-related 404s
    if "image" in message:
        if OpenAINotFoundError is not None and isinstance(error, OpenAINotFoundError):
            return True
        code = getattr(error, "code", None)
        if code == 404 or str(code) == "404":
            return True
        status_code = getattr(error, "status_code", None)
        if status_code == 404:
            return True
    return False


def _strip_images_from_input(value: Any) -> tuple[Any, bool]:
    if isinstance(value, BaseMessage):
        return _strip_images_from_message(value)
    if isinstance(value, dict):
        messages = value.get("messages")
        if messages is None:
            return value, False
        sanitized_messages, changed = _strip_images_from_sequence(messages)
        if not changed:
            return value, False
        new_payload = dict(value)
        new_payload["messages"] = sanitized_messages
        return new_payload, True
    if isinstance(value, (list, tuple)):
        sanitized_messages, changed = _strip_images_from_sequence(list(value))
        if not changed:
            return value, False
        if isinstance(value, tuple):
            return tuple(sanitized_messages), True
        return sanitized_messages, True
    return value, False


def _strip_images_from_sequence(messages: Iterable[Any]) -> tuple[list[Any], bool]:
    sanitized: list[Any] = []
    changed_any = False
    for message in messages:
        sanitized_msg: Any
        if isinstance(message, BaseMessage):
            sanitized_msg, changed = _strip_images_from_message(message)
        elif isinstance(message, dict):
            sanitized_msg, changed = _strip_images_from_message_dict(message)
        else:
            sanitized_msg, changed = message, False
        sanitized.append(sanitized_msg)
        changed_any = changed_any or changed
    return sanitized, changed_any


def _strip_images_from_message(message: BaseMessage) -> tuple[BaseMessage, bool]:
    sanitized_content, changed = _strip_images_from_content(message.content)
    if not changed:
        return message, False
    return message.model_copy(update={"content": sanitized_content}), True


def _strip_images_from_message_dict(
    message: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    content = message.get("content")
    if content is None:
        return message, False
    sanitized_content, changed = _strip_images_from_content(content)
    if not changed:
        return message, False
    new_message = deepcopy(message)
    new_message["content"] = sanitized_content
    return new_message, True


def _strip_images_from_content(content: Any) -> tuple[Any, bool]:
    if isinstance(content, list):
        sanitized_parts: list[str] = []
        image_found = False
        for part in content:
            if isinstance(part, dict) and part.get("type") == "image_url":
                image_found = True
                continue
            if isinstance(part, dict):
                txt = part.get("text") or part.get("content")
                if isinstance(txt, str) and txt:
                    sanitized_parts.append(txt)
            elif isinstance(part, str):
                sanitized_parts.append(part)
        if image_found and not sanitized_parts:
            sanitized_parts.append(IMAGE_PLACEHOLDER_TEXT)
            logger.info(IMAGE_REMOVAL_NOTICE)
        # Join textual parts into a single string since some endpoints
        # (e.g., chat.completions) expect content to be a string, not a list.
        flat_text = "\n".join(sanitized_parts).strip()
        return flat_text, True
    return content, False
