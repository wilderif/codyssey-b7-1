"""Conversation persistence repository다."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.chat.models import Conversation


def create_success_conversation(
    *,
    db: Session,
    user_id: int,
    question: str,
    answer: str,
) -> Conversation:
    """성공한 질문 처리 결과를 flush한다."""

    conversation = Conversation(
        user_id=user_id,
        question=question,
        answer=answer,
        status="success",
        error_message=None,
    )
    db.add(conversation)
    db.flush()
    return conversation


def create_failed_conversation(
    *,
    db: Session,
    user_id: int,
    question: str,
    error_message: str,
) -> Conversation:
    """실패한 질문 처리 결과를 flush한다."""

    conversation = Conversation(
        user_id=user_id,
        question=question,
        answer=None,
        status="failed",
        error_message=error_message,
    )
    db.add(conversation)
    db.flush()
    return conversation


def get_recent_success_conversations(
    *,
    db: Session,
    user_id: int,
    limit: int = 5,
) -> list[Conversation]:
    """사용자의 최근 성공 Conversation을 반환한다."""

    if not 1 <= limit <= 5:
        raise ValueError("limit must be between 1 and 5")

    statement = (
        select(Conversation)
        .where(
            Conversation.user_id == user_id,
            Conversation.status == "success",
        )
        .order_by(Conversation.created_at.desc(), Conversation.id.desc())
        .limit(limit)
    )
    return list(db.scalars(statement))


def list_user_conversations(*, db: Session, user_id: int) -> list[Conversation]:
    """사용자의 전체 Conversation history를 반환한다."""

    statement = (
        select(Conversation)
        .where(Conversation.user_id == user_id)
        .order_by(Conversation.created_at.desc(), Conversation.id.desc())
    )
    return list(db.scalars(statement))
