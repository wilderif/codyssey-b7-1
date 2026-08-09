# API 계약

> 📑 이 페이지가 HTTP 경로, session, 입력, 응답, 오류의 단일 기준입니다. 현재는 계약만
> 확정되었고 구현 결과를 의미하지 않습니다.

## 1. 공통 계약

| 항목 | 계약 |
| --- | --- |
| 인증 | Starlette `SessionMiddleware`의 서명된 session cookie 사용. JWT·token 인증 없음 |
| Session data | 로그인 사용자 ID만 저장. 서명되지만 암호화된 저장소로 간주하지 않음 |
| Secret key | `SESSION_SECRET` environment variable에서 load |
| 만료 | 8시간(`max_age=28800`) |
| Cookie | `HttpOnly=true`, `SameSite=Lax`, 배포 환경 `Secure=true` |
| Request ID | server가 request마다 생성하고 `X-Request-ID` response header로 반환. client 제공 값은 재사용하지 않음 |
| 관리자 | `users.role`로 판별. 초기 username은 `admin` 하나이며 `ADMIN_USERNAME=admin`만 허용. 최초 생성 password는 `ADMIN_INITIAL_PASSWORD` |
| 시간 | DB는 UTC, API는 UTC ISO 8601(`Z`) 사용 |
| 내부정보 | SQL 오류, 전체 stack, key, cookie, 내부 `error_message`를 API·화면에 노출하지 않음 |

## 2. HTML·폼 경로

이 section은 HTTP 동작과 template data의 기준입니다. 화면 구조와 Browser interaction은
[Frontend UI 계약](../ui/UI.md)을 따릅니다.

| Method | 경로 | 성공 | 실패·비로그인 | 설명 |
| --- | --- | --- | --- | --- |
| `GET` | `/` | 로그인 `303 /chat` · 비로그인 `303 /login` | 해당 없음 | 메인화면 |
| `GET` | `/signup` | `200 signup.html` | 해당 없음 | 회원가입화면 |
| `POST` | `/signup` | 자동 로그인 없이 `303 /login` | 동일 화면 `400` | 회원가입 처리 |
| `GET` | `/login` | `200 login.html` | 해당 없음 | 로그인화면 |
| `POST` | `/login` | 세션 생성 후 `303 /chat` | 동일 화면 `400` | 로그인 처리 |
| `POST` | `/logout` | 세션 삭제 후 `303 /login` | 비로그인도 `303 /login` | 로그아웃 처리 |
| `GET` | `/chat` | 본인 이전 대화와 입력창을 포함한 `200 chat.html` | 비로그인 `303 /login` | 채팅·사용자 대화 로그 화면 |
| `GET` | `/admin/logs` | 관리자 `200 admin_logs.html` | 비로그인 `303 /login`, 비관리자 `403` | `app/admin/router.py`가 소유하는 관리자 전용 채팅 운영 metadata 조회 화면 |

- form 성공 후 이동은 모두 `303 See Other`를 사용합니다.
- `username`: 앞뒤 공백 제거 후 3~30자, `password`: 8~72자입니다.
- 중복 username·길이 오류는 사용자용 message와 함께 동일 화면을 `400`으로 다시 렌더링합니다.
- 로그인 실패는 `아이디 또는 비밀번호가 올바르지 않습니다.`만 사용해 username 존재 여부를
  구분하지 않습니다.
- `GET /chat`이 사용자 대화 로그 조회 역할을 겸하며 사용자용 별도 `/logs`는 만들지 않습니다.

### Chat 화면 계약

`GET /chat`은 login 사용자의 기록만 최신순으로 조회해 입력창과 함께 `chat.html`을 rendering합니다.

- Template variable: `chat_exchanges`
- 항목: `chat_exchange_id`, `question`, `answer`, `status`, `created_at`
- `answer=null`이고 `status=failed`이면 `답변을 생성하지 못했습니다.` 표시
- 내부 `error_message`와 운영 metadata는 template에 전달하지 않음

### 관리자 채팅 운영 metadata 화면 계약

