# Architecture

## 주요 Component

| Component | 역할 |
| --- | --- |
| Browser | 회원가입·login, 질문 입력, AI 답변과 본인 기록 확인, 관리자 운영 metadata 조회 |
| `app/main.py` | FastAPI application 생성, SessionMiddleware와 router 등록, DB·관리자 초기화 조립 |
| `app/auth` | User, 회원가입·login·logout, password 검증, 인증·관리자 dependency |
| `app/chat` | 질문 검증, 최근 성공 대화 5개 문맥, OpenAI 호출, 사용자 ChatExchange 저장·조회 |
| `app/admin` | 관리자 전용 route, read-only 통합 조회, 운영 metadata projection |
| `app/core` | environment variable, SQLAlchemy Base·DB session, 보안, request ID, 공통 logging |
| `app/ui` | Jinja2 화면 router, chat·본인 기록·관리자 template, CSS·JavaScript static asset |
| SQLite | 사용자, 질문·답변 쌍, 상태, UTC 시각, 요청별 운영 metadata 저장 |
| OpenAI API | 현재 질문과 사용자별 최근 성공 문맥으로 답변 생성 |

## Directory 구조

```text
app/
├── main.py
├── admin/
│   ├── router.py
│   ├── service.py
│   ├── repository.py
│   └── schemas.py
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

### Module 책임과 소유권

| 경로·영역 | 책임 | 소유자 |
| --- | --- | --- |
| `app/main.py` | application 생성, SessionMiddleware, router 등록, health, DB·관리자 초기화 | 김대웅 |
| `app/auth/**` | User, 회원가입·login·logout, password, 인증·관리자 dependency | 김대웅 |
| `app/chat/**` | 질문 검증, 문맥 구성, OpenAI 호출, 사용자 ChatExchange CRUD·저장·조회 | 이상헌 |
| `app/admin/**` | 관리자 전용 route, read-only 통합 query, 운영 metadata projection | 이상헌 |
| `app/core/database.py` | SQLAlchemy Base, engine, session factory와 요청별 DB session | 이상헌 |
| `app/core/config.py` | environment variable loading·type 변환·validation | 이상헌 |
| `app/core/request_id.py` | HTTP request ID 생성·전달 interface | 김대웅 |
| `app/core/security.py` | password·session 보안 helper | 김대웅 |
| 공통 logging·health | log 설정과 필수 event 형식, `GET /health` | 김대웅 |
| `app/ui/**` | HTML·form router, template, CSS·JavaScript, 화면 흐름 | 김우종 |
| 배포 설정 | `/data` persistent storage와 최종 실행 구성 | 김우종 |

### 공통 원칙

- 의존 방향은 `Main·Router → Service → Repository → Core`입니다.
- `app/main.py`는 router·middleware·model·DB 초기화를 조립하고 business rule을 구현하지 않습니다.
- Router는 HTTP·form·template 변환, Service는 use case와 transaction, Repository는 DB 조회·변경만 담당합니다.
- Repository는 `commit()`하지 않습니다. 쓰기 use case의 Service가 성공 시 `commit()`, 실패 시 `rollback()`합니다.
- `app/chat`은 Auth가 제공한 `user_id: int`만 사용하며 cookie와 User 조회 방식을 알지 않습니다.
- `app/admin`은 관리자 read-side 예외로 `app.auth.models.User`와
  `app.chat.models.ChatExchange` ORM model을 read-only query에 직접 사용할 수 있습니다. Admin은
  Auth·Chat Service 또는 Repository를 조합 호출하지 않습니다.
- `app/ui`는 Auth·Chat Service를 호출하고 Repository와 OpenAI를 직접 호출하지 않습니다.
  `admin_logs.html`과 공통 CSS·JavaScript 등 관리자 표현 자원은 제공하지만 `/admin/logs` route와
  관리자 데이터 조합은 소유하지 않습니다.

## 공유 계약

### Config

```python
from app.core.config import settings
```

```python
settings.database_url
settings.session_secret
settings.openai_api_key
settings.openai_model
settings.openai_timeout_seconds
settings.app_env
settings.log_level
settings.admin_username
settings.admin_initial_password
```

- 초기 관리자 계정의 username은 `admin` 하나로 고정합니다. `ADMIN_USERNAME=admin`만 허용하며
  임의 관리자 username 선택 기능은 제공하지 않습니다.
- `ADMIN_INITIAL_PASSWORD`는 최초 관리자 생성에만 사용하는 선택적 secret입니다.
- 초기 `admin` 계정이 없을 때만 `ADMIN_INITIAL_PASSWORD`가 필수입니다. 이 조건부
  검증은 Auth startup Service가 담당하며, `config.py`는 loading·type 변환·validation만 담당합니다.
- secret 원문은 code, error, `repr`, log와 console 출력에 노출하지 않습니다.

### Database

```python
from app.core.database import Base, SessionLocal, get_db, init_db
```

- `Base`, engine과 Session factory는 `app/core/database.py`에서만 생성합니다.
- `get_db()`는 request별 Session을 열고 반드시 닫으며 자동 commit하지 않습니다.
- `User`와 `ChatExchange`는 같은 `Base`를 사용합니다.
- `app/main.py`가 두 model을 import한 뒤 `init_db()`를 호출합니다.
- SQLite에서는 `check_same_thread=False`와 foreign key 활성화를 적용합니다.

### Request ID

```python
from app.core.request_id import RequestIdMiddleware, get_request_id
```

- `RequestIdMiddleware`는 HTTP request마다 server-generated UUID를 생성하고
  `request.state.request_id`에 저장합니다.
- client가 보낸 request ID는 신뢰하거나 server request ID로 재사용하지 않습니다.
- `get_request_id()`는 Router가 현재 request ID를 Service에 전달하는 공용 interface입니다.
- response의 `X-Request-ID`, server log와 `ChatExchange.request_id`는 같은 값을 사용합니다.

### Auth → UI·Chat

```python
from app.auth.service import (
    authenticate_user,
    ensure_initial_admin,
    register_user,
)
from app.auth.dependencies import get_current_user_id, require_admin
```

```python
def register_user(*, db: Session, username: str, password: str) -> User: ...
def authenticate_user(*, db: Session, username: str, password: str) -> User | None: ...
def ensure_initial_admin(*, db: Session) -> None: ...
def get_current_user_id(request: Request) -> int: ...
def require_admin(...): ...
```

- `User`는 역할을 저장하는 `role` field를 포함합니다. 일반 회원가입 계정은 일반 사용자,
  초기 `admin` 계정은 관리자 역할로 생성합니다.
- `ensure_initial_admin()`은 시작 시 `admin` 계정 존재 여부를 확인합니다. 기존
  계정이 있으면 비밀번호를 바꾸지 않고 종료하며, 없으면 `ADMIN_INITIAL_PASSWORD`를 검증·hash하여
  생성합니다.
- 계정이 없는데 password가 누락되었거나 유효하지 않으면 명확한 설정 오류로 시작을 중단하고,
  원인을 식별 가능한 log에 남깁니다. 초기 비밀번호 원문은 기록하지 않습니다.
- `get_current_user_id()`는 보호된 JSON route의 비로그인 요청을 API 계약의 `401`로 변환합니다.
- `require_admin`은 관리자 경로를 검사하고 비관리자를 `403`으로 차단합니다. UI는 관리자
  여부를 최종 판별하지 않습니다.

### Chat → Auth·UI

```python
from app.chat.service import (
    get_chat_exchange,
    list_chat_exchange_history,
    process_chat,
)
```

- `process_chat()`은 질문 검증, 최근 성공 문맥 5개, OpenAI 호출과 성공·실패 record 저장을
  책임집니다. 성공 또는 실패 record 저장이 완료된 뒤 결과나 OpenAI 오류를 반환합니다.
- Chat Router는 공용 request ID interface에서 받은 ID를 `process_chat()`에 명시적으로
  전달합니다.
- DB 저장 실패는 rollback하고 `500`을 `502`·`504`보다 우선합니다.
- History는 로그인 사용자의 record만 최신순으로 제공하며 내부 `error_message`와 운영
  metadata를 포함하지 않습니다.
- `get_chat_exchange()`는 `chat_exchange_id`와 `user_id`를 함께 조건으로 조회합니다. 없는 ID와
  다른 사용자의 ID는 모두 `None`을 반환하고 Router가 같은 `404`로 변환합니다.

### Admin → Auth·UI·Main

```python
from app.admin.service import list_admin_chat_operation_metadata
from app.admin.router import router as admin_router
from app.auth.dependencies import require_admin
```

- `app/admin/router.py`가 `GET /admin/logs` HTTP use case를 소유하고 `require_admin`·`get_db`
  dependency와 Admin Service를 연결합니다.
- Admin Repository는 `chat_exchanges`를 기준으로 `users`를 `ChatExchange.user_id == User.id`로
  `LEFT JOIN`하는 read-only query를 수행합니다. 대응 User가 없는 ChatExchange record도 유지하며
  `username: str | None`으로 제공합니다.
- Admin Service는 정확히 `user_id`, `username`, `chat_exchange_id`, `created_at`, `request_id`,
  `user_agent`, `response_time_ms`, `status`, `error_code`의 9-field projection만 제공합니다.
  `question`, `answer`, `error_message`, `password_hash`와 그 밖의 민감정보는 포함하지 않습니다.
- Admin은 별도 JSON API, 수정·삭제 CRUD, 고급 검색·pagination, 별도 운영 log table, 별도
  역할·권한 table을 제공하지 않습니다. 사용자 역할은 `users.role`을 사용합니다.
- Main은 `admin_router` 등록만 담당합니다.

### UI·Main integration

- `app/ui`의 화면 구조, Browser 상태, interaction, 접근성, responsive 동작은
  [Frontend UI 계약](ui/UI.md)을 따릅니다.
- `GET /chat`은 `list_chat_exchange_history()`로 로그인 사용자의 이전 대화와 입력창을 함께
  렌더링합니다. 사용자용 별도 `/logs` 경로는 제공하지 않습니다.
- `app/chat/router.py`는 `POST /api/chat`, `GET /api/chat-exchanges`,
  `GET /api/chat-exchanges/{chat_exchange_id}`에 `get_current_user_id`와 `get_db`를 연결합니다.
- `/admin/logs`는 `chat_exchanges`의 사용자별 운영 metadata를 읽기 전용으로 표시합니다.
  `app/admin/router.py`가 `require_admin`으로 접근을 검사하고 Admin Service의 projection을
  `admin_logs.html`에 전달합니다. 질문·답변 원문과 내부 `error_message`는 기본 표시에서
  제외합니다.
- `app/main.py`는 UI·Chat·Admin router, SessionMiddleware, logging, health, `init_db()`를 연결하고,
  DB 초기화 후 요청을 받기 전에 `ensure_initial_admin()`을 호출합니다.
- server log는 요청 수신, AI 호출·응답, DB 저장 성공·실패를 application logging으로 남깁니다.
  `/admin/logs`는 server runtime log file을 표시하는 화면이 아닙니다.

## Chat 처리 흐름

1. session cookie에서 로그인 사용자 ID를 확인합니다.
2. JSON 형식과 질문 길이를 검증합니다.
3. 해당 사용자의 `status=success` record만 최신순으로 최대 5개 조회합니다.
4. Chat 내부 system prompt 뒤에 조회 결과를 오래된 순서의 `user`·`assistant` message로 변환합니다.
5. 현재 질문을 마지막 `user` message로 추가합니다.
6. `settings.openai_model`로 OpenAI를 30초 제한, 자동 retry 없이 한 번 호출합니다.
7. 성공 또는 안전한 실패 code, 요청별 운영 metadata를 `ChatExchange`에 저장합니다.
8. JSON 응답을 반환하고 UI가 결과를 표시합니다.

## 핵심 제약

- 사용자마다 하나의 연속 chat만 제공
- 새 chat·대화방 선택·대화방 목록 없음
- `chat_exchanges` 한 record는 질문과 답변 한 쌍
- 다른 사용자의 기록과 실패 기록은 AI 문맥에서 제외
- 사용자 기록은 `/chat` 화면과 본인 소유 record만 반환하는 대화 기록 API에서 조회
- 관리자 수정·삭제 기능과 별도 log table 없음
- 초기 버전은 OpenAI 자동 재시도 없음
- timeout·API 오류·비정상 OpenAI response에는 생성된 대체 답변을 사용하지 않고 실패
  record를 저장한 뒤 API layer가 오류 응답으로 변환
- table 생성은 `Base.metadata.create_all()`, Alembic은 사용하지 않음
