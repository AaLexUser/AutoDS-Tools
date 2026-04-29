from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage
from langgraph.runtime import get_runtime

from autods.environments.jupyter import JupyterExecutor
from autods.prompting.prompt_store import prompt_store
from autods.tools.base import BaseTool, Observation, ToolError


async def _observation_to_content(observation: Observation) -> list[str | dict]:
    """Convert an observation into LangChain content blocks."""
    message = (observation.message or "").strip()

    content: list[str | dict] = []
    if message:
        content.append({"type": "text", "text": message})

    for image in observation.base64_images or []:
        content.append({"type": "image_url", "image_url": {"url": image}})

    if not content:
        content.append({"type": "text", "text": "Notebook cell executed with no output."})
    return content


def _get_context() -> Any:
    """Fetch the current agent context from the running LangGraph runtime."""
    runtime = get_runtime()
    context = getattr(runtime, "context", None)
    if context is None:
        raise ToolError("Jupyter tool requires an agent context with workspace information.")
    return context


def _build_executor(project_path: Path, env_vars: dict[str, str] | None) -> JupyterExecutor:
    return JupyterExecutor(workspace=project_path, env_vars=env_vars)


def _get_executor(context: Any) -> JupyterExecutor:
    """Fetch or create the executor stored on the agent context."""
    executor = getattr(context, "jupyter_executor", None)
    if executor is not None:
        return executor

    project_path = Path(getattr(context, "project_path", Path.cwd()))
    project_path.mkdir(parents=True, exist_ok=True)

    env_vars = getattr(context, "python_env", None)
    executor = _build_executor(project_path, env_vars)
    try:
        context.jupyter_executor = executor  # type: ignore[attr-defined]
    except (AttributeError, TypeError):
        object.__setattr__(context, "jupyter_executor", executor)
    return executor


class IPythonTool(BaseTool):
    name: str = "jupyter"
    timeout: float | None = None

    def get_prompt(self) -> str:
        return prompt_store.load("tools/ipython.md")

    async def execute(self, **kwargs) -> HumanMessage:
        code = kwargs.get("arg")
        if not isinstance(code, str) or not code.strip():
            raise ToolError("Parameter 'code' is required and must be a non-empty string.")

        context = _get_context()
        executor = _get_executor(context)
        observation = await executor.run(code=code, timeout=self.timeout)

        if not observation.is_success:
            raise ToolError(observation.message or "Notebook execution failed.")

        return HumanMessage(
            content=await _observation_to_content(observation),
            role="tool",
        )
