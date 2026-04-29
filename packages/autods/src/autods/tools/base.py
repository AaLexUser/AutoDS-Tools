from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field


class ToolError(Exception):
    """Base class for tool errors."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message: str = message


class Observation(BaseModel):
    """Represents the result of a tool execution."""

    is_success: bool = Field(default=True)
    message: str = Field(default="")
    base64_images: Optional[List[str]] = Field(default=None)


class BaseToolCall(BaseModel):
    name: str
    params: Dict[str, Any]


class BaseTool(ABC, BaseModel):
    name: str
    usage: str = Field(default="", description="Usage example of the tool.")

    @abstractmethod
    def get_prompt(self) -> str:
        """Return the prompt of the tool."""

    def success_response(self, result: str) -> HumanMessage:
        """Return the response of the tool."""
        return HumanMessage(content=result, role="tool")

    def error_response(self, error: str) -> HumanMessage:
        """Return the error response of the tool."""
        return HumanMessage(
            content=(f"[ERROR] FIX and TRY again\n{error}\n[DEBUG OPTIONS]: \nA. Python `help()`"),
            role="tool",
        )

    async def __call__(
        self,
        **kwargs,
    ) -> Any:
        """Execute the tool with given parameters. With error handling."""
        try:
            message = await self.execute(**kwargs)
            if isinstance(message, str):
                return self.success_response(message)
            elif isinstance(message, HumanMessage):
                return message
        except Exception as e:
            return self.error_response(str(e))

    @abstractmethod
    async def execute(self, **kwargs) -> str | HumanMessage:
        """Execute the tool with given parameters."""
