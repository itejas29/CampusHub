"""Chatbot API routes with role-aware and security-guarded query processing."""
from __future__ import annotations

from fastapi import APIRouter

from app.core.deps import CurrentUser, DbSession
from app.models.enums import Role
from app.schemas.chatbot import (
    ChatInitialConfigResponse, ChatQueryRequest, ChatQueryResponse,
)
from app.services.chatbot import get_user_role_context, process_chat_query

router = APIRouter(prefix="/chatbot", tags=["chatbot"])


@router.get("/config", response_model=ChatInitialConfigResponse)
def get_chatbot_config(current_user: CurrentUser, db: DbSession):
    """Fetch initial role-specific greeting and suggestions for the logged-in user."""
    context = get_user_role_context(current_user, db)
    role_badge = context["role_badge"]

    if current_user.has_role(Role.STUDENT):
        greeting = (
            f"Hello {current_user.full_name}! I am your CampusHub Academic Assistant. "
            f"Ask me about your internship reports, mentor, electives, or campus policies."
        )
        suggestions = [
            "What is my internship status?",
            "Who is my assigned mentor?",
            "What is the minimum attendance policy?",
            "Am I eligible for minor specialisation?",
            "What is the grading scale?",
        ]
    elif current_user.has_role(Role.FACULTY, Role.HOD):
        is_hod = context.get("is_hod", False)
        if is_hod:
            greeting = f"Welcome Dr. {current_user.full_name} (HOD). I can assist with departmental coordination, faculty rosters, and round overviews."
            suggestions = [
                "List our department coordinators",
                "How many reports need review?",
                "Show active registration rounds",
            ]
        else:
            greeting = f"Welcome Prof. {current_user.full_name}. I can help you monitor your mentees, pending report reviews, and meetings."
            suggestions = [
                "How many weekly reports need my review?",
                "Show my assigned mentees",
                "What is the grading policy?",
            ]
    else:
        greeting = f"Welcome Administrator {current_user.full_name}. How can I assist with institution-wide overview today?"
        suggestions = [
            "Show active registration rounds",
            "Show department summary",
            "What is the grading system?",
        ]

    return ChatInitialConfigResponse(
        role_context=role_badge,
        user_name=current_user.full_name,
        greeting=greeting,
        suggestions=suggestions,
    )


@router.post("/query", response_model=ChatQueryResponse)
def handle_chat_query(
    body: ChatQueryRequest,
    current_user: CurrentUser,
    db: DbSession,
):
    """Handle chat query with role-based scoping and confidential information leakage guard."""
    return process_chat_query(
        user=current_user,
        query=body.query,
        history=body.history,
        db=db,
    )
