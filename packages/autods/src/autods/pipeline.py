import json
import os
from pathlib import Path
from typing import Any, Awaitable, Callable, TypedDict

from langchain.agents import AgentState, create_agent
from langchain.agents.middleware import (
    AgentMiddleware,
    ModelRetryMiddleware,
    SummarizationMiddleware,
    ToolCallRequest,
    after_agent,
    before_agent,
    wrap_tool_call,
)
from langchain.chat_models import init_chat_model
from langchain.messages import ToolMessage
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage
from langchain_core.runnables import Runnable
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from langgraph.types import Command

from autods.constants import ANALYST_REPORT_PATH, MANAGER_REPORT_PATH, PRESENTER_REPORT_PATH, RESEARCHER_REPORT_PATH
from autods.environments import JupyterExecutor, LocalSandboxAdapter, resolve_venv_env
from autods.tools import (
    create_libq_search_tool,
    create_run_python_tool,
    create_run_shell_tool,
    create_submit_report_tool,
)

ANALYST_SYSTEM_PROMPT = """
You are the Analyst stage in an AutoDS demo pipeline.
Create detailed analytical report for the task.

Goal:
Provide comprehencise exploration data and task analysis for managment and development team.
You are their sole source of analytical expertise.

Rules
- do not solve the task directly
- keep statements evidence-based
- when the report is complete, call `submit_report(text=...)` with the full markdown report
- after the report is saved, you may provide a short completion message without additional tool calls

Workflow
- [1] Competition Overview: Understand the background and context of the topic.
- [2] Files: Analyze each provided file, detailing its purpose and how it should be used in the competition.
- [3] Problem Definition: Clarify the problem's definition and requirements.
- [4] Data Information: Gather detailed information about the data, including its structure and contents.
    - [4.1] Data type:
        - [4.1.1] ID type: features that are unique identifiers for each data point, which will NOT be used in the model training.
        - [4.1.2] Numerical type: features that are numerical values.
        - [4.1.3] Categorical type: features that are categorical values.
        - [4.1.4] Datetime type: features that are datetime values.
    - [4.2] Detailed data description
- [5] Target Variable: Identify the target variable that needs to be predicted or optimized, which is provided in the training set but not in the test set.
- [6] Evaluation Metrics: Determine the evaluation metrics that will be used to assess the submissions.
- [7] Submission Format: Understand the required format for the final submission.
- [8] Other Key Aspects: Highlight any other important aspects that could influence the approach to the competition.

Output:
- background ALL information with strong evidence, facts, and data.
- be concise and to the point.
- the report must encompass all the required sections.
""".strip()

RESEARCHER_SYSTEM_PROMPT = """
You are the Research stage in the AutoDS pipeline.
Create a cookbook with relevant snippets for a task based on information retrieved from `libq_search`.

Goal:
Help developers obtain concise information how to solve the task without any prior experience with the library.

Rules:
- use `libq_search` for library/API questions instead of relying on memory
- do not solve the task directly
- distinguish verified facts from uncertainty
- when the report is complete, call `submit_report(text=...)` with the full markdown report
- keep the report concise and easy to scan
- ensure the report contains all the information to solve the task for developer without prior experience
- after the report is saved, you may provide a short completion message without additional tool calls

Workflow:
- [1] Analyze the task and the data.
- [2] Select Sber Library according to the selection rules below.
    - [2.1] Apply selection rules IN ORDER
    - [2.2] Choose:
        if time series forecasting then tsururu `https://github.com/sb-ai-lab/tsururu`
        else if user-item recommendations then replay `https://github.com/sb-ai-lab/RePlay`
        else if event sequences then ptls `https://github.com/pytorch-lifestream/pytorch-lifestream`
        else if NVIDIA CUDA availability then py-boost `https://github.com/sb-ai-lab/Py-Boost`
        else LightAutoML `https://github.com/sb-ai-lab/LightAutoML`
    - [2.3] Justify your selection explicitly with evidence
- [3] Create a cookbook for the selected library with emphasis on VERIFICATION:
    - [3.1] Use `libq_search` for asking information about library and usage examples.
    - [3.2] Find verified examples: "[library_name] examples from loading data to saving predictions"
- [4] When the report is complete, call `submit_report(text=...)` with the full markdown report 
    - [4.1] Include ONLY verified information with sources
    
Output:

Cookbook
[Library Name]
[Short description of the library]
[Installation options]
---
Code Snippets
[Description of the 1st]
```python
...
```
---
CheatSheet
(Tabels, Lists)
[Classes, Methods, Args, Signatures, Dependencies, Notes, Key Info]
[Compact, Consice]
""".strip()

MANAGER_SYSTEM_PROMPT = """
You are the PM / Planner stage in an AutoDS demo pipeline.
Create technical specification document for this task.

Goal:
Define the tasks and scope of work for the research team, and establish clear objectives and verification steps.

Rules
- do not write solution code
- when the spec is complete, call `submit_report(text=...)` with the full markdown plan
""".strip()