`GET /admin/logs`는 관리자만 접근하는 읽기 전용 화면이며 server runtime log file을 보여주지
않습니다. `chat_exchanges`에 저장된 사용자별 운영 metadata를 조회합니다.

- 기본 조회 항목: `user_id`, `username`, `chat_exchange_id`, `created_at`, `request_id`,
  `user_agent`, `response_time_ms`, `status`, `error_code`
- `app/admin/router.py`가 `require_admin`으로 접근을 검사하고 Admin Service의 projection을
  `admin_logs.html`에 전달합니다. UI는 route와 관리자 데이터 조합을 담당하지 않습니다.
- 질문·답변 원문, 내부 `error_message`, `password_hash`와 그 밖의 민감정보는 projection과 화면에서
  제외합니다.
- 별도 관리자 JSON API, 관리자 수정·삭제 CRUD, 고급 검색·pagination, 별도 운영 log table은
  제공하지 않습니다.
- 별도 역할·권한 table은 추가하지 않으며 사용자 역할은 `users.role`을 사용합니다.

## 3. JSON 경로

| Method | 경로 | 인증 | 역할 |
| --- | --- | --- | --- |
| `POST` | `/api/chat` | 필수 | 질문 검증, 문맥 구성, OpenAI 호출, 대화 저장 |
| `GET` | `/api/chat-exchanges` | 필수 | 로그인 사용자의 전체 질문·답변을 JSON으로 반환 |
| `GET` | `/api/chat-exchanges/{chat_exchange_id}` | 필수 | 로그인 사용자의 특정 질문·답변 한 건을 JSON으로 반환 |
| `GET` | `/health` | 불필요 | process 상태만 확인 |

- 보호된 JSON 경로의 비로그인 응답은
  `401 {"code":"not_authenticated","detail":"로그인이 필요합니다."}`입니다.
- 사용자 API는 내부 `error_message`와 운영 metadata를 반환하지 않습니다.

## 4. Chat API 요청과 응답

### 요청

```http
POST /api/chat
Content-Type: application/json
```

```json
{"message":"FastAPI의 장점을 설명해주세요."}
```

- `message`는 문자열 필수이며, 앞뒤 공백 제거 결과가 1~1000자여야 합니다.
- 필드 누락·잘못된 자료형·잘못된 JSON은 `422 validation_error`입니다.
- 공백 입력과 1000자 초과 문자열은 `400 validation_error`입니다.

### 성공 응답

```json
{
  "chat_exchange_id": 15,
  "answer": "FastAPI는 Python 기반의 웹 프레임워크입니다.",
  "created_at": "2026-08-04T06:00:00Z"
}
```

- `chat_exchange_id`는 `chat_exchanges.id`를 의미합니다.
- 답변 저장이 성공한 뒤에만 `200 OK`를 반환합니다.

## 5. 대화 기록 조회 API

`GET /api/chat-exchanges`는 로그인 사용자의 전체 history를 JSON array로 반환합니다.

```json
[
  {
    "chat_exchange_id": 15,
    "question": "FastAPI의 장점을 설명해주세요.",
    "answer": "FastAPI는 Python 기반의 웹 프레임워크입니다.",
    "status": "success",
    "created_at": "2026-08-04T06:00:00Z"
  }
]
```

`GET /api/chat-exchanges/{chat_exchange_id}`는 로그인 사용자가 소유한 한 건을 같은 field로
반환합니다. 존재하지 않거나 다른 사용자의 record면 모두 `404 conversation_not_found`를
반환합니다. 두 API 모두 내부 `error_message`와 운영 metadata를 반환하지 않습니다.

- `status=failed`인 항목은 `answer: null`을 반환합니다.

## 6. 오류 응답

JSON API 오류는 `{"code":"...","detail":"..."}` 형식으로 통일합니다. `code`는
frontend 분기·자동화 test·운영 추적에 쓰는 안정적인 lower_snake_case 식별자이고, `detail`은
locale에 따라 변환되는 사용자용 안전 message입니다.

