"""Reusable Think-Act agent builder for composable LangGraph workflows."""

import time
from typing import Any, Callable, Generic, TypeVar, cast

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, RemoveMessage
from langgraph.graph import END
from langgraph.types import Command

from autods.agents.domain import BaseAgentState, BaseThinkActAgent
from autods.prompting.prompt_generator import PromptGenerator
from autods.task_inference.base import TaskInference
from autods.tools.toolkit import Toolkit
from autods.utils.parse_tools import parse_tools_from_message
from autods.utils.system_resources import get_system_info

StateT = TypeVar("StateT", bound=BaseAgentState)
ContextT = TypeVar("ContextT", bound=BaseThinkActAgent)

VerificationFn = Callable[[str], tuple[bool, str | None]]

# Shared state keys for Think/Act coordination
_ORIGINAL_HISTORY_KEY = "original_history"
_AGENT_START_INDEX_KEY = "agent_start_index"


def _create_remove_messages(messages: list[BaseMessage]) -> list[RemoveMessage]:
    """Create RemoveMessage commands for all messages with IDs."""
    return [RemoveMessage(id=msg.id) for msg in messages if hasattr(msg, "id") and msg.id]


class ThinkActAgent(TaskInference[StateT, ContextT], Generic[StateT, ContextT]):
    def __init__(
        self,
        prompt_generator: PromptGenerator,
        toolkit: Toolkit,
        context_type: type[ContextT],
        state_type: type[StateT],
        throw_history: bool = False,
        verificate_fn: VerificationFn | None = None,
        max_steps: int = 50,
        prefix: str = "",
        next_node: str = END,
        last_messages_cnt: int = -1,
        shared_state: dict[str, Any] | None = None,
    ):
        self.prompt_generator = prompt_generator
        self.toolkit = toolkit
        self.max_steps = max_steps
        self._context_type = context_type
        self._state_type = state_type
        self.throw_history = throw_history
        self.verificate_fn = verificate_fn
        self.prefix = prefix
        self._step_count = 0
        self.act_node = f"{prefix}act"
        self.think_node = f"{prefix}think"
        self.next_node = next_node
        self.last_messages_cnt = last_messages_cnt
        self._shared = shared_state if shared_state is not None else {}

    @property
    def context_type(self) -> type[ContextT]:
        return self._context_type

    @property
    def state_type(self) -> type[StateT]:
        return self._state_type


class Think(ThinkActAgent[StateT, ContextT]):
    def add_extra_info(self, history: list, context: ContextT):
        if not history:
            return
        new_history = list(history)
        last_message = new_history[-1]
        session_time_sec = time.perf_counter() - context.start_time
        session_time = f"{int(session_time_sec // 60)}m {int(session_time_sec % 60)}s"
        if isinstance(last_message, HumanMessage):
            turn_info = {
                "system_info": get_system_info(),
                "session_time": session_time,
                "steps": f"{self._step_count}/{self.max_steps}",
            }
            new_history[-1] = HumanMessage(content=str(last_message.content) + f"\n{turn_info}")
        return new_history

    async def _runnable(self, state: StateT, context: ContextT) -> StateT | Command[Any]:
        messages: list[BaseMessage] = state.messages

        if _ORIGINAL_HISTORY_KEY not in self._shared:
            self._shared[_ORIGINAL_HISTORY_KEY] = messages.copy()
            self._shared[_AGENT_START_INDEX_KEY] = len(messages)

            if self.last_messages_cnt > 0:
                if len(messages) > self.last_messages_cnt:
                    state.replace_messages(state.messages_tail(self.last_messages_cnt))
                    return Command(goto=self.think_node, update={"messages": state.messages})

        # Run initial messages prompt
        response = self.prompt_generator.get_next_initial_message_prompt()
        if response is not None:
            return Command(
                update={"messages": state.append_messages([response])},
                goto=self.act_node,
            )

        history_with_extra = self.add_extra_info(messages, context)
        prompt = self.prompt_generator.react_prompt(history_with_extra)

        try:
            response = await context.llm_client.ainvoke(prompt)
        except ValueError as e:
            if "No generations found in stream" in str(e):
                return Command(goto=END)
            raise

        self._step_count += 1
        return Command(
            update={"messages": state.append_messages([response])},
            goto=self.act_node,
        )


