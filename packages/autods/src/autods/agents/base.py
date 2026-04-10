from abc import ABC, abstractmethod
from typing import Any, Optional

from langchain.tools import StructuredTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import StateGraph
from langgraph.graph.state import CompiledStateGraph

from autods.utils.config import Config


class BaseAgent(ABC):
    def __init__(self, config: Config):
        self.config = config
        self._compiled: CompiledStateGraph | None = None

    def _compile_workflow(
        self,
        workflow: StateGraph[Any, Any, Any, Any],
        checkpointer: BaseCheckpointSaver[Any] | None = None,
    ) -> CompiledStateGraph:
        if checkpointer is not None:
            return workflow.compile(checkpointer=checkpointer)
        return workflow.compile()

    @abstractmethod
    def runnable(
        self, checkpointer: BaseCheckpointSaver[Any] | None = None
    ) -> CompiledStateGraph[Any, Any, Any, Any]:
        """Return the compiled state graph for the agent."""

    def as_tool(
        self, checkpointer: BaseCheckpointSaver[Any] | None = None
    ) -> StructuredTool:
        """Return an asynchronous runnable tool for the agent."""
        raise NotImplementedError

    def get_mermaid_png(self, filename: Optional[str] = None) -> bytes:
        """Generate a Mermaid diagram PNG of the agent's workflow."""
        workflow = self.runnable(checkpointer=None)
        return workflow.get_graph().draw_mermaid_png(output_file_path=filename)