CODER_SYSTEM_PROMPT = """
You are the Coder stage in an AutoDS demo pipeline.

Goal:
- implement the plan in the workspace
- use fast validation loops first, then complete the final solution
- prefer simple, reproducible approaches

Rules:
- use `run_shell` to inspect files and run shell workflows
- use `run_python` for Python execution in the shared notebook workspace
- use `libq_search` when library behavior is unclear
- if tool output includes debugger analysis, incorporate it and continue
- finish with a concise assistant message that explains what was implemented and what artifacts were produced
""".strip()

DEBUGGER_SYSTEM_PROMPT = """
You are the Debugger stage in an AutoDS demo pipeline.

Goal:
- analyze a Python execution error and identify its root cause
- do not write code
- do not produce a report file

Rules:
- use only `libq_search`
- return a concise root-cause explanation and the most likely fix direction
""".strip()


PRESENTER_SYSTEM_PROMPT = """
You are the Presenter stage in an AutoDS demo pipeline.

Goal:
- review the prior stage outputs and present the final result clearly
- explain what was built, what files or artifacts matter, and any remaining caveats
- keep the response concise and user-facing
""".strip()


def _required_env(name: str, override: str | None = None) -> str:
    value = override if override is not None else os.getenv(name)
    if value is None or value.strip() == "":
        raise ValueError(f"{name} environment variable is required")
    return value


def _optional_int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _optional_json_dict_env(name: str) -> dict[str, Any] | None:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{name} contains invalid JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{name} must decode to a JSON object")
    return value


def resolve_report_pathes(project_path: Path) -> dict[str, Path]:
    return {
        "analyst": project_path / ANALYST_REPORT_PATH,
        "researcher": project_path / RESEARCHER_REPORT_PATH,
        "manager": project_path / MANAGER_REPORT_PATH,
        "presenter": project_path / PRESENTER_REPORT_PATH,
    }


def read_if_exists(path: Path) -> str:
    if path.exists() and path.is_file():
        return path.read_text(encoding="utf-8").strip()
    return ""


def create_base_middlewares(model: BaseChatModel) -> list[AgentMiddleware]:
    return [
        SummarizationMiddleware(model=model, trigger=("tokens", 128000), keep=("messages", 5)),
        ModelRetryMiddleware(max_retries=3, backoff_factor=2.0, initial_delay=1.0),
    ]


def create_inject_reports_middleware(project_path: Path):
    @before_agent()
    def inject_reports_middleware(state: AgentState, runtime: Runtime):
        reports_content = ""
        for key, value in resolve_report_pathes(project_path).items():
            if text := read_if_exists(value):
                reports_content += "\n\n".join([f"[{key.capitalize()}]:{text}"])
        if reports_content.strip():
            return {"messages": [{"role": "user", "content": reports_content}]}
        return None

    return inject_reports_middleware


@wrap_tool_call
async def tool_error_middleware(
    request: ToolCallRequest,
    handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command]],
) -> ToolMessage | Command:
    try:
        return await handler(request)
    except RuntimeError as e:
        return ToolMessage(content=str(e), tool_call_id=request.tool_call["id"], status="error")


def create_skip_agent_if_report_exists_middleware(report_path: Path):
    @before_agent(can_jump_to=["end"])
    def skip_agent_if_report_exists_middleware(state: AgentState, runtime: Runtime):
        if bool(read_if_exists(report_path)):
            return {"jump_to": "end"}
        return None

    return skip_agent_if_report_exists_middleware


def create_report_required_middleware(report_path: Path, *, name: str):
    @after_agent(can_jump_to=["model"], name=f"{name}_require_report")
    def report_required_middleware(state: AgentState, runtime: Runtime):
        if not bool(read_if_exists(report_path)):
            return {
                "messages": [
                    SystemMessage(
                        content=(
                            "Before finishing this stage, call submit_report(text=...) with the full markdown report."
                        )
                    )
                ],
                "jump_to": "model",
            }

    return report_required_middleware


class PipelineState(TypedDict):
    task: str


