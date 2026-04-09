from abc import ABC
from datetime import datetime
from pathlib import Path

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage

from autods.constants import (
    ANALYST_REPORT_PATH,
    RESEARCHER_REPORT_PATH,
)
from autods.prompting.prompt_store import prompt_store
from autods.tools.base import BaseTool


class PromptGenerator(ABC):
    def __init__(self) -> None:
        self._initial_message_index: int = 0

    @property
    def system_prompt(self) -> SystemMessage:
        return SystemMessage(content="")

    @property
    def user_prompt(self) -> HumanMessage:
        return HumanMessage(content="")

    @property
    def handler(self):
        return lambda x: x

    @property
    def initial_messages_prompts(self) -> list[AIMessage]:
        return []

    def get_next_initial_message_prompt(self) -> AIMessage | None:
        messages = self.initial_messages_prompts
        if self._initial_message_index < len(messages):
            message = messages[self._initial_message_index]
            self._initial_message_index += 1
            return message
        return None

    def reset_initial_message_index(self) -> None:
        self._initial_message_index = 0

    def chat_prompt(self, history: list[AnyMessage] | None = None) -> list[AnyMessage]:
        if history is None:
            history = []
        return [self.system_prompt, *history, self.user_prompt]

    def react_prompt(self, history: list[AnyMessage] | None = None) -> list[AnyMessage]:
        if history is None:
            history = []
        return [self.system_prompt, self.user_prompt, *history]


class AutoDSPromptGenerator(PromptGenerator):
    def __init__(self, project_path: str, tools: list[BaseTool]) -> None:
        super().__init__()
        self.project_path = project_path
        self.tools: list[BaseTool] = tools

    @property
    def system_prompt(self) -> SystemMessage:
        rules = prompt_store.load("autods.md")
        tool_guidance = "\n\n---\n\n".join(
            [tool.get_prompt() for tool in self.tools if tool.name != "web_search"]
        )
        return SystemMessage(content="\n\n".join([rules, tool_guidance]))

    # @property
    # def initial_messages_prompts(self) -> list[AIMessage]:
    #     return [
    #         AIMessage(
    #             content=(
    #                 f"I'm a senior MLE. I will help you with this task.\n\n"
    #                 f"My [1] step is to explore files.\n"
    #                 f"---\n\n"
    #                 f'<CodeBlock lang="bash">\n'
    #                 f"ls -lahS\n"
    #                 f"</CodeBlock>\n\n"
    #                 f"---\n"
    #                 f"I will wait for result of execution of this step. On next turn I will continue with [2] step: Minimal working baseline.\n"
    #             ),
    #         ),
    #     ]

    @property
    def user_prompt(self) -> HumanMessage:
        return HumanMessage(
            content=(
                f"[Time]\n{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"[Project root path]\n{self.project_path}\n\n"
            )
        )


