import os
import time
from pathlib import Path
from typing import Any, Optional, cast

from langchain.tools import StructuredTool
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.config import get_stream_writer
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel, Field

from autods.agents.autods.domain import AutoDSContext, AutoDSState
from autods.agents.base import BaseAgent
from autods.agents.think_act_agent import create_think_act_agent
from autods.constants import (
    ANALYST_REPORT_PATH,
    AUTO_DS_AGENT,
    RESEARCHER_REPORT_PATH,
)
from autods.environments.python_env import resolve_venv_env
from autods.environments.sandbox import LocalSandboxAdapter
from autods.prompting.prompt_generator import (
    AnalystPromptGenerator,
    AutoDSPromptGenerator,
    DebuggerPromptGenerator,
    PresenterPromptGenerator,
    ResearcherPromptGenerator,
)
from autods.task_inference.autods import (
    Act,
    OneShotAnalyst,
    OneShotAnalystSaveReport,
    OneShotPlanner,
    ResearcherReportLoad,
    ResearcherSaveReport,
    Think,
)
from autods.tools.base import BaseTool
from autods.tools.codeblocks import CodeBlocksTool
from autods.tools.libq import LibQTool
from autods.tools.submit import SubmitTool
from autods.tools.toolkit import Toolkit
from autods.utils.llm_client import LLMClient

DEFAULT_RECURSION_STEPS = 50
ANALYST_STEPS = 5
RESEARCHER_STEPS = 5
PLANNER_STEPS = 5
DEBUGGER_STEPS = 5
PRESENTER_STEPS = 5


