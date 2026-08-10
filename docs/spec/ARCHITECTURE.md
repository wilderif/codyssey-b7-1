# Architecture

이 문서는 application 구조, module responsibility와 module 간 interface를 설명합니다. 구현 변경으로
이 계약이 달라지는 경우 code와 이 문서를 같은 변경에서 함께 갱신합니다. HTTP 결과, DB schema,
Frontend 동작, 실행·배포 설정의 상세값은 각 기술 문서에서 정의합니다.

## 구조 개요

Application은 하나의 FastAPI process 안에서 책임별 module을 분리하는 modular monolith입니다.

```text
Browser
   |
   v
FastAPI (Main + Auth + UI + Chat + Admin + Core)
   |                                      |
   v                                      v
SQLite                                OpenAI API
```

## 인증 방식 결정

### 현재 선택: Session

Browser와 FastAPI가 같은 application에서 동작하므로, 서명된 session cookie로 로그인 사용자 ID만
전달합니다. JWT를 포함한 token 인증은 현재 제공하지 않습니다.

### Session을 선택한 이유

- Server-rendered form과 Browser 화면 흐름에 자연스럽게 연결됩니다.
- `HttpOnly`, `SameSite=Lax`, production `Secure` cookie 설정으로 Browser JavaScript에 session
  정보를 노출하지 않습니다.
- Auth module이 사용자 조회와 관리자 권한을 server에서 일관되게 판단할 수 있습니다.

### Token 기반 인증이 필요한 경우

- mobile app이나 외부 client가 Browser session 없이 API를 호출해야 하는 경우
- frontend와 API가 서로 다른 origin에서 독립 배포되는 경우
- service-to-service API처럼 cookie session을 공유할 수 없는 호출이 필요한 경우

### Token 사용 시 방식

Token 도입이 승인되면 현재 Session 계약을 병행하지 않고 API 계약을 함께 갱신합니다. Client는
`Authorization: Bearer <access token>`으로 짧은 수명의 access token을 전달하고, token에는 사용자
식별자·권한·만료 정보를 포함합니다. refresh, revoke, logout, CORS와 token 보관 방식은 도입 시점의
보안 요구사항에 맞춰 별도 계약으로 정의합니다.

## 주요 Component

| Component | 역할 |
| --- | --- |
| Browser | 회원가입·login, 질문 입력, AI 답변과 본인 기록 확인, 관리자 운영 metadata 조회 |
| `app/main.py` | FastAPI application 생성, SessionMiddleware와 router 등록, DB·관리자 초기화 조립 |
| `app/auth` | User, 회원가입·login·logout, password 검증, 인증·관리자 dependency |
| `app/chat` | 질문 검증, 사용자 대화 문맥, OpenAI 호출, 사용자 ChatExchange 저장·조회 |
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
| `docs/spec/DEPLOYMENT.md` | environment variable, local 실행과 deployment 구성 | 김우종 |

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

## 공유 interface

### Config

`app/core/config.py`는 environment variable의 loading, type 변환과 값 자체의 validation을 담당합니다.
정확한 설정 key, 기본값과 환경별 값은 [실행·배포 계약](DEPLOYMENT.md)에서 정의합니다. 각 business
module은 자신이 소비하는 설정의 use-case 조건을 검증하며, secret 원문을 error, `repr`, log 또는
console 출력에 노출하지 않습니다.

### Database

```python
from app.core.database import Base, SessionLocal, get_db, init_db
```

- `Base`, engine과 Session factory는 `app/core/database.py`에서만 생성합니다.
- `get_db()`는 request별 Session을 열고 반드시 닫으며 자동 commit하지 않습니다.
- `User`와 `ChatExchange`는 같은 `Base`를 사용합니다.
- `app/main.py`가 두 model을 import한 뒤 `init_db()`를 호출합니다.
- SQLite 연결과 schema의 상세 동작은 [DB schema 계약](db/DB.md)을 따릅니다.

### Request ID

```python
from app.core.request_id import RequestIdMiddleware, get_request_id
```

- `RequestIdMiddleware`는 HTTP request마다 server-generated UUID를 생성하고
  `request.state.request_id`에 저장합니다.
- client가 보낸 request ID는 신뢰하거나 server request ID로 재사용하지 않습니다.
- `get_request_id()`는 Router가 현재 request ID를 Service에 전달하는 공용 interface입니다.
- response의 `X-Request-ID`, server log와 `ChatExchange.request_id`는 같은 값을 사용합니다.
- Core는 공통 logging 설정을 제공하고, Router는 request ID를 Service에 전달합니다. 각 Service는
  자신이 소유한 request 수신, 외부 API 호출과 persistence 성공·실패 event를 application logging
  interface로 기록합니다.

### Auth → UI·Chat

```python
from app.auth.service import (
    authenticate_user,
    ensure_initial_admin,
    register_user,
)
from app.auth.dependencies import (
    clear_session_user_id,
    get_current_user_id,
    get_session_user_id,
    require_admin,
    set_session_user_id,
)
```

```python
def register_user(*, db: Session, username: str, password: str) -> User: ...
def authenticate_user(*, db: Session, username: str, password: str) -> User | None: ...
def ensure_initial_admin(*, db: Session, app_settings: Settings) -> None: ...
def set_session_user_id(request: Request, *, user_id: int) -> None: ...
def get_session_user_id(request: Request) -> int | None: ...
def clear_session_user_id(request: Request) -> None: ...
def get_current_user_id(request: Request) -> int: ...
def require_admin(...): ...
```

- `User`는 역할을 저장하는 `role` field를 포함합니다. 일반 회원가입 계정은 일반 사용자,
  초기 `admin` 계정은 관리자 역할로 생성합니다.
