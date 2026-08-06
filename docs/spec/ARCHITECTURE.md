# Architecture

## 주요 Component

| Component | 역할 |
| --- | --- |
| Browser | 회원가입·login, 질문 입력, AI 답변과 본인 기록 확인 |
| `app/main.py` | FastAPI application 생성, SessionMiddleware와 router 등록 |
| `app/auth` | 회원가입·login·logout, password 검증, 인증 사용자 확인 |
| `app/chat` | 질문 검증, 최근 성공 대화 5개 문맥, OpenAI 호출, 성공·실패 저장 |
| `app/core` | environment variable, SQLAlchemy Base·DB session, 보안, 공통 logging |
| `app/ui` | Jinja2 화면 router, template, CSS·JavaScript static asset |
| SQLite | 사용자와 질문·답변 쌍, 상태, UTC 시각 저장 |
| OpenAI API | 현재 질문과 사용자별 최근 성공 문맥으로 답변 생성 |

## Directory 구조

```text
app/
├── main.py
├── auth/
├── chat/
├── core/
└── ui/
    ├── router.py
    ├── templates/
    └── static/
```

## Module 경계

> 🧱 file 소유권은 동시 수정 충돌을 줄이기 위한 기본 경계입니다. 공용 file 변경은
> 관련 담당자와 합의한 뒤 PR에 명시합니다.

### Module 책임

| 경로·영역 | 책임 |
| --- | --- |
| `app/main.py` | application 생성, SessionMiddleware, router 등록, health 연결 |
| `app/auth/**` | User, 회원가입·login·logout, password, 인증 dependency |
| `app/chat/**` | 질문 검증, 문맥 구성, OpenAI 호출, 대화 저장·조회 |
| `app/core/database.py` | SQLAlchemy Base, engine, session factory와 요청별 DB session 제공 |
| `app/core/config.py` | environment variable loading과 공통 설정 |
| `app/core/security.py` | password·session 관련 보안 helper |
| 공통 logging·health | log 설정과 필수 event 형식, `GET /health` |
| `app/ui/**` | `router.py`, Jinja2 template, CSS·JavaScript, 화면 흐름 |
| 배포 설정 | Railway? 설정, `/data` Volume, 시작 명령 |
| `README`, `CONTRIBUTING`, `.env.example` | 실행·협업·environment variable 문서 |

### 공유 계약

- SQLAlchemy `Base`와 DB session은 `app/core/database.py`에서만 생성하고 다른 module은 import해서 사용합니다.
- `app/ui`는 OpenAI를 직접 호출하거나 DB 쓰기 규칙을 중복 구현하지 않습니다.
- `app/chat`은 `app/auth`가 제공한 login 사용자 ID를 사용하고 다른 사용자의 record를 조회하지 않습니다.
- `app/chat/service.py`는 `ConversationRepository` Protocol에 의존하고, production에서는
  `SqlAlchemyConversationRepository`를 조립해 사용합니다.
- Repository는 query·flush만 수행하고, Conversation 저장의 `commit()`·`rollback()`은
  Chat Service가 소유합니다.
- `app/main.py` router 등록 변경은 관련 담당자가 병합하거나 사전 합의합니다.
- HTTP 동작은 [API 계약](api/API.md), DB field는 [DB schema 계약](db/DB.md)을 기준으로 삼습니다.

## Chat 처리 흐름

1. session cookie에서 login 사용자 ID 확인
2. JSON 형식과 질문 길이 검증
3. 해당 사용자의 `status=success` 기록을 최신순으로 최대 5개 조회
4. Chat 내부 단일 system prompt 뒤에 조회 결과를 오래된 순으로 `question → user`,
   `answer → assistant` message로 변환
5. 현재 질문을 마지막 `user` message로 추가
6. `settings.openai_model`로 OpenAI를 30초 제한, 자동 retry 없이 한 번 호출
7. 성공 또는 안전한 오류 code만 담은 AI 실패 record를 SQLite에 저장
8. JSON 응답을 반환하고 UI가 결과를 표시

## 핵심 제약

- 사용자마다 하나의 연속 chat만 제공
- 새 chat·대화방 선택·대화방 목록 없음
- `conversations` 한 record는 질문과 답변 한 쌍
- 다른 사용자의 기록과 실패 기록은 AI 문맥에서 제외
- 초기 버전은 OpenAI 자동 재시도 없음
- timeout·API 오류·비정상 OpenAI response에는 생성된 대체 답변을 사용하지 않고 실패
  record를 저장한 뒤 API layer가 오류 응답으로 변환
- table 생성은 `Base.metadata.create_all()`, Alembic은 사용하지 않음