class AutoDSAgent(BaseAgent):
    def __init__(
        self,
        project_path: Optional[str] = None,
        *,
        llm_client: LLMClient | None = None,
    ):
        super().__init__()
        start_time = time.perf_counter()
        self.llm = llm_client or LLMClient()
        self.max_steps = DEFAULT_RECURSION_STEPS

        resolved_path = Path(project_path or os.getcwd())
        venv_env = resolve_venv_env(resolved_path)

        self.sandbox = LocalSandboxAdapter()
        self.sandbox.update_environment(extra_env=venv_env)

        self.toolkit = self.create_autods_toolkit()
        self.context = AutoDSContext(
            llm_client=self.llm,
            toolkit=self.toolkit,
            debugger_enabled=DEBUGGER_STEPS > 0,
            sandbox=self.sandbox,
            python_env=venv_env,
            project_path=str(resolved_path),
            start_time=start_time,
        )

    def create_autods_toolkit(self) -> Toolkit:
        tools = [
            CodeBlocksTool(timeout=60 * 60),  # 1 hour
            LibQTool(),
            SubmitTool(),
        ]
        return Toolkit(*tools)

    def create_analyst_toolkit(self) -> Toolkit:
        tools: list[BaseTool] = [
            CodeBlocksTool(),
        ]

        return Toolkit(*tools)

    def create_researcher_toolkit(self) -> Toolkit:
        tools: list[BaseTool] = [LibQTool()]
        return Toolkit(*tools)

    def create_planner_toolkit(self) -> Toolkit:
        tools: list[BaseTool] = [
            CodeBlocksTool(),
        ]

        return Toolkit(*tools)

    def create_debugger_toolkit(self) -> Toolkit:
        tools: list[BaseTool] = [
            CodeBlocksTool(timeout=60 * 60),  # 1 hour
            LibQTool(),
        ]

        return Toolkit(*tools)

    def create_presenter_toolkit(self) -> Toolkit:
        tools: list[BaseTool] = [
            CodeBlocksTool(timeout=60 * 60),  # 1 hour
        ]

        return Toolkit(*tools)

    def check_file_exists_and_not_empty(self, path: Path) -> bool:
        return path.exists() and path.is_file() and path.stat().st_size > 0 and path.read_text().strip() != ""

    def runnable(self, checkpointer: BaseCheckpointSaver[Any] | None = None) -> CompiledStateGraph:
        workflow = StateGraph(AutoDSState, context_schema=AutoDSContext)

        think_node = Think(
            prompt_generation=AutoDSPromptGenerator(self.context.project_path, tools=self.context.toolkit.tools)
        ).runnable
        act_node = Act().runnable

        if ANALYST_STEPS:
            analyst_report_path = Path(self.context.project_path) / ANALYST_REPORT_PATH
            if self.check_file_exists_and_not_empty(analyst_report_path):
                one_shot_analyst_node = OneShotAnalyst(analyst_report_path).runnable
                workflow.set_entry_point("analyst_think")
                workflow.add_node("analyst_think", one_shot_analyst_node)
                workflow.add_edge("analyst_think", "researcher_think")
            else:
                if RESEARCHER_STEPS:
                    next_node = "researcher_think"
                elif PLANNER_STEPS:
                    next_node = "planner_think"
                else:
                    next_node = "think"
                analyst_toolkit = self.create_analyst_toolkit()
                analyst_think, analyst_act = create_think_act_agent(
                    prompt_generator=AnalystPromptGenerator(
                        project_path=self.context.project_path,
                        tools=analyst_toolkit.tools,
                        steps_limit=ANALYST_STEPS,
                    ),
                    toolkit=analyst_toolkit,
                    throw_history=True,
                    max_steps=ANALYST_STEPS,
                    context_type=AutoDSContext,
                    state_type=AutoDSState,
                    prefix="analyst_",
                    next_node="analyst_save_report",
                )
                workflow.set_entry_point("analyst_think")
                workflow.add_node("analyst_think", analyst_think)
                workflow.add_node("analyst_act", analyst_act)
                workflow.add_node("analyst_save_report", OneShotAnalystSaveReport().runnable)
                workflow.add_edge("analyst_save_report", next_node)

        if RESEARCHER_STEPS:
            researcher_report_path = Path(self.context.project_path) / RESEARCHER_REPORT_PATH
            if ANALYST_STEPS == 0:
                workflow.set_entry_point("researcher_think")
            if self.check_file_exists_and_not_empty(researcher_report_path):
                researcher_report_load_node = ResearcherReportLoad().runnable
                workflow.add_node("researcher_think", researcher_report_load_node)
                workflow.add_edge("researcher_think", "planner_think")
            else:
                next_node = "planner_think" if PLANNER_STEPS else "think"
                researcher_toolkit = self.create_researcher_toolkit()
                researcher_think, researcher_act = create_think_act_agent(
                    prompt_generator=ResearcherPromptGenerator(
                        project_path=self.context.project_path,
                        tools=researcher_toolkit.tools,
                        steps_limit=RESEARCHER_STEPS,
                    ),
                    toolkit=researcher_toolkit,
                    throw_history=True,
                    max_steps=RESEARCHER_STEPS,
                    context_type=AutoDSContext,
                    state_type=AutoDSState,
                    prefix="researcher_",
                    next_node="researcher_save_report",
                )
                if not ANALYST_STEPS:
                    workflow.set_entry_point("researcher_think")
                workflow.add_node("researcher_think", researcher_think)
                workflow.add_node("researcher_act", researcher_act)
                workflow.add_node("researcher_save_report", ResearcherSaveReport().runnable)
                workflow.add_edge("researcher_save_report", next_node)
        if PLANNER_STEPS:
            one_shot_planner_node = OneShotPlanner().runnable
            workflow.add_node("planner_think", one_shot_planner_node)
            workflow.add_edge("planner_think", "think")
        else:
            workflow.set_entry_point("think")

        if DEBUGGER_STEPS:
            debugger_toolkit = self.create_debugger_toolkit()
            debugger_think, debugger_act = create_think_act_agent(
                prompt_generator=DebuggerPromptGenerator(
                    project_path=self.context.project_path,
                    tools=debugger_toolkit.tools,
                    steps_limit=DEBUGGER_STEPS,
                ),
                toolkit=debugger_toolkit,
                throw_history=True,
                max_steps=DEBUGGER_STEPS,
                context_type=AutoDSContext,
                state_type=AutoDSState,
                last_messages_cnt=2,
                prefix="debugger_",
                next_node="think",
            )
            workflow.add_node("debugger_think", debugger_think)
            workflow.add_node("debugger_act", debugger_act)

        workflow.add_node("think", think_node)
        workflow.add_node("act", act_node)

        if PRESENTER_STEPS:
            presenter_toolkit = self.create_presenter_toolkit()
            presenter_think, presenter_act = create_think_act_agent(
                prompt_generator=PresenterPromptGenerator(
                    project_path=self.context.project_path,
                    tools=presenter_toolkit.tools,
                    steps_limit=PRESENTER_STEPS,
                ),
                toolkit=presenter_toolkit,
                throw_history=True,
                max_steps=PRESENTER_STEPS,
                context_type=AutoDSContext,
                state_type=AutoDSState,
                last_messages_cnt=2,
                prefix="presenter_",
                next_node=END,
            )
            workflow.add_node("presenter_think", presenter_think)
            workflow.add_node("presenter_act", presenter_act)

        return self._compile_workflow(workflow, checkpointer)

    class _AutoDSToolInput(BaseModel):
        task: str = Field(..., description="Task for AutoDS agent")

    def as_tool(self, checkpointer: BaseCheckpointSaver[Any] | None = None) -> StructuredTool:
        async def runnable_tool(task: str, config: RunnableConfig | None = None) -> str:
            writer = get_stream_writer()
            final_text = ""
            async for mode, chunk in self.runnable(checkpointer=checkpointer).astream(
                input={"messages": [HumanMessage(content=task)]},
                context=cast(Any, self.context),
                config=config,
                stream_mode=["updates", "values", "custom"],
            ):
                match mode:
                    case "updates" | "custom":
                        writer({AUTO_DS_AGENT: chunk})
                    case "values":
                        if not isinstance(chunk, dict):
                            continue
                        msgs = chunk.get("messages", [])
                        if msgs:
                            last = msgs[-1]
                            final_text = getattr(last, "content", str(last))
            return final_text or "done"

        return StructuredTool.from_function(
            coroutine=runnable_tool,
            name=AUTO_DS_AGENT,
            description="Run the AutoDS agent (Data Science & ML).",
            args_schema=AutoDSAgent._AutoDSToolInput,
        )
