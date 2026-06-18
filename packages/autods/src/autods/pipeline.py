import json
import os
import subprocess
from pathlib import Path
from typing import Any, Awaitable, Callable, TypedDict

from langchain.agents import AgentState, create_agent
from langchain.agents.middleware import (
    AgentMiddleware,
    FilesystemFileSearchMiddleware,
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
from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.runnables import Runnable
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.runtime import Runtime
from langgraph.types import Command

from autods.constants import (
    ANALYST_REPORT_PATH,
    AUTODS_PROJECT_HOME,
    MANAGER_REPORT_PATH,
    PRESENTER_REPORT_PATH,
    RESEARCHER_REPORT_PATH,
)
from autods.environments import LocalSandboxAdapter, resolve_venv_env
from autods.tools import (
    create_libq_search_tool,
    create_read_tool,
    create_run_python_tool,
    create_run_shell_tool,
    create_submit_report_tool,
    create_submit_solution_tool,
)


class _UnrestrictedFileSearchMiddleware(FilesystemFileSearchMiddleware):
    """FilesystemFileSearchMiddleware that can search inside hidden/ignored dirs"""

    def _ripgrep_search(
        self, pattern: str, base_path: str, include: str | None
    ) -> dict[str, list[tuple[int, str]]]:
        try:
            base_full = self._validate_and_resolve_path(base_path)
        except ValueError:
            return {}

        if not base_full.exists():
            return {}

        cmd = ["rg", "--json", "--hidden", "--no-ignore", "--glob", "!.git"]

        if include:
            cmd.extend(["--glob", include])

        cmd.extend(["--", pattern, str(base_full)])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return self._python_search(pattern, base_path, include)

        results: dict[str, list[tuple[int, str]]] = {}
        for line in result.stdout.splitlines():
            try:
                data = json.loads(line)
                if data["type"] == "match":
                    path = data["data"]["path"]["text"]
                    virtual_path = "/" + str(Path(path).relative_to(self.root_path))
                    line_num = data["data"]["line_number"]
                    line_text = data["data"]["lines"]["text"].rstrip("\n")

                    if virtual_path not in results:
                        results[virtual_path] = []
                    results[virtual_path].append((line_num, line_text))
            except (json.JSONDecodeError, KeyError):
                continue

        return results


TIME_OUT = 60 * 60 * 1 # 1h

ANALYST_SYSTEM_PROMPT = """
You are the Analyst stage in an AutoDS pipeline.
Create detailed analytical report for the task.

Goal:
Provide comprehencise exploration data and task analysis for managment and development team.
You are their sole source of analytical expertise.

Rules
- do not solve the task directly
- keep statements evidence-based
- when the report is complete, call `submit_report(text=...)` with the full markdown report
- prefer a high-level public API and try to avoid using internal APIs in reports.
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
You are the PM / Planner stage in an AutoDS pipeline.
Create technical specification document for this task.

Goal:
Define the tasks and scope of work for the research team, and establish clear objectives and verification steps.

Rules
- do not write solution code
- when the spec is complete, call `submit_report(text=...)` with the full markdown plan
""".strip()

CODER_SYSTEM_PROMPT = """
You are the Coder stage in an AutoDS pipeline.

Goal:
- implement the plan in the workspace
- use fast validation loops first, then complete the final solution
- prefer simple, fast (under 5 minutes), reproducible approaches

Rules:
- use `run_shell` to inspect files and run shell workflows
- use `run_python` for Python execution in the workspace
- use `libq_search` when library behavior is unclear
- before completing the task, use the `submit_solution` function.
- if tool output includes debugger analysis, incorporate it and continue
- finish with a concise assistant message that explains what was implemented and what artifacts were produced
""".strip()

DEBUGGER_SYSTEM_PROMPT = """
You are the Debugger stage in an AutoDS pipeline.
Identify the root cause of the error reported by the user and provide a concise explanation and fix direction supported by evidences.

Goal:
Help the user identify the root cause of the error, rather than providing a quick workaround or trapping them in a try-error loop.

Instruction:
- Ensure that the output is concise and does not exceed 250 words.
- If the problem is due to incorrect API usage, you can use `glob`, `grep`, `read`, and `libq_search` to find the correct signatures, parameters, and other relevant information.

Ouput format:
1. Root cause with concise explanation
2. Fix direction

Available tools:
- use `glob` to discover relevant files in the project workspace
- use `grep` to locate code, symbols, or error strings
- use `read` to inspect specific text files with optional line windows
""".strip()


PRESENTER_SYSTEM_PROMPT = """
You are the Presenter stage in an AutoDS pipeline.

Context: 
The Coder has just completed a task in the current folder.
A submission file (predictions) has been generated, and the source code/notebooks used to create it are available.

Objective: 
Generate a rigorous Technical Validation Report. 

Instruction:
- review the prior stage outputs and present the final result clearly
- explain what was built, what files or artifacts matter, and any remaining caveats
- analyze the results, conduct exploratory data analysis, and explain the findings if they seem accurate and their meaning.
- keep the response concise and user-facing
- when the presentation is complete, call `submit_report(text=...)` with the full markdown plan

Output format:
1. Executive Technical Summary 
2. Methodology & Code Audit
3. Prediction distribution analysis
4. Submission format validation
5. Conclusion
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


def create_tool_error_middleware(debugger: CompiledStateGraph):
    @wrap_tool_call
    async def tool_error_middleware(
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command]],
    ) -> ToolMessage | Command:
        try:
            return await handler(request)
        except Exception as e:
            if request.tool and request.tool.name == "run_python":
                message = f"INPUT:\n\n{request.tool}\n\n---\n\nOUTPUT:\n\n{e}"
                debugger_response = await debugger.ainvoke({"messages": [{"role": "user", "content": f"{message}"}]})
                debugger_messages = debugger_response.get("messages", [AIMessage(content="")])
                if len(debugger_messages) > 1:
                    debugger_last_message_text = debugger_messages[-1].content
                    tool_message = f"Original error: {e}.\n\nDebugger observation:\n\n{debugger_last_message_text}"
                    return ToolMessage(content=tool_message, tool_call_id=request.tool_call["id"], status="error")
            return ToolMessage(content=str(e), tool_call_id=request.tool_call["id"], status="error")

    return tool_error_middleware


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

def create_solution_required_middleware(solution_path: Path, *, name: str):
    @after_agent(can_jump_to=["model"], name=f"{name}_require_solution")
    def solution_required_middleware(state: AgentState, runtime: Runtime):
        if not bool(read_if_exists(solution_path)):
            return {
                "messages": [
                    SystemMessage(
                        content=(
                            "Before finishing this stage, please submit the complete Python code solution by calling submit_solution(code=…)."
                        )
                    )
                ],
                "jump_to": "model",
            }

    return solution_required_middleware


class PipelineState(TypedDict):
    task: str


def build_pipeline(project_path: str, *, checkpointer: None | bool | BaseCheckpointSaver = None) -> Runnable:

    resolved_path = Path(project_path).resolve()
    venv_env = resolve_venv_env(resolved_path)

    sandbox = LocalSandboxAdapter(extra_env=venv_env)

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

    shell_tool = create_run_shell_tool(sandbox=sandbox, project_path=resolved_path, timeout=TIME_OUT)
    python_tool = create_run_python_tool(
        sandbox=sandbox,
        project_path=resolved_path,
        timeout=TIME_OUT,
    )
    libq_tool = create_libq_search_tool()
    read_tool = create_read_tool(project_path=resolved_path)

    report_path_dict = resolve_report_pathes(resolved_path)

    base_middlewares = create_base_middlewares(lm_client)
    inject_reports_middleware = create_inject_reports_middleware(resolved_path)

    debugger_agent = create_agent(
        model=lm_client,
        tools=[read_tool, libq_tool],
        system_prompt=DEBUGGER_SYSTEM_PROMPT,
        middleware=[
            *base_middlewares,
            _UnrestrictedFileSearchMiddleware(
                root_path=str(resolved_path),
                use_ripgrep=True,
            ),
        ],
    )

    tool_error_middleware = create_tool_error_middleware(debugger_agent)

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
    
    solution_path = resolved_path / "solution.py"

    coder_agent = create_agent(
        model=lm_client,
        tools=[shell_tool, python_tool, libq_tool, create_submit_solution_tool(solution_path=solution_path)],
        system_prompt=CODER_SYSTEM_PROMPT,
        middleware=[*base_middlewares, 
                    tool_error_middleware, 
                    inject_reports_middleware,
                    create_solution_required_middleware(solution_path=solution_path, name="coder")],
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
        coder_reponse = await coder_agent.ainvoke({"messages": [{"role": "user", "content": f"{state['task']}"}]})
        
        coder_messages = coder_reponse.get("messages", [])
        presenter_input_msg = [{"role": "user", "content": f"{state['task']}"}]
        if coder_messages and len(coder_messages) > 1:
            coder_last_msg_content = coder_messages[-1].content
            presenter_input_msg.append({"role": "assistant", "content": coder_last_msg_content})
        await presenter_agent.ainvoke({"messages": presenter_input_msg})
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
