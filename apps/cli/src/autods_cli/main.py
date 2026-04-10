import asyncio
import os
import sys
import traceback
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

import click
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from pydantic import BaseModel
from rich.console import Console
from rich.prompt import Prompt
from rich.table import Table

from autods.agents.autods.autods import AutoDSAgent
from autods.agents.base import BaseAgent
from autods.callbacks.printer import MessageStreamPrinter
from autods.callbacks.tracer import Tracer
from autods.runtime.runner import AgentRunner
from autods.sessions import SessionMetadata, SessionNotFoundError, SessionService
from autods.utils.config import load_config
from autods_web.server import start_web_server

_ = load_dotenv()

console = Console()


class AgentCLIOptions(BaseModel):
    provider: Optional[str]
    model: Optional[str]
    model_base_url: Optional[str]
    api_key: Optional[str]
    max_steps: Optional[int]
    project_path: Optional[str]
    config_file: Optional[str]
    trace_debug: bool = False
    trace_file: Optional[str] = None

    @staticmethod
    def agent_options(func: Callable[..., Any]) -> Callable[..., Any]:
        options = [
            click.option("--provider", "-p", help="LLM provider to use"),
            click.option("--model", "-m", help="Specific model to use"),
            click.option("--model-base-url", help="Base URL for the model API"),
            click.option("--api-key", "-k", help="API key override"),
            click.option(
                "--max-steps", type=int, help="Maximum LangGraph recursion steps"
            ),
            click.option(
                "--config-file",
                help="Path to configuration file",
            ),
            click.option(
                "--trace-debug",
                is_flag=True,
                help="Capture LangGraph debug events into a tracing YAML file.",
            ),
            click.option(
                "--trace-file",
                type=click.Path(dir_okay=False, path_type=Path),
                help="Destination file for debug tracing output.",
            ),
        ]
        for option in reversed(options):
            func = option(func)
        return func

    @classmethod
    def from_args(cls, kwargs: dict[str, Any]) -> "AgentCLIOptions":
        def _normalize(value: Any) -> Any:
            if value is None:
                return None
            if isinstance(value, (str, Path, os.PathLike)):
                return str(value)
            if hasattr(value, "__class__") and value.__class__.__name__ == "Sentinel":
                return None
            return value

        return AgentCLIOptions(
            provider=_normalize(kwargs.get("provider")),
            model=_normalize(kwargs.get("model")),
            model_base_url=_normalize(kwargs.get("model_base_url")),
            api_key=_normalize(kwargs.get("api_key")),
            max_steps=_normalize(kwargs.get("max_steps")),
            project_path=_normalize(kwargs.get("project_path")),
            config_file=_normalize(kwargs.get("config_file")),
            trace_debug=bool(kwargs.get("trace_debug", False)),
            trace_file=_normalize(kwargs.get("trace_file")),
        )


def _load_app_config(cli_opts: AgentCLIOptions):
    return load_config(
        provider=cli_opts.provider,
        model=cli_opts.model,
        model_base_url=cli_opts.model_base_url,
        api_key=cli_opts.api_key,
        max_steps=cli_opts.max_steps,
        config_file=cli_opts.config_file,
    )


def _build_runner(
    cli_opts: AgentCLIOptions, session: SessionMetadata, agent: BaseAgent
) -> AgentRunner:
    """Create an AgentRunner with configured settings."""
    recursion_limit = cli_opts.max_steps or 200
    return AgentRunner(
        agent=agent,
        project_path=cli_opts.project_path,
        recursion_limit=recursion_limit,
        session=session,
    )


def _build_tracer(cli_opts: AgentCLIOptions) -> Tracer | None:
    """Create tracer if debug tracing is enabled."""
    if not cli_opts.trace_debug and not cli_opts.trace_file:
        return None
    trace_path = cli_opts.trace_file
    return Tracer(trace_path) if trace_path else Tracer()


def _build_stream_callbacks(
    stream_printer: MessageStreamPrinter, tracer: Tracer | None
) -> list[Callable[[str, Any], Awaitable[None]]]:
    """Build stream callbacks for agent execution."""
    callbacks: list[Callable[[str, Any], Awaitable[None]]] = [
        stream_printer.print_chunk_callback
    ]
    if tracer is not None:
        callbacks.append(tracer.tracing_callback)
    return callbacks


def _setup_common_components(cli_opts: AgentCLIOptions):
    """Setup common CLI components: stream printer, tracer, session service."""
    stream_printer = MessageStreamPrinter()
    tracer = _build_tracer(cli_opts)
    session_service = SessionService()

    if tracer is not None:
        console.print(
            f"[blue]Debug tracing enabled:[/blue] {tracer.file_path}", soft_wrap=True
        )

    return stream_printer, tracer, session_service


