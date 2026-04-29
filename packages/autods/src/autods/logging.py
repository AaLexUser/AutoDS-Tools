from __future__ import annotations

import contextlib
import logging
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import platformdirs
from loguru import logger

if TYPE_CHECKING:
    from loguru import Logger

_FORMAT = (
    "<fg 216,222,233>{time:YYYY-MM-DD HH:mm:ss.SSS}</fg 216,222,233> | "
    "{level:<8} | "
    "<fg 136,192,208>{extra[name]}</fg 136,192,208>:"
    "<fg 129,161,193>{function}</fg 129,161,193>:"
    "<fg 235,203,139>{line}</fg 235,203,139> | "
    "{message}"
)

_FILE_FORMAT = "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {extra[name]}:{function}:{line} | {message}"

_DEFAULT_APP_NAME = "autods"
_LEVEL_ENV_VARS = ("AUTODS_LOG_LEVEL", "PYGRAD_LOG_LEVEL")
_DIR_ENV_VARS = ("AUTODS_LOG_DIR", "PYGRAD_LOG_DIR")


class _InterceptHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        bound_logger = logger.bind(name=record.name)
        bound_logger.opt(exception=record.exc_info, depth=6).log(
            level,
            record.getMessage(),
        )


def _env_value(names: tuple[str, ...]) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return None


def _log_dir() -> Path:
    env = _env_value(_DIR_ENV_VARS)
    if env:
        return Path(env)
    return Path(platformdirs.user_log_dir(_DEFAULT_APP_NAME))


def setup_logging(level: str | None = None, *, console: bool = True) -> None:
    resolved_level = level or _env_value(_LEVEL_ENV_VARS) or "DEBUG"

    with contextlib.suppress(ValueError):
        logger.remove()

    logger.configure(extra={"name": _DEFAULT_APP_NAME})

    if console:
        logger.add(sys.stderr, format=_FORMAT, level=resolved_level.upper())

    log_dir = _log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    logger.add(
        log_dir / "{time:YYYY-MM-DD_HH-mm-ss}.log",
        format=_FILE_FORMAT,
        level="DEBUG",
        rotation="10 MB",
        retention="7 days",
        encoding="utf-8",
    )

    logging.basicConfig(
        handlers=[_InterceptHandler()],
        level=0,
        force=True,
    )


def get_logger(name: str) -> Logger:
    return logger.bind(name=name)
