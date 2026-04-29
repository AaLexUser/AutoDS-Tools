from pathlib import Path
from unittest.mock import AsyncMock, Mock

from langchain_core.messages import AIMessage, HumanMessage

from autods.agents.autods.domain import AutoDSContext, AutoDSState
from autods.constants import (
    ANALYST_REPORT_PATH,
    PLANNER_REPORT_PATH,
    RESEARCHER_REPORT_PATH,
)
from autods.prompting.prompt_generator import (
    AutoDSPromptGenerator,
    PlannerOneShotPromptGenerator,
    ResearcherPromptGenerator,
)
from autods.task_inference.autods import (
    OneShotAnalystSaveReport,
    OneShotPlanner,
    ResearcherSaveReport,
)
from autods.tools.toolkit import Toolkit
from autods.utils.config import Config
from autods.utils.llm_client import LLMClient


def build_context(project_path: Path, llm_client: LLMClient | None = None) -> AutoDSContext:
    return AutoDSContext(
        project_path=str(project_path),
        llm_client=llm_client or Mock(spec=LLMClient),
        toolkit=Toolkit(),
        config=Config(),
    )


def test_autods_prompt_generator_loads_saved_reports(tmp_path: Path) -> None:
    project_path = tmp_path
    (project_path / ANALYST_REPORT_PATH).parent.mkdir(parents=True, exist_ok=True)
    (project_path / ANALYST_REPORT_PATH).write_text("analyst body", encoding="utf-8")
    (project_path / PLANNER_REPORT_PATH).write_text("planner body", encoding="utf-8")
    (project_path / RESEARCHER_REPORT_PATH).write_text("researcher body", encoding="utf-8")

    prompt = AutoDSPromptGenerator(
        project_path=str(project_path),
        tools=[],
    ).user_prompt

    assert "[Analyst Report]\nanalyst body" in prompt.content
    assert "[Planner Report]\nplanner body" in prompt.content
    assert "[Researcher Report]\nresearcher body" in prompt.content


def test_researcher_prompt_generator_loads_saved_reports(tmp_path: Path) -> None:
    project_path = tmp_path
    (project_path / ANALYST_REPORT_PATH).parent.mkdir(parents=True, exist_ok=True)
    (project_path / ANALYST_REPORT_PATH).write_text("analyst body", encoding="utf-8")
    (project_path / PLANNER_REPORT_PATH).write_text("planner body", encoding="utf-8")
    (project_path / RESEARCHER_REPORT_PATH).write_text("researcher body", encoding="utf-8")

    prompt = ResearcherPromptGenerator(
        project_path=str(project_path),
        tools=[],
        steps_limit=2,
    ).user_prompt

    assert "[Analyst Report]\nanalyst body" in prompt.content
    assert "[Planner Report]\nplanner body" in prompt.content
    assert "[Researcher Report]\nresearcher body" in prompt.content


def test_planner_prompt_generator_loads_saved_reports(tmp_path: Path) -> None:
    project_path = tmp_path
    (project_path / ANALYST_REPORT_PATH).parent.mkdir(parents=True, exist_ok=True)
    (project_path / ANALYST_REPORT_PATH).write_text("analyst body", encoding="utf-8")
    (project_path / PLANNER_REPORT_PATH).write_text("planner body", encoding="utf-8")
    (project_path / RESEARCHER_REPORT_PATH).write_text("researcher body", encoding="utf-8")

    prompt = PlannerOneShotPromptGenerator(project_path=str(project_path)).user_prompt

    assert "[Analyst Report]\nanalyst body" in prompt.content
    assert "[Planner Report]\nplanner body" in prompt.content
    assert "[Researcher Report]\nresearcher body" in prompt.content


async def test_analyst_save_report_persists_and_removes_visible_report(
    tmp_path: Path,
) -> None:
    state = AutoDSState(messages=[HumanMessage(content="internal analyst report")])
    context = build_context(tmp_path)

    result = await OneShotAnalystSaveReport()._runnable(state, context)

    assert result is state
    assert (tmp_path / ANALYST_REPORT_PATH).read_text(encoding="utf-8") == ("internal analyst report")
    assert state.messages == []


async def test_researcher_save_report_persists_and_removes_visible_report(
    tmp_path: Path,
) -> None:
    state = AutoDSState(messages=[HumanMessage(content="internal researcher report")])
    context = build_context(tmp_path)

    result = await ResearcherSaveReport()._runnable(state, context)

    assert result is state
    assert (tmp_path / RESEARCHER_REPORT_PATH).read_text(encoding="utf-8") == ("internal researcher report")
    assert state.messages == []


async def test_one_shot_planner_writes_report_without_appending_chat_copy(
    tmp_path: Path,
) -> None:
    response = AIMessage(content="planner artifact")
    llm_client = AsyncMock(spec=LLMClient)
    llm_client.ainvoke.return_value = response

    state = AutoDSState(messages=[])
    context = build_context(tmp_path, llm_client=llm_client)

    result = await OneShotPlanner()._runnable(state, context)

    assert result is state
    assert (tmp_path / PLANNER_REPORT_PATH).read_text(encoding="utf-8") == ("planner artifact")
    assert state.messages == []
