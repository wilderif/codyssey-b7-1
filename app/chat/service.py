"""Chat use case와 Conversation transaction을 처리한다."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from sqlalchemy.orm import Session

from app.chat.context import ChatMessage, build_context_messages
from app.chat.errors import (
    ChatGenerationError,
    ChatPersistenceError,
    ChatValidationError,
)
from app.chat.models import Conversation
from app.chat.openai_client import (
    OpenAIAnswerGenerator,
    create_openai_client,
    get_openai_model,
)
from app.chat.repository import ConversationRepository, SqlAlchemyConversationRepository

CONTEXT_HISTORY_LIMIT = 5
MAX_MESSAGE_LENGTH = 1000


class AnswerGenerator(Protocol):
    """Chat Service가 사용하는 answer 생성 계약이다."""

    async def generate(self, *, messages: Sequence[ChatMessage]) -> str:
        """message 목록의 answer를 생성한다."""

        ...


@dataclass(frozen=True)
class ChatResult:
    """성공적으로 저장된 Chat 처리 결과다."""

    conversation_id: int
    answer: str
    created_at: datetime


@dataclass(frozen=True)
class ConversationHistoryItem:
    """사용자 화면에 안전하게 전달할 Conversation history 항목이다."""

    conversation_id: int
    question: str
    answer: str | None
    status: str
    created_at: datetime


class ChatService:
    """질문 처리, answer 생성, Conversation 저장을 하나의 use case로 묶는다."""

    def __init__(
        self,
        *,
        db: Session,
        repository: ConversationRepository,
        answer_generator: AnswerGenerator,
    ) -> None:
        self._db = db
        self._repository = repository
        self._answer_generator = answer_generator

    async def process_chat(self, *, user_id: int, message: str) -> ChatResult:
        """질문을 처리하고 성공·실패 Conversation transaction을 완료한다."""

        question = _normalize_message(message)
        try:
            conversations = self._repository.get_recent_success_conversations(
                user_id=user_id,
                limit=CONTEXT_HISTORY_LIMIT,
            )
            messages = build_context_messages(
                conversations=conversations,
                current_question=question,
            )
        except Exception as error:
            self._db.rollback()
            raise ChatPersistenceError() from error

        try:
            answer = await self._answer_generator.generate(messages=messages)
        except ChatGenerationError as error:
            self._save_failed_conversation(
                user_id=user_id,
                question=question,
                error_message=error.record_message,
            )
            raise
        except Exception as error:
            generation_error = ChatGenerationError()
            self._save_failed_conversation(
                user_id=user_id,
                question=question,
                error_message=generation_error.record_message,
            )
            raise generation_error from error

        try:
            conversation = self._repository.create_success_conversation(
                user_id=user_id,
                question=question,
                answer=answer,
            )
            self._db.commit()
        except Exception as error:
            self._db.rollback()
            raise ChatPersistenceError() from error

        return ChatResult(
            conversation_id=conversation.id,
            answer=answer,
            created_at=conversation.created_at,
        )

    def _save_failed_conversation(
        self,
        *,
        user_id: int,
        question: str,
        error_message: str,
    ) -> None:
        try:
            self._repository.create_failed_conversation(
                user_id=user_id,
                question=question,
                error_message=error_message,
            )
            self._db.commit()
        except Exception as error:
            self._db.rollback()
            raise ChatPersistenceError() from error


async def process_chat(*, user_id: int, message: str, db: Session) -> ChatResult:
    """production 의존성을 조립해 Chat use case를 실행한다."""

    repository = SqlAlchemyConversationRepository(db=db)
    async with create_openai_client() as client:
        service = ChatService(
            db=db,
            repository=repository,
            answer_generator=OpenAIAnswerGenerator(
                client=client,
                model=get_openai_model(),
            ),
        )
        return await service.process_chat(user_id=user_id, message=message)


def list_conversation_history(
    *,
    user_id: int,
    db: Session,
) -> list[ConversationHistoryItem]:
    """로그인 사용자의 Conversation history를 내부 오류 없이 projection한다."""

    repository: ConversationRepository = SqlAlchemyConversationRepository(db=db)
    try:
        conversations = repository.list_user_conversations(user_id=user_id)
    except Exception as error:
        db.rollback()
        raise ChatPersistenceError() from error

    return [_to_history_item(conversation) for conversation in conversations]


def _normalize_message(message: str) -> str:
    normalized = message.strip()
    if not normalized:
        raise ChatValidationError()
    if len(normalized) > MAX_MESSAGE_LENGTH:
        raise ChatValidationError()
    return normalized


def _to_history_item(conversation: Conversation) -> ConversationHistoryItem:
    return ConversationHistoryItem(
        conversation_id=conversation.id,
        question=conversation.question,
        answer=conversation.answer,
        status=conversation.status,
        created_at=conversation.created_at,
    )
