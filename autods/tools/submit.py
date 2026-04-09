from langchain_core.messages import HumanMessage

from autods.prompting.prompt_store import prompt_store
from autods.tools.base import BaseTool, ToolError


class SubmitTool(BaseTool):
    name: str = "submit"

    def get_prompt(self) -> str:
        return prompt_store.load("tools/submit.md")

    async def execute(self, **kwargs) -> str | HumanMessage:
        # Support both old format (arg) and new structured format (summary + code_path)
        summary = kwargs.get("summary") or kwargs.get("arg")
        code_path = kwargs.get("code_path")

        if not isinstance(summary, str) or not summary.strip():
            raise ToolError(
                "Parameter 'summary' is required and must be a non-empty string. "
                "Provide a presentation of your work and final message."
            )

        result = f"Task completed successfully.\n\n{summary.strip()}"
        if code_path:
            result += f"\n\nSolution file: {code_path}"

        return result
