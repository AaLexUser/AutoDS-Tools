from pathlib import Path

from langchain_core.messages import HumanMessage
from langgraph.runtime import get_runtime
from pydantic import Field

from autods.prompting.prompt_store import prompt_store
from autods.tools.base import BaseTool, ToolError


class SubmitTool(BaseTool):
    name: str = "submit"
    validate_imports: bool = Field(
        default=False,
        description="Whether to validate that code_path imports required AutoML libraries",
    )

    def get_prompt(self) -> str:
        return prompt_store.load("tools/submit.md")

    async def execute(self, **kwargs) -> str | HumanMessage:
        # Support both old format (arg) and new structured format (summary + code_path)
        summary = kwargs.get("summary") or kwargs.get("arg")
        code_path = kwargs.get("code_path")

        # Validate summary
        if not isinstance(summary, str) or not summary.strip():
            raise ToolError(
                "Parameter 'summary' is required and must be a non-empty string. "
                "Provide a presentation of your work and final message."
            )

        # If validation is enabled, check code_path
        if self.validate_imports:
            if not code_path or not isinstance(code_path, str) or not code_path.strip():
                raise ToolError(
                    "Parameter 'code_path' is required when import validation is enabled. "
                    "Provide the path to your solution file for reproducibility."
                )

            # Get project path from runtime context to resolve relative paths
            runtime = get_runtime()
            context = getattr(runtime, "context", None)
            if context is None:
                raise ToolError("No runtime context available for path resolution")

            project_path = getattr(context, "project_path", None)
            if not project_path:
                raise ToolError("Project path not available in runtime context")

            # Resolve the code path relative to project
            resolved_path = Path(project_path) / code_path
            if not resolved_path.is_absolute():
                resolved_path = resolved_path.resolve()

        # Format success message
        result = f"Task completed successfully.\n\n{summary.strip()}"
        if code_path:
            result += f"\n\nSolution file: {code_path}"

        return result