def _get_or_create_session(
    session_id: Optional[str], session_service: SessionService
) -> SessionMetadata:
    """Get existing session or create new one."""
    if session_id:
        try:
            return session_service.get_session(session_id)
        except SessionNotFoundError as exc:
            raise click.ClickException(f"Session not found: {session_id}") from exc
    return session_service.create_session()


def _handle_task_input(task: Optional[str], file_path: Optional[str]) -> str:
    """Handle task input from argument or file."""
    if file_path and task:
        raise click.ClickException("Provide either inline task or --file, not both")

    if file_path:
        try:
            return Path(file_path).read_text().strip()
        except FileNotFoundError as exc:
            raise click.ClickException(f"File not found: {file_path}") from exc

    if not task:
        raise click.ClickException("Task is required")

    return task


# ==============================================================================
# Common CLI options
# ==============================================================================


def common_options(func: Callable[..., Any]) -> Callable[..., Any]:
    """Add common CLI options that are shared across commands."""
    options = [
        click.option(
            "--file",
            "-f",
            "file_path",
            help="Path to file containing the task/input description.",
        ),
        click.option(
            "--project-path", "-w", help="Project workspace path for the agent."
        ),
    ]
    for option in reversed(options):
        func = option(func)
    return func


# ==============================================================================
# Async execution helpers
# ==============================================================================


async def _display_history(
    runner: AgentRunner,
    stream_printer: MessageStreamPrinter,
    user_message: str | None = None,
):
    """Display conversation history and optionally add user message."""
    state = await runner.get_state()
    messages = state.values.get("messages") or []
    if user_message:
        messages.append(HumanMessage(content=user_message))
    for msg in messages:
        stream_printer.handle(msg)


async def _run_chat_loop(
    runner: AgentRunner,
    stream_printer: MessageStreamPrinter,
    session_service: SessionService,
    session: SessionMetadata,
    tracer: Tracer | None,
) -> None:
    """Run interactive chat loop with error handling."""
    try:
        while True:
            # Run blocking prompt in a thread to avoid blocking the event loop
            message = await asyncio.to_thread(Prompt.ask, ">")
            if not isinstance(message, str):
                continue

            user_msg = HumanMessage(content=message)
            stream_printer.handle(user_msg)
            await runner.astream(
                message,
                callbacks=_build_stream_callbacks(stream_printer, tracer),
                debug=tracer is not None,
            )
    except KeyboardInterrupt:
        console.print("\n[yellow]Task execution interrupted by user[/yellow]")
        console.print(f"\n[green]To resume run: autods resume {session.id}[/green]")
        sys.exit(1)
    except Exception as e:
        console.print(f"\n[red]Unexpected error: {e}[/red]")
        console.print(traceback.format_exc())
        sys.exit(1)
    finally:
        session_service.upsert_session(session)
        stream_printer.flush()


async def _execute_with_handling(
    coro,
    session_service: SessionService,
    session: SessionMetadata,
    stream_printer: MessageStreamPrinter,
    session_id_for_resume: Optional[str] = None,
):
    """Common async execution with error handling and cleanup."""
    try:
        return await coro
    except KeyboardInterrupt:
        console.print("\n[yellow]Task execution interrupted by user[/yellow]")
        if session_id_for_resume:
            console.print(
                f"\n[green]To resume run: autods resume {session_id_for_resume}[/green]"
            )
        sys.exit(1)
    except Exception as e:
        console.print(f"\n[red]Unexpected error: {e}[/red]")
        console.print(traceback.format_exc())
        sys.exit(1)
    finally:
        session_service.upsert_session(session)
        stream_printer.flush()


