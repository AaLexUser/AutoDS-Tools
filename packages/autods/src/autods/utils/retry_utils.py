"""Retry utility helpers supporting sync and async call patterns."""

from __future__ import annotations

import asyncio
import logging
import random
import time
from functools import wraps
from typing import Any, Awaitable, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def retry_with(
    func: Callable[..., T],
    provider_name: str = "OpenAI",
    max_retries: int = 3,
) -> Callable[..., T]:
    """Decorator adding retry logic with randomized backoff."""

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> T:
        last_exception: Exception | None = None

        for attempt in range(max_retries + 1):
            try:
                return func(*args, **kwargs)
            except Exception as exc:  # pragma: no cover - defensive: sync variant
                last_exception = exc
                if attempt == max_retries:
                    raise

                sleep_time = random.randint(3, 30)
                logger.warning(
                    (
                        f"{provider_name} API call failed: {exc}. "
                        f"Sleeping for {sleep_time} seconds before retry"
                    ),
                    exc_info=True,
                )
                time.sleep(sleep_time)

        raise last_exception or Exception("Retry failed for unknown reason")

    return wrapper


async def async_retry(
    func: Callable[[], Awaitable[T]],
    *,
    max_attempts: int = 3,
    base_delay: float = 0.5,
    backoff_factor: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
) -> T:
    """Execute ``func`` with exponential backoff on the provided exceptions."""

    if max_attempts <= 0:
        raise ValueError("max_attempts must be positive")
    if base_delay < 0:
        raise ValueError("base_delay must be non-negative")
    if backoff_factor < 1:
        raise ValueError("backoff_factor must be at least 1")

    attempt = 0
    while True:
        try:
            return await func()
        except exceptions as exc:
            if isinstance(exc, asyncio.CancelledError):
                raise
            attempt += 1
            if attempt >= max_attempts:
                raise
            delay = base_delay * (backoff_factor ** (attempt - 1))
            if delay > 0:
                await asyncio.sleep(delay)
