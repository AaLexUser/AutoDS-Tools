import logging
import os
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterable, Literal, Sequence, cast

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from pydantic import BaseModel

from autods.agents.base import BaseAgent
from autods.constants import AUTO_DS_AGENT
from autods.sessions.domain import SessionMetadata

logger = logging.getLogger(__name__)

StreamCallback = Callable[[str, Any], Awaitable[None]]
StreamModeLiteral = Literal["values", "updates", "debug", "messages", "custom"]


class StreamResult(BaseModel):
    final_text: str
    messages: list[BaseMessage]
    user_message: HumanMessage


class AgentRunner:
    def __init__(
        self,
        agent: BaseAgent,
        project_path: str | None,
        session: SessionMetadata,
        recursion_limit: int,
    ) -> None:
        self.project_path = self._resolve_project_path(project_path)
        self.recursion_limit = recursion_limit
        self.session = session
        self.agent = agent

        self._config: RunnableConfig = {
            "recursion_limit": recursion_limit,
            "configurable": {"thread_id": session.id},
        }

    def _resolve_project_path(self, project_path: str | None) -> str:
        """Resolve and validate the project path, changing directory if needed."""
        if project_path:
            path = Path(project_path)
            should_chdir = True
        else:
            path = Path.cwd()
            should_chdir = False

        if not path.is_absolute():
            raise ValueError("Working directory must be an absolute path")

        if should_chdir:
            os.chdir(path)
            logger.info(f"Changed working directory to: {path}")

        return str(path)

    async def get_state(self):
        """Retrieve the current state of the agent."""
        try:
            async with AsyncSqliteSaver.from_conn_string(
                self.session.checkpoint_nsp
            ) as checkpointer:
                compiled = self.agent.runnable(checkpointer=checkpointer)
                return await compiled.aget_state(self._config)
        except Exception as exc:
            await self._safe_shutdown_on_error(exc)
            raise
        finally:
            await self._shutdown_async()

    def _get_stream_modes(self, debug: bool) -> list[StreamModeLiteral]:
        """Build the list of stream modes based on debug flag."""
        modes: list[StreamModeLiteral] = ["values", "updates", "custom", "messages"]
        if debug:
            modes.append("debug")
        return modes

    def _extract_final_text(self, last_msg: BaseMessage) -> str:
        """Extract text content from the last AI message."""
        if not isinstance(last_msg, AIMessage):
            return ""
        content = last_msg.content
        return content if isinstance(content, str) else str(content)

    async def astream(
        self,
        prompt: str,
        *,
        callbacks: Iterable[StreamCallback] | None = None,
        debug: bool = False,
    ) -> StreamResult:
        """Stream agent execution with the given prompt."""
        callbacks = list(callbacks or [])
        user_message = HumanMessage(content=prompt)
        final_text = ""
        final_messages: list[BaseMessage] = []
        stream_modes = self._get_stream_modes(debug)

        try:
            async with AsyncSqliteSaver.from_conn_string(
                self.session.checkpoint_nsp
            ) as checkpointer:
                compiled = self.agent.runnable(checkpointer=checkpointer)

                async for mode, chunk in compiled.astream(
                    input={"messages": [user_message]},
                    context=getattr(self.agent, "context", None),
                    config=self._config,
                    stream_mode=cast(Sequence[StreamModeLiteral], stream_modes),
                ):
                    for cb in callbacks:
                        await cb(mode, chunk)

                    if mode == "values" and isinstance(chunk, dict):
                        msgs = chunk.get("messages")
                        if isinstance(msgs, list) and msgs:
                            final_messages = msgs
                            final_text = self._extract_final_text(msgs[-1])

                    if mode == "custom" and isinstance(chunk, dict):
                        agent_chunk = chunk.get(AUTO_DS_AGENT)
                        if isinstance(agent_chunk, str):
                            final_text = agent_chunk
        finally:
            await self._shutdown_async()

        if not final_messages:
            final_messages = [user_message]

        return StreamResult(
            final_text=final_text, messages=final_messages, user_message=user_message
        )

    async def _shutdown_async(self) -> None:
        """Cleanup resources like persistent executors."""
        context = getattr(self.agent, "context", None)
        if context:
            executor = getattr(context, "jupyter_executor", None)
            if executor is not None:
                await executor.terminate()

    async def _safe_shutdown_on_error(self, exc: Exception) -> None:
        """Attempt to cleanup resources when an error occurs without masking the error.

        Ensures any async executors (e.g., Jupyter) are terminated before the exception
        propagates. Logs the error for visibility but does not raise.
        """
        try:
            logger.exception("Agent runner encountered an error: %s", exc)
            await self._shutdown_async()
        except Exception:
            # Suppress any secondary errors during shutdown to not hide the original
            logger.debug(
                "Suppressed error during shutdown after exception", exc_info=True
            )
