"""Pydantic schemas for the role-aware floating chatbot."""
from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field

from app.schemas.fields import block


class ChatActionLink(BaseModel):
    title: str
    path: str


class ChatMessageItem(BaseModel):
    role: Literal["user", "assistant"]
    content: block(4000, min_length=1)


class ChatQueryRequest(BaseModel):
    query: block(1000, min_length=1)
    history: list[ChatMessageItem] = Field(default_factory=list)


class ChatQueryResponse(BaseModel):
    reply: str
    role_context: str
    suggestions: list[str] = Field(default_factory=list)
    action_links: list[ChatActionLink] = Field(default_factory=list)
    is_confidential_block: bool = False
    timestamp: str


class ChatInitialConfigResponse(BaseModel):
    role_context: str
    user_name: str
    greeting: str
    suggestions: list[str]
