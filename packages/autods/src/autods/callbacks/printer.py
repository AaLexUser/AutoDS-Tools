from typing import Any

from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    BaseMessageChunk,
    HumanMessage,
    HumanMessageChunk,
    ToolMessage,
    ToolMessageChunk,
)
from rich.console import Console


class MessageStreamPrinter:
    """Handles streaming message chunks while keeping role labels tidy."""

    role_labels = (
        (AIMessage, "[AI]"),
        (AIMessageChunk, "[AI]"),
        (HumanMessage, "[User]"),
        (HumanMessageChunk, "[User]"),
        (ToolMessage, "[Tool]"),
        (ToolMessageChunk, "[Tool]"),
    )

    def __init__(self, streaming: bool = True, console: Console | None = None) -> None:
        self.active_label: str | None = None
        self.streaming = streaming
        self.console = console or Console()
        self._pending_skip_label: str | None = None
        self._displayed_message_ids: set[str] = set()
        self._current_streaming_message_id: str | None = None

    @staticmethod
    def _label_for(message: Any) -> str | None:
        for message_type, candidate_label in MessageStreamPrinter.role_labels:
            if isinstance(message, message_type):
                return candidate_label
        return None

    @staticmethod
    def _normalize_message(
        raw_message: Any,
    ) -> tuple[str | None, str, bool, bool] | None:
        if isinstance(raw_message, tuple):
            if not raw_message:
                return None
            message = raw_message[0]
        else:
            message = raw_message
        if not isinstance(message, (BaseMessageChunk, BaseMessage)):
            return None

        content = message.content
        text = content if isinstance(content, str) else str(content)
        if not text:
            return None

        label = MessageStreamPrinter._label_for(message)
        is_chunk = isinstance(message, BaseMessageChunk)
        finish_reason = (getattr(message, "response_metadata", {}) or {}).get(
            "finish_reason"
        )
        is_final_chunk = finish_reason == "STOP"
        return label, text, is_chunk, is_final_chunk

    @staticmethod
    def _format_line(label: str | None, text: str) -> str:
        return f"{label.center(50, '=')}\n{text}" if label else text

    def handle(self, raw_message: Any) -> None:
        message = raw_message[0] if isinstance(raw_message, tuple) else raw_message

        if hasattr(message, "id") and message.id:
            if message.id in self._displayed_message_ids:
                return

        normalized = MessageStreamPrinter._normalize_message(raw_message)
        if not normalized:
            return
        label, text, is_chunk, is_final_chunk = normalized
        if is_chunk:
            self._handle_chunk(label, text, is_final_chunk, message)
        else:
            self._handle_complete(label, text, message)

    def flush(self) -> None:
        if self.streaming:
            self.console.print()
            self.streaming = False
            self.active_label = None
        self._pending_skip_label = None

    def _handle_chunk(
        self, label: str | None, text: str, is_final_chunk: bool, message: Any
    ) -> None:
        message_id = message.id if hasattr(message, "id") else None

        if label != self.active_label or (
            message_id and message_id != self._current_streaming_message_id
        ):
            if self._current_streaming_message_id:
                self._displayed_message_ids.add(self._current_streaming_message_id)

            if self.streaming:
                self.console.print()
            if label:
                self.console.print(label.center(50, "="), soft_wrap=True)
            self.active_label = label
            self.streaming = True
            self._current_streaming_message_id = message_id

        self.console.print(text, end="", soft_wrap=True)
        if is_final_chunk:
            self.console.print()
            self.streaming = False
            self._pending_skip_label = label
            self.active_label = None
            if self._current_streaming_message_id:
                self._displayed_message_ids.add(self._current_streaming_message_id)
                self._current_streaming_message_id = None

    def _handle_complete(self, label: str | None, text: str, message: Any) -> None:
        if self._pending_skip_label and self._pending_skip_label == label:
            self._pending_skip_label = None
            return
        if self.streaming:
            if self._current_streaming_message_id:
                self._displayed_message_ids.add(self._current_streaming_message_id)
                self._current_streaming_message_id = None
            self.console.print()
            self.streaming = False
            self.active_label = None

        if hasattr(message, "id") and message.id:
            self._displayed_message_ids.add(message.id)

        self.console.print(
            MessageStreamPrinter._format_line(label, text), soft_wrap=True
        )

    async def print_chunk_callback(self, mode: str, chunk: Any):
        if mode != "messages":
            return

        self.handle(chunk)
