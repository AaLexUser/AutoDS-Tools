from __future__ import annotations

from typing import List, Type

from langchain_core.messages import HumanMessage

from autods.tools.base import BaseTool, BaseToolCall


class Toolkit:
    def __init__(self, *tools: BaseTool):
        self.tools: list[BaseTool] = list(tools)
        self.tool_map = {tool.name: tool for tool in self.tools}

    def __iter__(self):
        return iter(self.tools)

    def get_available_tools_prompt(
        self, exclude: List[Type[BaseTool]] = [], include: List[Type[BaseTool]] = []
    ) -> str:
        return "\n\n".join(
            tool.get_prompt()
            for tool in self.tools
            if not isinstance(tool, tuple(exclude))
            and (not include or isinstance(tool, tuple(include)))
        )

    async def execute(self, call: BaseToolCall) -> HumanMessage:
        tool = self.tool_map.get(call.name)
        if not tool:
            available_tools_str = " ".join([f"<{tool.name}/>" for tool in self.tools])
            return HumanMessage(
                content=f"Unknown tool(s): {call.name}\n\n"
                f"Available tools:\n{available_tools_str}"
            )
        try:
            result = await tool(**call.params)
            return result
        except Exception as e:
            return HumanMessage(content=str(e))
