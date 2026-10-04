import re
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.services.chat_router import ChatUsage
from app.services.ollama_agent import AgentToolExecution


class AgentRunRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=8192)
    conversation_id: UUID | None = None
    attachment_ids: list[UUID] = Field(default_factory=list, max_length=10)

    @field_validator("prompt")
    @classmethod
    def strip_prompt(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("prompt must not be blank")
        return value


class AgentRunResponse(BaseModel):
    answer: str
    tool_calls: list[AgentToolExecution]


class ChatStreamRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=8192)
    provider: Literal["ollama", "openai_compatible"] | None = None
    model: str | None = Field(default=None, min_length=1, max_length=128)
    conversation_id: UUID | None = None
    attachment_ids: list[UUID] = Field(default_factory=list, max_length=10)

    @field_validator("prompt")
    @classmethod
    def strip_prompt(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("prompt must not be blank")
        return value

    @field_validator("model")
    @classmethod
    def strip_model(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("model must not be blank")
        return value


class ChatModelOption(BaseModel):
    provider: Literal["ollama", "openai_compatible"]
    model: str
    configured: bool
    is_default: bool


class ChatModelCatalog(BaseModel):
    default_provider: Literal["ollama", "openai_compatible"]
    default_model: str
    models: list[ChatModelOption]


class DocumentIngestResponse(BaseModel):
    document_id: UUID
    source_name: str
    chunks_indexed: int
    uploaded_at: datetime


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=8192)
    top_k: int = Field(default=5, ge=1, le=50)
    document_id: UUID | None = None

    @field_validator("query")
    @classmethod
    def strip_query(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("query must not be blank")
        return value


class SearchHit(BaseModel):
    chunk_id: str
    document_id: UUID
    chunk_index: int
    content: str
    score: float
    metadata: dict[str, Any]


class SearchResponse(BaseModel):
    query: str
    results: list[SearchHit]


class SkillSummary(BaseModel):
    name: str
    description: str
    parameters: dict[str, Any]


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=128)
    display_name: str | None = Field(default=None, max_length=80)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            raise ValueError("email must be a valid email address")
        return value

    @field_validator("display_name")
    @classmethod
    def strip_display_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            raise ValueError("email must be a valid email address")
        return value


class AuthenticatedUserResponse(BaseModel):
    id: UUID
    email: str | None
    display_name: str


class ConversationCreateRequest(BaseModel):
    title: str = Field(default="New conversation", min_length=1, max_length=72)

    @field_validator("title")
    @classmethod
    def strip_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("title must not be blank")
        return value


class ConversationSummary(BaseModel):
    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime


class ConversationMessage(BaseModel):
    id: UUID
    role: Literal["user", "assistant"]
    content: str
    usage: ChatUsage | None = None
    tool_calls: list[AgentToolExecution] = Field(default_factory=list)
    attachment_ids: list[UUID] = Field(default_factory=list)
    created_at: datetime


class ConversationDetail(ConversationSummary):
    messages: list[ConversationMessage]


class DocumentSummary(BaseModel):
    document_id: UUID
    source_name: str
    chunks_indexed: int
    uploaded_at: datetime