- `ensure_initial_admin()`은 시작 시 `role=admin` 계정 존재 여부를 확인합니다. username과 관계없이
  관리자 역할 계정이 하나라도 있으면 기존 계정을 변경하지 않고 종료합니다.
- 관리자 역할 계정이 없으면 `create_app()`에서 전달된 실행 설정의 초기 관리자 password를
  검증·hash하여 username
  `admin`, role `admin`인 초기 계정을 생성합니다. 이때 username `admin`이 일반 사용자 역할로 이미
  존재하면 자동 승격하지 않고 명확한 설정 오류로 시작을 중단합니다.
- 초기 관리자 생성이 필요한데 password가 누락되었거나 유효하지 않으면 시작을 중단하고 원인을
  식별 가능한 log에 남깁니다. 초기 비밀번호 원문은 기록하지 않습니다.
- Auth는 session에 사용자 ID를 저장·조회·삭제하는 public helper의 mechanics를 소유합니다.
  UI Router는 session key를 직접 읽거나 쓰지 않고, login 인증 성공과 logout 요청에서 이 helper를
  호출합니다.
- `get_current_user_id()`와 `require_admin`은 Router가 인증·권한 결과를 얻는 public dependency입니다.
  외부 HTTP 결과는 [API 계약](api/API.md)을 따르며 UI는 관리자 여부를 최종 판별하지 않습니다.

### Chat → Auth·UI

```python
from app.chat.service import (
    get_chat_exchange,
    list_chat_exchange_history,
    process_chat,
)
```

- `process_chat()`은 질문 검증, 사용자 대화 문맥, OpenAI 호출과 성공·실패 record 저장을
  책임집니다. 성공 또는 실패 record 저장이 완료된 뒤 결과나 OpenAI 오류를 반환합니다.
- 사용 model, system prompt와 OpenAI message 구성의 상세 계약은 [AI 호출 계약](ai/AI.md)을
  따릅니다.
- Chat Router는 공용 request ID interface에서 받은 ID를 `process_chat()`에 명시적으로
  전달합니다.
- DB 저장 실패는 rollback하며, 외부 HTTP 결과는 [API 계약](api/API.md)을 따릅니다.
- History는 로그인 사용자의 record만 최신순으로 제공하며 내부 `error_message`와 운영
  metadata를 포함하지 않습니다.
- `get_chat_exchange()`는 `chat_exchange_id`와 `user_id`를 함께 조건으로 조회합니다. 없는 ID와
  다른 사용자의 ID는 모두 `None`을 반환하고 Router가 같은 API 결과로 변환합니다.

### Admin → Auth·UI·Main

```python
from app.admin.service import list_admin_chat_operation_metadata
from app.admin.router import router as admin_router
from app.auth.dependencies import require_admin
```

- `app/admin/router.py`가 `GET /admin/logs` HTTP use case를 소유하고 `require_admin`·`get_db`
  dependency와 Admin Service를 연결합니다.
- Admin Repository는 Auth·Chat ORM model을 직접 사용하는 read-only query를 수행하고, Admin
  Service는 화면에 허용된 운영 metadata만 projection합니다. Query와 projection field의 상세
  계약은 [DB schema 계약](db/DB.md)을 따릅니다.
- Admin은 별도 JSON API, 수정·삭제 CRUD, 고급 검색·pagination, 별도 운영 log table, 별도
  역할·권한 table을 제공하지 않습니다. 사용자 역할은 `users.role`을 사용합니다.
- Main은 `admin_router` 등록만 담당합니다.

### UI·Main integration

- `app/ui`의 화면 구조, Browser 상태, interaction, 접근성, responsive 동작은
  [Frontend UI 계약](ui/UI.md)을 따릅니다.
- UI Router는 Auth·Chat Service와 Auth session helper를 사용해 사용자 화면 흐름을 구성하고,
  Chat Router는 Auth와 DB dependency를 Chat JSON API에 연결합니다. 경로와 HTTP 결과의 상세
  계약은 [API 계약](api/API.md)을 따릅니다.
- Admin Router는 권한 dependency와 Admin Service를 연결해 read-only 운영 metadata를 UI template에
  전달합니다.
- `app/main.py`는 UI·Chat·Admin router, SessionMiddleware, logging, health, `init_db()`를 연결하고,
  DB 초기화 후 요청을 받기 전에 `create_app()`이 선택한 실행 설정을 전달하여
  `ensure_initial_admin()`을 호출합니다.
- server log는 요청 수신, AI 호출·응답, DB 저장 성공·실패를 application logging으로 남깁니다.
  `/admin/logs`는 server runtime log file을 표시하는 화면이 아닙니다.

## 개념적 요청 흐름

### Login과 logout

UI Router가 form을 HTTP 입력으로 변환하고 Auth Service를 호출합니다. 인증 성공 또는 logout 요청이면
Auth가 제공하는 helper로 session 사용자 ID를 저장하거나 삭제하고, Router가 API 계약에 맞는 화면
이동을 반환합니다.

### Chat

Auth dependency가 식별한 `user_id`와 Router가 변환한 질문을 Chat Service에 전달합니다. Chat Service는
사용자 문맥 조회, OpenAI 호출과 성공·실패 persistence를 조정하고 transaction을 완료합니다. Router는
그 결과를 HTTP 응답으로 변환하며 UI는 Browser 상태에 맞게 표시합니다.

### 관리자 조회

Admin Router가 Auth의 관리자 dependency를 적용하고 Admin Service를 호출합니다. Admin Service와
Repository는 허용된 read-only 운영 metadata를 조회하며 UI template은 전달받은 projection만
표시합니다.

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
- schema와 persistence 제약의 상세 계약은 [DB schema 계약](db/DB.md)을 따름
