import time
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END
from langgraph.types import Command

from autods.agents.autods.domain import AutoDSContext, AutoDSState
from autods.constants import (
    ANALYST_REPORT_PATH,
    AUTO_DS_AGENT,
    MULTI_TOOL_ERROR,
    PLANNER_REPORT_PATH,
    RESEARCHER_REPORT_PATH,
    TOOLS_NOT_FOUND_ERROR,
)
from autods.prompting.prompt_generator import (
    AutoDSPromptGenerator,
    PlannerOneShotPromptGenerator,
)
from autods.task_inference import TaskInference
from autods.utils.parse_tools import parse_tools_from_message
from autods.utils.system_resources import get_system_info


def _is_python_error(response_content: str) -> bool:
    """
    Detect if an error response is from Python code execution.
    """
    if not isinstance(response_content, str):
        return False

    # Check for Python-specific error patterns
    python_error_patterns = [
        "Traceback (most recent call last):",
        "Traceback",
        "Exception:",
        "Error:",
    ]
    has_traceback = any(
        pattern in response_content for pattern in python_error_patterns
    )

    return has_traceback


class AutoDSTaskInference(TaskInference[AutoDSState, AutoDSContext]):
    @property
    def context_type(self) -> type[AutoDSContext]:
        return AutoDSContext

    @property
    def state_type(self) -> type[AutoDSState]:
        return AutoDSState


class Think(AutoDSTaskInference):
    def __init__(self, prompt_generation: AutoDSPromptGenerator):
        self.prompt_generator = prompt_generation

    def add_extra_info(self, history: list, context: AutoDSContext):
        if not history:
            return
        new_histoty = history.copy()
        last_message = new_histoty[-1]
        session_time_sec = time.perf_counter() - context.start_time
        session_time = f"{int(session_time_sec // 60)}m {int(session_time_sec % 60)}s"
        system_info = get_system_info()
        if system_info.gpu.available:
            gpu_info = f"GPU: {system_info.gpu.count} {system_info.gpu.names} ({'MPS' if system_info.gpu.type == 'mps' else 'NVIDIA'})\n"
        else:
            gpu_info = ""
        avaliable_resurces = (
            f"CPU: {system_info.cpu_count} cores\n"
            f"{gpu_info}"
            f"Memory: {system_info.memory.available} GB available\n"
            f"OS: {system_info.os_system}\n"
        )
        avaliable_resurces_message = (
            f"--- All resources are reserved for your task. Maximize their utilization. ---\n"
            f"{avaliable_resurces}\n"
            f"Session time: {session_time}\n"
            f"--- End of resources usage info ---\n"
            f"--- cpu_limit=os.cpu_count(), memory_limit=psutil.virtual_memory().available ---\n"
        )
        if isinstance(last_message, HumanMessage):
            new_histoty[-1] = HumanMessage(
                content=str(last_message.content) + f"\n\n{avaliable_resurces_message}"
            )
        return new_histoty

    async def _runnable(
        self, state: AutoDSState, context: AutoDSContext
    ) -> AutoDSState | Command[Any]:
        # Run initial messages prompt
        response = self.prompt_generator.get_next_initial_message_prompt()
        if response is not None:
            return Command(
                update={"messages": state.append_messages([response])},
                goto="act",
            )

        history = state["messages"]
        history_with_extra = self.add_extra_info(history, context)

        prompt = self.prompt_generator.react_prompt(history_with_extra)

        try:
            response = await context.llm_client.ainvoke(prompt)
        except ValueError as e:
            if "No generations found in stream" in str(e):
                return Command(goto=END)
            raise

        return Command(
            update={"messages": state.append_messages([response])},
            goto="act",
        )


