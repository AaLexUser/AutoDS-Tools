from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar, cast

from langgraph.runtime import Runtime
from langgraph.types import Command
from langgraph.typing import ContextT

from autods.agents.domain import BaseAgentContext

StateT = TypeVar("StateT")
TaskContextT = TypeVar("TaskContextT", bound=BaseAgentContext)


class TaskInference(ABC, Generic[StateT, TaskContextT]):
    @property
    @abstractmethod
    def context_type(self) -> type[TaskContextT]:
        """Return the expected context type for this task."""
        ...

    # Subclasses should override when they want the framework to coerce
    # incoming dict states (from LangGraph) into typed Pydantic models.
    @property
    def state_type(self) -> type[StateT] | None:
        return None

    async def runnable(
        self, state: StateT, runtime: Runtime[ContextT]
    ) -> StateT | Command[Any]:
        """Adapter wrapper called by LangGraph for each node.

        LangGraph commonly passes the state around as a plain dict even when a
        schema is provided. Many of our task nodes operate on typed Pydantic
        state models. To make both call styles work, transparently coerce dict
        inputs into the declared ``state_type`` when available.
        """
        context = self._ensure_context(runtime)
        return await self._runnable(cast(StateT, state), context)

    async def _runnable(
        self, state: StateT, context: TaskContextT
    ) -> StateT | Command[Any]:
        raise NotImplementedError()

    def _ensure_context(self, runtime: Runtime[ContextT]) -> TaskContextT:
        runtime_context = getattr(runtime, "context", None)
        if runtime_context is None:
            raise RuntimeError(
                f"{self.context_type.__name__} runtime context is not configured."
            )
        if not isinstance(runtime_context, self.context_type):
            raise RuntimeError(
                f"Expected runtime context of type {self.context_type.__name__}, "
                f"got {type(runtime_context).__name__}."
            )
        return cast(TaskContextT, runtime_context)