@click.group(invoke_without_command=True)
@click.version_option(version="0.1.0")
@click.pass_context
def cli(ctx: click.Context) -> None:
    """Autods Agent - LLM-based agent for automl tasks."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(chat)


# ==============================================================================
# CLI Commands
# ==============================================================================


@AgentCLIOptions.agent_options
@common_options
@cli.command()
@click.argument("task", required=False)
@click.option(
    "--session-id", help="Resume execution using the specified session identifier."
)
def exec(
    task: str | None, file_path: str | None, session_id: str | None, **kwargs: Any
):
    """Execute a single AutoDS task."""
    cli_opts = AgentCLIOptions.from_args(kwargs)
    stream_printer, tracer, session_service = _setup_common_components(cli_opts)

    inline_task = _handle_task_input(task, file_path)
    selected_session = _get_or_create_session(session_id, session_service)

    app_config = _load_app_config(cli_opts)
    agent = AutoDSAgent(app_config, cli_opts.project_path)
    runner = _build_runner(cli_opts, selected_session, agent)

    async def _exec_task():
        await _display_history(
            runner=runner, stream_printer=stream_printer, user_message=inline_task
        )
        await runner.astream(
            inline_task,
            callbacks=_build_stream_callbacks(stream_printer, tracer),
            debug=tracer is not None,
        )

    asyncio.run(
        _execute_with_handling(
            _exec_task(),
            session_service,
            selected_session,
            stream_printer,
            selected_session.id,
        )
    )


@AgentCLIOptions.agent_options
@cli.command()
def chat(**kwargs: Any):
    """Start an interactive chat session with AutoDS agent."""
    cli_opts = AgentCLIOptions.from_args(kwargs)
    stream_printer, tracer, session_service = _setup_common_components(cli_opts)

    # Create new session for chat
    session = session_service.create_session()

    # Initialize agent and runner
    app_config = _load_app_config(cli_opts)
    agent = AutoDSAgent(app_config, cli_opts.project_path)
    runner = _build_runner(cli_opts, session, agent)

    async def _chat_session() -> None:
        await _display_history(runner=runner, stream_printer=stream_printer)
        await _run_chat_loop(
            runner=runner,
            stream_printer=stream_printer,
            session_service=session_service,
            session=session,
            tracer=tracer,
        )

    asyncio.run(_chat_session())


def _print_sessions_table(sessions: list[SessionMetadata]) -> None:
    table = Table(title="Saved sessions")
    table.add_column("#", style="cyan", justify="right")
    table.add_column("Session ID", style="green")
    table.add_column("Created")
    table.add_column("Updated")
    for idx, session in enumerate(sessions, start=1):
        table.add_row(
            str(idx),
            session.id,
            session.created_at.strftime("%H:%M:%S %d/%m/%Y"),
            session.updated_at.strftime("%H:%M:%S %d/%m/%Y"),
        )
    console.print(table)


def _prompt_for_session_selection(
    sessions: list[SessionMetadata],
) -> SessionMetadata:
    if not sessions:
        raise click.ClickException("No sessions available to resume")
    max_display = min(len(sessions), 10)
    display_sessions = sessions[:max_display]
    _print_sessions_table(display_sessions)
    choice = Prompt.ask(
        "Select session", choices=[str(i) for i in range(1, max_display + 1)]
    )
    return display_sessions[int(choice) - 1]


@AgentCLIOptions.agent_options
@common_options
@cli.command()
@click.argument("session_id", required=False)
def resume(session_id: Optional[str], **kwargs: Any):
    """Resume an existing session or start new chat session."""
    cli_opts = AgentCLIOptions.from_args(kwargs)
    stream_printer, tracer, session_service = _setup_common_components(cli_opts)

    # Get sessions list and handle selection
    sessions = session_service.list_sessions()
    if not sessions:
        raise click.ClickException("No sessions available to resume")

    if session_id:
        session = _get_or_create_session(session_id, session_service)
    else:
        session = _prompt_for_session_selection(sessions)

    # Initialize agent and runner
    app_config = _load_app_config(cli_opts)
    agent = AutoDSAgent(app_config, cli_opts.project_path)
    runner = _build_runner(cli_opts, session, agent)

    async def _resume_session() -> None:
        await _display_history(runner=runner, stream_printer=stream_printer)
        await _run_chat_loop(
            runner=runner,
            stream_printer=stream_printer,
            session_service=session_service,
            session=session,
            tracer=tracer,
        )

    asyncio.run(_resume_session())


@AgentCLIOptions.agent_options
@cli.command()
@click.option("--api-host", default="localhost", help="API server host")
@click.option("--api-port", default=8000, type=int, help="API server port")
@click.option("--background", is_flag=True, help="Run API server in background")
def web(api_host: str, api_port: int, background: bool, **kwargs):
    cli_opts = AgentCLIOptions.from_args(kwargs)

    agent_options = {
        "provider": cli_opts.provider,
        "model": cli_opts.model,
        "model_base_url": cli_opts.model_base_url,
        "api_key": cli_opts.api_key,
        "max_steps": cli_opts.max_steps,
        "config_file": cli_opts.config_file,
        "project_path": cli_opts.project_path,
    }
    agent_options = {k: v for k, v in agent_options.items() if v is not None}

    if background:
        proc = start_web_server(
            api_host,
            api_port,
            background=True,
            agent_options=agent_options,
        )
        if proc:
            console.print("API сервер запущен в фоновом режиме")
            console.print(f"API: http://{api_host}:{api_port}")
            console.print("\nИспользуйте команды системы для остановки процесса")
        else:
            console.print("[red]Ошибка запуска API сервера[/red]")
            sys.exit(1)
    else:
        start_web_server(
            api_host,
            api_port,
            background=False,
            agent_options=agent_options,
        )


def main():
    """Entry point for the autods CLI."""
    cli()
