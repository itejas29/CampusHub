"""Pydantic schemas for the role-aware floating chatbot."""
from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class ChatActionLink(BaseModel):
    title: str
    path: str


class ChatMessageItem(BaseModel):
    role: str = Field(..., description="'user' or 'assistant'")
    content: str


class ChatQueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)
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
