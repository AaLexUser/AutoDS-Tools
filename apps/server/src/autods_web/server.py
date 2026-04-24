from __future__ import annotations

import multiprocessing
from typing import Any, Optional

import uvicorn
from dotenv import load_dotenv

from autods.logging import get_logger, setup_logging

from .api import create_app

logger = get_logger(__name__)


def run_api_server(
    host: str = "localhost",
    port: int = 8000,
    agent_options: Optional[dict[str, Any]] = None,
):
    load_dotenv()
    setup_logging(console=False)
    logger.info("Starting API server on {}:{}", host, port)
    app = create_app(agent_options=agent_options or {})
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
        access_log=False,
        log_config=None,
    )


def start_web_server(
    api_host: str = "localhost",
    api_port: int = 8000,
    background: bool = False,
    agent_options: Optional[dict[str, Any]] = None,
) -> Optional[multiprocessing.Process]:
    if background:
        api_process = multiprocessing.Process(
            target=run_api_server,
            args=(api_host, api_port, agent_options),
        )
        try:
            api_process.start()
            return api_process
        except Exception:
            logger.exception("Failed to start API server")
            api_process.terminate()
            return None

    try:
        run_api_server(api_host, api_port, agent_options)
    except KeyboardInterrupt:
        logger.info("Stopping API server")

    return None


def main() -> None:
    run_api_server()