class Act(AutoDSTaskInference):
    async def _runnable(
        self, state: AutoDSState, context: AutoDSContext
    ) -> AutoDSState | Command[Any]:
        last_message = state["messages"][-1]
        if not isinstance(last_message, AIMessage):
            raise TypeError("Act expects the last message to be an AIMessage.")

        if not isinstance(last_message.content, str):
            raise ValueError(
                f"Expected string content, got {type(last_message.content)}"
            )
        text = last_message.content
        calls = parse_tools_from_message(text)

        if len(calls) == 1:
            response = await context.toolkit.execute(call=calls[0])

            should_route_to_debugger = False
            agent_config = context.config.agents.get(AUTO_DS_AGENT)
            debugger_steps = (
                getattr(agent_config, "debugger_steps", 0) if agent_config else 0
            )

            # Check if there's a Python error and debugger is configured
            response_content = (
                response.content if hasattr(response, "content") else str(response)
            )
            if not isinstance(response_content, str):
                response_content = str(response_content)
            if debugger_steps > 0 and _is_python_error(response_content):
                should_route_to_debugger = True

            if calls[0].name == "submit" and not "ERROR" in response.content:
                return Command(
                    goto="presenter_think",
                    update={"messages": state.append_messages([response])},
                )

            # Route to debugger or think based on conditions
            next_node = "debugger_think" if should_route_to_debugger else "think"
            return Command(
                goto=next_node, update={"messages": state.append_messages([response])}
            )

        if len(calls) > 1:
            return Command(
                goto="think",
                update={
                    "messages": state.append_messages(
                        [HumanMessage(content=MULTI_TOOL_ERROR)]
                    )
                },
            )

        return Command(
            goto="think",
            update={
                "messages": state.append_messages(
                    [
                        HumanMessage(
                            content=TOOLS_NOT_FOUND_ERROR(
                                tools={
                                    ", ".join(
                                        [
                                            f"<{tool.name}/>: {tool.usage}"
                                            for tool in context.toolkit.tools
                                        ]
                                    )
                                }
                            )
                        )
                    ]
                )
            },
        )


class OneShotPlanner(AutoDSTaskInference):
    async def _runnable(
        self, state: AutoDSState, context: AutoDSContext
    ) -> AutoDSState | Command[Any]:
        self.prompt_generator = PlannerOneShotPromptGenerator(
            project_path=context.project_path
        )
        report_path = Path(context.project_path) / PLANNER_REPORT_PATH
        if (
            report_path.exists()
            and report_path.stat().st_size > 0
            and report_path.read_text(encoding="utf-8").strip() != ""
        ):
            return state
        else:
            history = state["messages"]
            prompt = self.prompt_generator.react_prompt(history)
            try:
                response = await context.llm_client.ainvoke(prompt)
            except ValueError as e:
                if "No generations found in stream" in str(e):
                    return Command(goto=END)
                raise
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(response.content, encoding="utf-8")
            return state


class OneShotAnalystSaveReport(AutoDSTaskInference):
    async def _runnable(
        self, state: AutoDSState, context: AutoDSContext
    ) -> AutoDSState | Command[Any]:
        report = state["messages"][-1].content
        report_path = Path(context.project_path) / ANALYST_REPORT_PATH
        if not report_path.exists():
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.touch()
        report_path.write_text(report, encoding="utf-8")
        state.replace_messages(state.messages[:-1])
        return state


class ResearcherReportLoad(AutoDSTaskInference):
    async def _runnable(
        self, state: AutoDSState, context: AutoDSContext
    ) -> AutoDSState | Command[Any]:
        report_path = Path(context.project_path) / RESEARCHER_REPORT_PATH
        if not report_path.exists():
            return state
        report = report_path.read_text(encoding="utf-8")
        return Command(
            update={"messages": state.append_messages([AIMessage(content=report)])}
        )


class ResearcherSaveReport(AutoDSTaskInference):
    async def _runnable(
        self, state: AutoDSState, context: AutoDSContext
    ) -> AutoDSState | Command[Any]:
        report = state["messages"][-1].content
        report_path = Path(context.project_path) / RESEARCHER_REPORT_PATH
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report, encoding="utf-8")
        state.replace_messages(state.messages[:-1])
        return state


class OneShotAnalyst(AutoDSTaskInference):
    def __init__(self, report_path: Path):
        super().__init__()
        self.report_path = report_path

    async def _runnable(
        self, state: AutoDSState, context: AutoDSContext
    ) -> AutoDSState | Command[Any]:
        report = self.report_path.read_text(encoding="utf-8")
        return Command(
            update={"messages": state.append_messages([AIMessage(content=report)])}
        )