| 상태 | 상황 | code | 기본 `ko` detail |
| --- | --- | --- | --- |
| `400` | 빈 문자열·공백 | `validation_error` | `질문을 입력해주세요.` |
| `400` | 공백 제거 후 1000자 초과 | `validation_error` | `질문은 1000자 이하로 입력해주세요.` |
| `401` | 비로그인 JSON 요청 | `not_authenticated` | `로그인이 필요합니다.` |
| `403` | 권한 부족 JSON 요청 | `forbidden` | `접근 권한이 없습니다.` |
| `404` | 대화 기록 없음 또는 다른 사용자 소유 | `conversation_not_found` | `대화 기록을 찾을 수 없습니다.` |
| `422` | 필드 누락·자료형·JSON 형식 오류 | `validation_error` | `요청 형식이 올바르지 않습니다.` |
| `500` | DB 저장 실패 | `db_save_error` | `서버 오류가 발생했습니다. 잠시 후 다시 시도해주세요.` |
| `500` | 분류되지 않은 내부 오류 | `internal_error` | `서버 오류가 발생했습니다. 잠시 후 다시 시도해주세요.` |
| `502` | OpenAI API 오류 | `openai_api_error` | `AI 응답 생성에 실패했습니다. 잠시 후 다시 시도해주세요.` |
| `504` | OpenAI 30초 timeout | `openai_timeout` | `AI 응답 시간이 초과되었습니다. 잠시 후 다시 시도해주세요.` |

- 단일 `AppError`와 공통 handler가 프로젝트 정의 오류를 `code`·`detail` 형식으로 변환합니다.
  오류별 하위 예외 class는 만들지 않습니다.
- `RequestValidationError`는 전용 handler로 `422 validation_error`로 변환합니다.
- `HTTPException.detail`에 객체를 넣어 `{"detail":{"code":...}}`처럼 한 번 더 감싸지 않습니다.

### i18n 오류 message

- 초기 지원 locale은 `ko`, `en`입니다.
- locale 우선순위는 HTTP `Accept-Language` header, 기본 locale `ko` 순서입니다.
- 미지원 locale, 해석 불가 header, 누락된 번역 key는 모두 `ko`로 fallback합니다.
- 같은 `code`는 locale과 무관하게 의미와 HTTP 상태 code가 동일합니다. frontend는 `detail`이
  아니라 `code`를 기준으로 분기합니다.
- 번역 message에는 내부 예외, key, cookie, SQL, stack 정보를 포함하지 않습니다.
- 예를 들어 `openai_api_error`의 `en` detail은
  `Failed to generate an AI response. Please try again later.`입니다.

## 7. 문맥·OpenAI·저장 정책

1. 로그인 사용자 ID로 `status=success` record만 `created_at DESC` 최대 5개 조회합니다.
2. 다른 사용자의 record와 `failed` record는 제외하고, 결과를 오래된 순서로 뒤집습니다.
3. system prompt → 과거 user·assistant 최대 5쌍 → 현재 user 순서로 message를 구성합니다.
4. `settings.openai_model`, `OPENAI_TIMEOUT_SECONDS=30`을 사용하며 자동 retry는 하지 않습니다.

- 성공: `status=success`, `error_code=null` record를 UTC 시각·운영 metadata와 함께 저장한 뒤 `200`을 반환합니다.
- OpenAI 오류: `status=failed`, `error_code=openai_api_error` record를 저장한 뒤 `502`를 반환합니다.
- timeout: `status=failed`, `error_code=openai_timeout` record를 저장한 뒤 `504`를 반환합니다.
- 분류되지 않은 내부 오류는 `500 internal_error`이며 안전하게 저장 가능한 실패 경로라면
  `error_code=internal_error`를 저장할 수 있습니다.
- DB 저장 자체가 실패하면 같은 DB에 실패 record를 남기지 않고 `db_save_failed`를 server log에
  남긴 뒤 `500 db_save_error`를 반환합니다.
- `validation_error`, `not_authenticated`, `conversation_not_found`, `forbidden`, `db_save_error`는
  일반적으로 `ChatExchange.error_code`에 저장하지 않습니다.


## 8. Health API

```json
{"status":"ok"}
```

- `GET /health`, 인증 불필요, 정상 `200`
- OpenAI를 호출하지 않고 초기 버전에서는 DB 연결도 검사하지 않음