class AnalystPromptGenerator(PromptGenerator):
    def __init__(
        self, project_path: str, tools: list[BaseTool], steps_limit: int
    ) -> None:
        super().__init__()
        self.project_path = project_path
        self.tools: list[BaseTool] = tools
        self.steps_limit = steps_limit

    @property
    def system_prompt(self) -> SystemMessage:
        tool_guidance = "\n\n---\n\n".join([tool.get_prompt() for tool in self.tools])
        return SystemMessage(
            content="\n\n".join([prompt_store.load("analyst.md"), tool_guidance])
        )

    # @property
    # def initial_messages_prompts(self) -> list[AIMessage]:
    #     return [
    #         AIMessage(
    #             content=(
    #                 f"I'm an expert Analyst. I will create comprehensive report of the task.\n\n"
    #                 f"My plan is to: \n\n"
    #                 f"- [1] Explore files and read description of the task.\n"
    #                 f"- [2] Read description of the task.\n"
    #                 f"- [3] Analyse data distribution, missing values, outliers.\n"
    #                 f"- [4] Create structured complete analytical report of this task with [AnalystReport] at start and terminate marker at the end.\n"
    #                 f"---\n\n"
    #                 f"My [1] step is to explore files.\n"
    #                 f"---\n\n"
    #                 f'<CodeBlock lang="bash">\n'
    #                 f"ls -lahS\n"
    #                 f"</CodeBlock>\n\n"
    #                 f"---\n"
    #                 f"I will wait for result of execution of this step. On next turn I will continue with [2] step: read description of the task.\n"
    #             )
    #         ),
    #         AIMessage(
    #             content=(
    #                 f"Now I can see files. Let's continue with [2] step: read description of the task.\n"
    #                 f"I will read description of the task from file description.md.\n"
    #                 f"---\n\n"
    #                 f'<CodeBlock lang="python">\n'
    #                 f"with open('description.md', 'r') as file:\n"
    #                 f"    print(file.read())\n"
    #                 f"</CodeBlock>\n\n"
    #                 f"---\n\n"
    #                 f"I will wait for result of execution of this step. On next turn I will continue with [3] step: analyse data distribution, missing values, outliers.\n"
    #             )
    #         ),
    #         AIMessage(
    #             content=(
    #                 f"I have read description of the task. Let's continue with [3] step: analyse data distribution, missing values, outliers.\n"
    #                 f"---\n\n"
    #                 f'I will use <CodeBlock lang="python"> tool.\n'
    #                 f"I will create function called `load_and_analyze_data()`.\n"
    #                 f"I will use describe() function to analyse data distribution.\n"
    #                 f"I will use isna() function to check for missing values.\n"
    #                 f"I will use value_counts() function to check for outliers.\n"
    #                 f"And I will print it's result. After seeing results I will add this specific information into my report at step [4].\n"
    #             )
    #         ),
    #     ]

    @property
    def user_prompt(self) -> HumanMessage:
        return HumanMessage(
            content=(
                f"[Time]\n{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"[Project root path]\n{self.project_path}\n\n"
                f"[STEPS LIMIT]\n{self.steps_limit}\n\n"
            )
        )


class ResearcherPromptGenerator(PromptGenerator):
    def __init__(
        self, project_path: str, tools: list[BaseTool], steps_limit: int
    ) -> None:
        super().__init__()
        self.project_path = project_path
        self.tools: list[BaseTool] = tools
        self.steps_limit = steps_limit

    @property
    def system_prompt(self) -> SystemMessage:
        tool_guidance = "\n\n---\n\n".join([tool.get_prompt() for tool in self.tools])
        return SystemMessage(
            content="\n\n".join([prompt_store.load("researcher.md"), tool_guidance])
        )

    # @property
    # def initial_messages_prompts(self) -> list[AIMessage]:
    #     return [
    #         AIMessage(
    #             content=(
    #                 f"I'm an expert Researcher.\n"
    #                 f"I see report from Analyst. I will use it to be more specific in my search.\n"
    #                 f"I will create comprehensive research report of the task.\n\n"
    #                 f"My plan is to: \n\n"
    #                 f"- [1] Search for tutorial examples first.\n"
    #                 f"- [2] Output all this verified detailed information into my research report.\n"
    #                 f"---\n\n"
    #                 f"My [1] step is to search for tutorial examples first.\n"
    #             )
    #         ),
    #     ]

    @property
    def user_prompt(self) -> HumanMessage:
        return HumanMessage(
            content=(
                f"[Time]\n{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"[Project root path]\n{self.project_path}\n\n"
                f"[STEPS LIMIT]\n{self.steps_limit}\n\n"
            )
        )


class PlannerOneShotPromptGenerator(PromptGenerator):
    def __init__(self, project_path: str) -> None:
        super().__init__()
        self.project_path = project_path

    @property
    def system_prompt(self) -> SystemMessage:
        return SystemMessage(content=prompt_store.load("planner_one_shot.md"))

    @property
    def user_prompt(self) -> HumanMessage:
        return HumanMessage(
            content=(
                f"[Time]\n{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"[Project root path]\n{self.project_path}\n\n"
            )
        )


