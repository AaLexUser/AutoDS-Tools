import logging
import multiprocessing
from logging import log
from typing import Any, Optional

import uvicorn
from rich.console import Console

from .api import create_app

console = Console()


def run_api_server(
    host: str = "localhost",
    port: int = 8000,
    agent_options: Optional[dict[str, Any]] = None,
):
    log(logging.INFO, f"Starting API server on {host}:{port}")
    app = create_app(agent_options=agent_options or {})
    uvicorn.run(app, host=host, port=port, log_level="info", access_log=True)


def start_web_server(
    api_host: str = "localhost",
    api_port: int = 8000,
    background: bool = False,
    agent_options: Optional[dict[str, Any]] = None,
) -> Optional[multiprocessing.Process]:
    api_url = f"http://{api_host}:{api_port}"

    if background:
        api_process = multiprocessing.Process(
            target=run_api_server,
            args=(api_host, api_port, agent_options),
        )
        try:
            console.print("Запуск API сервера в фоновом режиме...")
            api_process.start()
            console.print(f"API доступно на: {api_url}")
            return api_process
        except Exception as e:
            log(logging.ERROR, f"Ошибка запуска сервера: {e}")
            api_process.terminate()
            return None

    try:
        console.print("Запуск API сервера...")
        console.print(f"API будет доступно на: {api_url}")
        console.print("Нажмите Ctrl+C для остановки")
        run_api_server(api_host, api_port, agent_options)
    except KeyboardInterrupt:
        console.print("\nОстановка сервера...")

    return None


def main() -> None:
    run_api_server()