class Act(ThinkActAgent[StateT, ContextT]):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._initial_message_count = None

    def set_initial_message_count(self, count: int) -> None:
        if self._initial_message_count is None:
            self._initial_message_count = count

    def _build_termination_output(self, state: StateT, artifact: str) -> list[BaseMessage | RemoveMessage]:
        """Build the final message output when agent terminates."""
        messages: list[BaseMessage] = state.messages
        artifact_message = HumanMessage(content=artifact)

        # Restore initial messages index
        self.prompt_generator.reset_initial_message_index()

        # Simple case: no history restoration needed
        if _ORIGINAL_HISTORY_KEY not in self._shared:
            if self.throw_history:
                messages_to_remove = _create_remove_messages(messages[self._initial_message_count :])
                return messages_to_remove + [artifact_message]
            return [artifact_message]

        # History restoration case
        restored_history = cast(list[BaseMessage], self._shared[_ORIGINAL_HISTORY_KEY])

        if self.last_messages_cnt > 0:
            # Truncated history: agent messages are after truncation point
            agent_messages = list(messages[self.last_messages_cnt :])
            state.replace_messages(restored_history)

            if self.throw_history:
                state.append_messages([artifact_message])
            else:
                state.append_messages(agent_messages)
            return list(state.messages)

        if self.throw_history:
            state.replace_messages(restored_history)
            state.append_messages([artifact_message])
            return list(state.messages)
        else:
            agent_messages = list(messages[self._shared[_AGENT_START_INDEX_KEY] :])
            state.replace_messages(restored_history)
            state.append_messages(agent_messages)
            return list(state.messages)

    def _reset_state(self) -> None:
        """Reset all agent state for next run."""
        self._step_count = 0
        self._initial_message_count = None
        self._shared.pop(_ORIGINAL_HISTORY_KEY, None)
        self._shared.pop(_AGENT_START_INDEX_KEY, None)

    async def _runnable(self, state: StateT, context: ContextT) -> StateT | Command[Any]:
        messages: list[BaseMessage] = state.messages

        self.set_initial_message_count(len(messages) - 1)
        self._step_count += 1

        last_message = messages[-1]
        if not isinstance(last_message, AIMessage):
            return Command(
                goto=self.think_node,
                update={
                    "messages": state.append_messages(
                        [
                            HumanMessage(
                                content="[ERROR] Expected AIMessage from Think phase, got "
                                f"{type(last_message).__name__}. Continuing..."
                            )
                        ]
                    )
                },
            )

        text = last_message.content if isinstance(last_message.content, str) else ""

        if "TERMINATE" in text or (self._step_count > self.max_steps + 3):
            artifact = text.replace("<TERMINATE>", "").replace("</TERMINATE>", "").replace("TERMINATE", "").strip()

            if self.verificate_fn is not None:
                is_valid, error_message = self.verificate_fn(artifact)
                if not is_valid:
                    error_content = (
                        f"[VERIFICATION ERROR] The submitted artifact did not pass verification.\n\n"
                        f"{error_message or 'No error details provided.'}\n\n"
                        f"Please fix the issues and try again."
                    )
                    return Command(
                        goto=self.think_node,
                        update={"messages": state.append_messages([HumanMessage(content=error_content)])},
                    )

            output = self._build_termination_output(state, artifact)
            self._reset_state()
            return Command(goto=self.next_node, update={"messages": output})

        if self._step_count > self.max_steps:
            return Command(
                goto=self.think_node,
                update={
                    "messages": state.append_messages(
                        [
                            HumanMessage(
                                content=f"[ERROR] Max steps ({self.max_steps}) reached. "
                                "Return your task artifact message (Report) and <TERMINATE> at the end of the message."
                            )
                        ]
                    )
                },
            )

        calls = parse_tools_from_message(text)

        if len(calls) > 1:
            return Command(
                goto=self.think_node,
                update={
                    "messages": state.append_messages(
                        [
                            HumanMessage(
                                content="[ERROR] Multiple tool calls found. Only one tool call per turn is allowed."
                            )
                        ]
                    )
                },
            )

        if len(calls) == 0:
            tool_list = ", ".join(f"<{tool.name}/>: {tool.usage}" for tool in self.toolkit.tools)
            return Command(
                goto=self.think_node,
                update={
                    "messages": state.append_messages(
                        [HumanMessage(content=f"[ERROR] No tool calls found. Available tools: {tool_list}")]
                    )
                },
            )

        call = calls[0]
        response = await self.toolkit.execute(call=call)

        return Command(
            goto=self.think_node,
            update={"messages": state.append_messages([response])},
        )


def create_think_act_agent(
    prompt_generator: PromptGenerator,
    toolkit: Toolkit,
    state_type: type[StateT],
    context_type: type[ContextT],
    max_steps: int = 50,
    throw_history: bool = False,
    verificate_fn: VerificationFn | None = None,
    prefix: str = "",
    next_node: str = END,
    last_messages_cnt: int = -1,
) -> tuple[Any, Any]:
    """Create Think and Act runnables for integration into any LangGraph workflow.

    Args:
        prompt_generator: PromptGenerator instance to create LLM prompts.
        toolkit: Toolkit instance containing available tools for execution.
        max_steps: Maximum number of Think-Act iterations before forced termination.
        throw_history: If True, remove all intermediate messages on termination.
        verificate_fn: Optional validation function called when <TERMINATE> tag is detected.
            Returns (is_valid: bool, error_message: str | None).
        context_type: The Context class for the agent.
        prefix: Optional prefix for node names (e.g., "research_" -> "research_think", "research_act").
        last_messages_cnt: Number of messages to keep from history at start. Use -1 (default) to disable truncation.
            If > 0, saves original history and truncates to last N messages for agent context.

    Returns:
        Tuple of (think_runnable, act_runnable) that can be added as nodes to any workflow.
        Node names should be f"{prefix}think" and f"{prefix}act".
    """

    # Create shared state dict for Think and Act nodes to share data
    shared_state: dict[str, Any] = {}

    think_node = Think[StateT, ContextT](
        prompt_generator=prompt_generator,
        toolkit=toolkit,
        max_steps=max_steps,
        throw_history=throw_history,
        verificate_fn=verificate_fn,
        state_type=state_type,
        context_type=context_type,
        prefix=prefix,
        next_node=next_node,
        last_messages_cnt=last_messages_cnt,
        shared_state=shared_state,
    )

    act_node = Act[StateT, ContextT](
        prompt_generator=prompt_generator,
        toolkit=toolkit,
        max_steps=max_steps,
        throw_history=throw_history,
        verificate_fn=verificate_fn,
        state_type=state_type,
        context_type=context_type,
        prefix=prefix,
        next_node=next_node,
        last_messages_cnt=last_messages_cnt,
        shared_state=shared_state,
    )

    return think_node.runnable, act_node.runnable