class DebuggerPromptGenerator(PromptGenerator):
    def __init__(
        self, project_path: str, tools: list[BaseTool], steps_limit: int
    ) -> None:
        super().__init__()
        self.project_path = project_path
        self.tools: list[BaseTool] = tools
        self.steps_limit = steps_limit

    @property
    def system_prompt(self) -> SystemMessage:
        tool_guidance = "\n\n---\n\n".join([tool.get_prompt() for tool in self.tools])
        return SystemMessage(
            content="\n\n".join([prompt_store.load("debugger.md"), tool_guidance])
        )

    @property
    def user_prompt(self) -> HumanMessage:
        analyst_report_path = Path(self.project_path) / ANALYST_REPORT_PATH
        researcher_report_path = Path(self.project_path) / RESEARCHER_REPORT_PATH

        context = ""
        if (
            analyst_report_path.exists()
            and analyst_report_path.is_file()
            and analyst_report_path.stat().st_size > 0
            and analyst_report_path.read_text(encoding="utf-8").strip() != ""
        ):
            analyst_report = analyst_report_path.read_text(encoding="utf-8")
            context += f"[Analyst Report]\n{analyst_report}\n\n"
        if (
            researcher_report_path.exists()
            and researcher_report_path.is_file()
            and researcher_report_path.stat().st_size > 0
            and researcher_report_path.read_text(encoding="utf-8").strip() != ""
        ):
            researcher_report = researcher_report_path.read_text(encoding="utf-8")
            context += f"[Researcher Report]\n{researcher_report}\n\n"

        return HumanMessage(
            content=(
                f"{context}\n\n"
                f"[Time]\n{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"[Project root path]\n{self.project_path}\n\n"
                f"[STEPS LIMIT]\n{self.steps_limit}\n\n"
            )
        )


class PresenterPromptGenerator(PromptGenerator):
    def __init__(
        self, project_path: str, tools: list[BaseTool], steps_limit: int
    ) -> None:
        super().__init__()
        self.project_path = project_path
        self.tools: list[BaseTool] = tools
        self.steps_limit = steps_limit

    @property
    def system_prompt(self) -> SystemMessage:
        tool_guidance = "\n\n---\n\n".join([tool.get_prompt() for tool in self.tools])
        return SystemMessage(
            content="\n\n".join([prompt_store.load("presenter.md"), tool_guidance])
        )

    @property
    def initial_messages_prompts(self) -> list[AIMessage]:
        return [
            AIMessage(
                content=(
                    f"I'm an expert Analyst.\n\n"
                    f"My [1] step is to explore files.\n"
                    f"---\n\n"
                    f'<CodeBlock lang="bash">\n'
                    f"ls -lahS\n"
                    f"</CodeBlock>\n\n"
                    f"---\n"
                    f"I will wait for result of execution of this step. On next turn I will continue with [2] step.\n"
                )
            ),
        ]

    @property
    def user_prompt(self) -> HumanMessage:
        analyst_report_path = Path(self.project_path) / ANALYST_REPORT_PATH
        researcher_report_path = Path(self.project_path) / RESEARCHER_REPORT_PATH

        context = ""
        if (
            analyst_report_path.exists()
            and analyst_report_path.is_file()
            and analyst_report_path.stat().st_size > 0
            and analyst_report_path.read_text(encoding="utf-8").strip() != ""
        ):
            analyst_report = analyst_report_path.read_text(encoding="utf-8")
            context += f"[Analyst Report]\n{analyst_report}\n\n"
        if (
            researcher_report_path.exists()
            and researcher_report_path.is_file()
            and researcher_report_path.stat().st_size > 0
            and researcher_report_path.read_text(encoding="utf-8").strip() != ""
        ):
            researcher_report = researcher_report_path.read_text(encoding="utf-8")
            context += f"[Researcher Report]\n{researcher_report}\n\n"

        return HumanMessage(
            content=(
                f"{context}\n\n"
                f"[Time]\n{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"[Project root path]\n{self.project_path}\n\n"
                f"[STEPS LIMIT]\n{self.steps_limit}\n\n"
            )
        )
