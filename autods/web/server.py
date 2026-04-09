import logging
import multiprocessing
import os
import subprocess
import sys
import time
from logging import log
from pathlib import Path
from typing import Any, Optional

import uvicorn
from rich.console import Console

# from autods.utils.logging import get_log
from autods.web.api import create_app

# log = get_log(__name__)
console = Console()


def run_api_server(
    host: str = "localhost",
    port: int = 8000,
    agent_options: Optional[dict[str, Any]] = None,
):
    log(logging.INFO, f"Starting API server on {host}:{port}")
    app = create_app(agent_options=agent_options or {})
    uvicorn.run(app, host=host, port=port, log_level="info", access_log=True)


def run_streamlit_server(port: int = 8501, api_url: str = "http://localhost:8000"):
    time.sleep(2)
    log(logging.INFO, f"Starting Streamlit server on port {port}")
    streamlit_file = Path(__file__).parent / "streamlit_app.py"

    # Передаем API_BASE_URL через переменную окружения
    env = os.environ.copy()
    env.update({"STREAMLIT_SERVER_PORT": str(port), "API_BASE_URL": api_url})

    subprocess.run(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(streamlit_file),
            "--server.port",
            str(port),
            "--server.address",
            "localhost",
        ],
        env=env,
    )


def start_web_servers(
    api_host: str = "localhost",
    api_port: int = 8000,
    streamlit_port: int = 8501,
    background: bool = False,
    agent_options: Optional[dict[str, Any]] = None,
) -> Optional[tuple]:
    # Формируем правильный API URL
    api_url = f"http://{api_host}:{api_port}"

    if background:
        api_process = multiprocessing.Process(
            target=run_api_server,
            args=(api_host, api_port, agent_options),
        )
        streamlit_process = multiprocessing.Process(
            target=run_streamlit_server, args=(streamlit_port, api_url)
        )

        try:
            console.print("Запуск API сервера в фоновом режиме...")
            api_process.start()
            console.print("Запуск Streamlit интерфейса в фоновом режиме...")
            streamlit_process.start()
            console.print(f"API доступно на: {api_url}")
            console.print(f"Streamlit доступен на: http://localhost:{streamlit_port}")
            return api_process, streamlit_process
        except Exception as e:
            log(logging.ERROR, f"Ошибка запуска серверов: {e}")
            if "api_process" in locals():
                api_process.terminate()
            if "streamlit_process" in locals():
                streamlit_process.terminate()
            return None
    else:
        try:
            console.print("Запуск серверов в интерактивном режиме...")
            console.print(f"API будет доступно на: {api_url}")
            console.print(
                f"Streamlit будет доступен на: http://localhost:{streamlit_port}"
            )
            console.print("Нажмите Ctrl+C для остановки")

            api_process = multiprocessing.Process(
                target=run_api_server,
                args=(api_host, api_port, agent_options),
            )
            streamlit_process = multiprocessing.Process(
                target=run_streamlit_server, args=(streamlit_port, api_url)
            )

            api_process.start()
            streamlit_process.start()
            api_process.join()
            streamlit_process.join()
        except KeyboardInterrupt:
            console.print("\nОстановка серверов...")
            api_process.terminate()
            streamlit_process.terminate()
        except Exception as e:
            log(logging.ERROR, f"Ошибка: {e}")
            api_process.terminate()
            streamlit_process.terminate()