def build_pipeline(project_path: str, *, checkpointer: None | bool | BaseCheckpointSaver = None) -> Runnable:

    resolved_path = Path(project_path).resolve()
    venv_env = resolve_venv_env(resolved_path)

    sandbox = LocalSandboxAdapter(extra_env=venv_env)
    executor = JupyterExecutor(workspace=resolved_path, env_vars=venv_env)

    lm_client = init_chat_model(
        model=_required_env("AUTODS_MODEL"),
        model_provider="openai",
        api_key=_required_env("AUTODS_API_KEY"),
        base_url=os.getenv("AUTODS_BASE_URL"),
        max_retries=_optional_int_env("AUTODS_MAX_RETRIES", default=3),
        model_kwargs=_optional_json_dict_env("AUTODS_MODEL_KWARGS_JSON") or {},
        extra_body=_optional_json_dict_env("AUTODS_EXTRA_BODY_JSON"),
        default_headers=_optional_json_dict_env("AUTODS_DEFAULT_HEADERS_JSON"),
    )

    shell_tool = create_run_shell_tool(sandbox=sandbox, project_path=resolved_path, timeout=300)
    python_tool = create_run_python_tool(executor=executor, timeout=300)
    libq_tool = create_libq_search_tool()

    report_path_dict = resolve_report_pathes(resolved_path)

    base_middlewares = create_base_middlewares(lm_client)
    inject_reports_middleware = create_inject_reports_middleware(resolved_path)

    analyst_agent = create_agent(
        model=lm_client,
        tools=[shell_tool, python_tool, libq_tool, create_submit_report_tool(report_path=report_path_dict["analyst"])],
        system_prompt=ANALYST_SYSTEM_PROMPT,
        middleware=[
            *base_middlewares,
            inject_reports_middleware,
            tool_error_middleware,
            create_skip_agent_if_report_exists_middleware(report_path_dict["analyst"]),
            create_report_required_middleware(report_path_dict["analyst"], name="analyst"),
        ],
    )

    researcher_agent = create_agent(
        model=lm_client,
        tools=[libq_tool, create_submit_report_tool(report_path=report_path_dict["researcher"])],
        system_prompt=RESEARCHER_SYSTEM_PROMPT,
        middleware=[
            *base_middlewares,
            inject_reports_middleware,
            tool_error_middleware,
            create_skip_agent_if_report_exists_middleware(report_path_dict["researcher"]),
            create_report_required_middleware(report_path_dict["researcher"], name="researcher"),
        ],
    )

    manager_agent = create_agent(
        model=lm_client,
        tools=[libq_tool, create_submit_report_tool(report_path=report_path_dict["manager"])],
        system_prompt=MANAGER_SYSTEM_PROMPT,
        middleware=[
            *base_middlewares,
            inject_reports_middleware,
            tool_error_middleware,
            create_skip_agent_if_report_exists_middleware(report_path_dict["manager"]),
            create_report_required_middleware(report_path_dict["manager"], name="manager"),
        ],
    )

    coder_agent = create_agent(
        model=lm_client,
        tools=[shell_tool, python_tool, libq_tool],
        system_prompt=CODER_SYSTEM_PROMPT,
        middleware=[*base_middlewares, tool_error_middleware, inject_reports_middleware],
    )

    presenter_agent = create_agent(
        model=lm_client,
        tools=[
            shell_tool,
            create_submit_report_tool(report_path=report_path_dict["presenter"]),
        ],
        system_prompt=PRESENTER_SYSTEM_PROMPT,
        middleware=[
            *base_middlewares,
            tool_error_middleware,
            create_report_required_middleware(report_path_dict["presenter"], name="presenter"),
        ],
    )

    async def pipeline(state: PipelineState):
        await analyst_agent.ainvoke({"messages": [{"role": "user", "content": f"{state['task']}"}]})
        await researcher_agent.ainvoke({"messages": [{"role": "user", "content": f"{state['task']}"}]})
        await manager_agent.ainvoke({"messages": [{"role": "user", "content": f"{state['task']}"}]})
        await coder_agent.ainvoke({"messages": [{"role": "user", "content": f"{state['task']}"}]})
        await presenter_agent.ainvoke({"messages": [{"role": "user", "content": f"{state['task']}"}]})
        return {"task": state["task"]}

    builder = StateGraph(state_schema=PipelineState)
    builder.add_node("pipeline", pipeline)

    builder.add_edge(START, "pipeline")
    builder.add_edge("pipeline", END)
    return builder.compile(checkpointer=checkpointer)


def print_messages(token):
    if len(token.content_blocks) > 0:
        for item in token.content_blocks:
            if item.get("type") == "text" and item.get("text"):
                print(item.get("text"), end="")
            else:
                print(f"{token.content_blocks}\n")


if __name__ == "__main__":
    import asyncio

    from dotenv import load_dotenv

    load_dotenv()

    async def _demo() -> None:
        titanic_dataset = "/Users/aleksejlapin/.codex/worktrees/fcc6/AutoDS-Tools/data/titanic"
        pipeline = build_pipeline(project_path=titanic_dataset)
        prev_node = ""
        async for chunk in pipeline.astream(
            {"task": "Solve this task with lightautoml"},
            stream_mode="messages",
            version="v2",
        ):
            if chunk["type"] == "messages":
                token, metadata = chunk["data"]
                current_node = metadata["langgraph_node"]
                if prev_node == current_node:
                    print_messages(token)
                else:
                    prev_node = current_node
                    print(f"node: {metadata['langgraph_node']}")
                    print_messages(token)

    try:
        asyncio.run(_demo())
    except KeyboardInterrupt:
        print("\nInterrupted.", flush=True)
