from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "developer"]
    content: str = Field(min_length=1, max_length=20000)
    name: str | None = None


class ChatCompletionRequest(BaseModel):
    model: str = Field(min_length=1, max_length=200)
    messages: list[ChatMessage] = Field(min_length=1, max_length=100)
    stream: bool = False
    temperature: float | None = None
    user: str | None = Field(default=None, max_length=200)
    metadata: dict[str, Any] | None = None

    @field_validator("messages")
    @classmethod
    def ensure_last_message_is_userish(cls, value: list[ChatMessage]) -> list[ChatMessage]:
        if not any(m.role == "user" for m in value):
            raise ValueError("at least one user message is required")
        return value


class AssistantMessage(BaseModel):
    role: Literal["assistant"] = "assistant"
    content: str


class Choice(BaseModel):
    index: int = 0
    finish_reason: Literal["stop"] = "stop"
    message: AssistantMessage


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionResponse(BaseModel):
    id: str
    object: Literal["chat.completion"] = "chat.completion"
    created: int
    model: str
    choices: list[Choice]
    usage: Usage | None = None
