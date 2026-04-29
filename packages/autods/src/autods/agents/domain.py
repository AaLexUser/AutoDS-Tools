import time

from langchain_core.messages import BaseMessage
from pydantic import BaseModel, ConfigDict, Field

from autods.tools.toolkit import Toolkit
from autods.utils.llm_client import LLMClient


def _merge_messages(existing: list[BaseMessage], new: list[BaseMessage]) -> list[BaseMessage]:
    existing_by_id = {msg.id: idx for idx, msg in enumerate(existing) if msg.id}
    result = list(existing)
    for msg in new:
        if msg.id and msg.id in existing_by_id:
            result[existing_by_id[msg.id]] = msg
        else:
            result.append(msg)
    return result


class BaseAgentState(BaseModel):
    """Base state for agents."""

    messages: list[BaseMessage] = Field(default_factory=list)

    def __setitem__(self, key, value):
        setattr(self, key, value)

    def __getitem__(self, key):
        return getattr(self, key)

    def get(self, key, default=None):
        return getattr(self, key, default)

    def replace_messages(self, messages: list[BaseMessage]):
        self.messages = messages

    def append_messages(self, messages: list[BaseMessage]) -> list[BaseMessage]:
        self.messages = _merge_messages(self.messages, messages)
        return self.messages

    def messages_tail(self, count: int):
        return self.messages[-count:]


class BaseAgentContext(BaseModel):
    """Base context for agents"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    llm_client: LLMClient


class BaseThinkActAgent(BaseAgentContext):
    """Base context for think-act agents"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    toolkit: Toolkit
    start_time: float = Field(default_factory=lambda: time.perf_counter())
