import os
import time
from typing import Any, Dict, Optional

from pydantic import ConfigDict, Field

from autods.agents.domain import BaseAgentState, BaseThinkActAgent
from autods.environments.jupyter import JupyterExecutor
from autods.environments.sandbox import LocalSandboxAdapter
from autods.tools.toolkit import Toolkit
from autods.utils.llm_client import LLMClient


class AutoDSState(BaseAgentState):
    """State for the ReAct agent containing message history and task information."""

    planner_agent_step: int = Field(default=0)
    code_agent_step: int = Field(default=0)


class AutoDSContext(BaseThinkActAgent):
    """Context containing configuration and LLM client for the agent."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    llm_client: LLMClient
    toolkit: Toolkit
    debugger_enabled: bool = Field(default=True)
    project_path: str = Field(default_factory=os.getcwd)
    jupyter_executor: Optional[JupyterExecutor] = Field(default=None)
    sandbox: Optional[LocalSandboxAdapter] = Field(default=None)
    python_env: Optional[Dict[str, str]] = Field(default=None)
    plan_state: Optional[Dict[str, Any]] = Field(default=None)
    start_time: float = Field(default_factory=lambda: time.perf_counter())
