# API 계약

> 📑 이 페이지가 HTTP 경로, session, 입력, 응답, 오류의 단일 기준입니다. 현재는 계약만
> 확정되었고 구현 결과를 의미하지 않습니다.

## 1. 공통 계약

| 항목 | 계약 |
| --- | --- |
| 인증 | Starlette `SessionMiddleware`의 서명된 session cookie 사용. JWT·token 인증 없음 |
| Session data | login 사용자 ID만 저장. 서명되지만 암호화된 저장소로 간주하지 않음 |
| Secret key | `SESSION_SECRET` environment variable에서 load |
| 만료 | 8시간(`max_age=28800`) |
| Cookie | `HttpOnly=true`, `SameSite=Lax`, 배포 환경 `Secure=true` |
| 관리자 | environment variable로 load한 `settings.admin_usernames` allowlist로 판별. DB role field 없음 |
| 시간 | DB는 UTC, API는 UTC ISO 8601(`Z`) 사용 |
| 내부정보 | SQL 오류, 전체 stack, key, cookie, 내부 `error_message`를 API·화면에 노출하지 않음 |

## 2. 사용자 URL

Browser가 직접 이동하거나 form을 제출하는 HTML 경로입니다.

| 순서 | Method | 경로 | 역할 | 성공 | 실패·unauthenticated |
| --- | --- | --- | --- | --- | --- |
| 1 | `GET` | `/` | 시작 경로 | login `303 /chat` · unauthenticated `303 /login` | 해당 없음 |
| 2 | `GET` | `/signup` | 회원가입 화면 | `200 signup.html` | 해당 없음 |
| 3 | `POST` | `/signup` | 회원가입 처리 | automatic login 없이 `303 /login` | 동일 화면 `400` |
| 4 | `GET` | `/login` | login 화면 | `200 login.html` | 해당 없음 |
| 5 | `POST` | `/login` | login 처리 | session 생성 후 `303 /chat` | 동일 화면 `400` |
| 6 | `GET` | `/chat` | chat·본인 대화 기록 화면 | `200 chat.html` | `303 /login` |
| 7 | `POST` | `/logout` | logout 처리 | session 삭제 후 `303 /login` | unauthenticated도 `303 /login` |
| 관리자 | `GET` | `/admin/logs` | 읽기 전용 server log 화면 | 관리자 `200 admin_logs.html` | unauthenticated `303 /login` · 비관리자 `403` |

- form 성공 후 이동은 모두 `303 See Other`를 사용합니다.
- `username`: 앞뒤 공백 제거 후 3~30자
- `password`: 8~72자
- 중복 username·길이 오류는 사용자용 message와 함께 동일 화면을 `400`으로 다시 rendering합니다.
- login 실패는 `아이디 또는 비밀번호가 올바르지 않습니다.`만 사용해 username 존재 여부를 구분하지 않습니다.
- 사용자용 별도 `/logs` 화면은 만들지 않습니다. `GET /chat`이 이전 대화와 입력창을 함께 rendering합니다.

### Chat 화면 계약

`GET /chat`은 login 사용자의 기록만 최신순으로 조회해 입력창과 함께 `chat.html`을 rendering합니다.

- Template variable: `chat_exchanges`
- 항목: `chat_exchange_id`, `question`, `answer`, `status`, `created_at`
- `answer=null`이고 `status=failed`이면 `답변을 생성하지 못했습니다.` 표시
- 내부 `error_message`는 template에 전달하지 않음

### 관리자 server log 화면 계약

`GET /admin/logs`는 environment variable allowlist에 포함된 관리자만 접근할 수 있습니다.

- server 운영 log를 조회하는 읽기 전용 화면입니다.
- 사용자 질문·답변 목록을 조회하는 화면으로 사용하지 않습니다.
- 관리자 수정·삭제 API는 제공하지 않습니다.

## 3. Server API

| Method | 경로 | 인증 | 역할 |
| --- | --- | --- | --- |
| `POST` | `/api/chat` | 필수 | 질문 검증, 문맥 구성, OpenAI 호출, 대화 저장 |
| `GET` | `/api/chat-exchanges` | 필수 | login 사용자의 전체 질문·답변 조회 |
| `GET` | `/api/chat-exchanges/{chat_exchange_id}` | 필수 | login 사용자의 특정 질문·답변 단건 조회 |
| `GET` | `/health` | 불필요 | process 상태만 확인 |

- 대화 기록 JSON 조회는 `GET /api/chat-exchanges`와
  `GET /api/chat-exchanges/{chat_exchange_id}`를 사용합니다.
- 보호된 JSON 경로의 unauthenticated 응답은 `401 {"detail":"로그인이 필요합니다."}`입니다.
- 대화 기록 API는 login 사용자가 소유한 record만 반환하고 내부 `error_message`를 노출하지 않습니다.

## 4. Chat API schema

### 요청

```http
POST /api/chat
Content-Type: application/json
```

```json
{
  "message": "FastAPI의 장점을 설명해주세요."
}
```

- `message`는 문자열 필수입니다.
- 앞뒤 공백 제거 결과가 1~1000자여야 합니다.
- field 누락, 잘못된 type, 잘못된 JSON은 FastAPI·Pydantic 기본 `422`입니다.
- 공백 입력과 1000자 초과 문자열은 `400`입니다.

### 성공 응답

```json
{
  "chat_exchange_id": 15,
  "answer": "FastAPI는 Python 기반의 web framework입니다.",
  "created_at": "2026-08-04T06:00:00Z"
}
```

- `chat_exchange_id`는 `chat_exchanges.id`를 의미합니다.
- 답변 저장이 성공한 뒤에만 `200 OK`를 반환합니다.

## 5. 대화 기록 API schema

### 전체 대화 조회

```http
GET /api/chat-exchanges
```

login 사용자의 전체 질문·답변을 최신순 JSON array로 반환합니다.

```json
[
  {
    "chat_exchange_id": 15,
    "question": "FastAPI의 장점을 설명해주세요.",
    "answer": "FastAPI는 Python 기반의 web framework입니다.",
    "status": "success",
    "created_at": "2026-08-04T06:00:00Z"
  }
]
```

### 단건 대화 조회

```http
GET /api/chat-exchanges/{chat_exchange_id}
```

login 사용자가 소유한 특정 질문·답변 한 건을 반환합니다.

```json
{
  "chat_exchange_id": 15,
  "question": "FastAPI의 장점을 설명해주세요.",
  "answer": "FastAPI는 Python 기반의 web framework입니다.",
  "status": "success",
  "created_at": "2026-08-04T06:00:00Z"
}
```

- 존재하지 않거나 login 사용자의 record가 아니면 `404`를 반환합니다.
- `status=failed` record의 `answer`는 `null`입니다.
- 두 API 모두 내부 `error_message`를 반환하지 않습니다.

## 6. 오류 응답

| 상태 | 상황 | 응답 |
| --- | --- | --- |
| `400` | 빈 문자열·공백 | `{"detail":"질문을 입력해주세요."}` |
| `400` | 공백 제거 후 1000자 초과 | `{"detail":"질문은 1000자 이하로 입력해주세요."}` |
| `401` | unauthenticated JSON 요청 | `{"detail":"로그인이 필요합니다."}` |
| `404` | 대화 record가 없거나 login 사용자의 소유가 아님 | `404 Not Found` |
| `422` | field 누락·type·JSON 형식 오류 | FastAPI 기본 검증 응답 |
| `500` | DB 저장 실패·예상하지 못한 server 오류 | `{"detail":"서버 오류가 발생했습니다. 잠시 후 다시 시도해주세요."}` |
| `502` | OpenAI API 오류 | `{"detail":"AI 응답 생성에 실패했습니다. 잠시 후 다시 시도해주세요."}` |
| `504` | OpenAI 30초 시간 초과 | `{"detail":"AI 응답 시간이 초과되었습니다. 잠시 후 다시 시도해주세요."}` |

## 7. 문맥·OpenAI 처리

1. login 사용자 ID로 `status=success` record만 `created_at DESC` 최대 5개 조회합니다.
2. 다른 사용자의 기록과 `failed` 기록은 제외합니다.
3. 조회한 5개를 오래된 순서로 뒤집습니다.
4. Chat 내부 단일 상수로 관리하는 system prompt를 첫 `system` message로 추가합니다.
5. 각 과거 `question`은 `user`, `answer`는 `assistant` message로 변환합니다.
6. 현재 질문을 마지막 `user` message로 추가합니다.
7. 최종 message 순서는 `system → 과거 user·assistant 최대 5쌍 → 현재 user`입니다.
8. `settings.openai_model`과 `OPENAI_TIMEOUT_SECONDS=30`을 적용합니다.
9. 자동 재시도는 `0회`이며 요청당 OpenAI 호출은 정확히 한 번입니다.
10. timeout·API 오류·비정상 response에는 대체 답변을 만들지 않고 실패 record를 저장한 뒤
   오류 응답으로 변환합니다.

## 8. 저장과 오류 우선순위

- 성공: 질문·답변·`status=success`·UTC 시각 저장 후 `200`
- OpenAI 오류: 질문·`answer=null`·`status=failed`·안전한 내부 요약·UTC 시각 저장 후 `502`
- OpenAI 시간 초과: 같은 실패 기록 저장 후 `504`
- OpenAI 비정상 response: 같은 실패 기록 저장 후 `502`
- 예상하지 못한 server 오류: AI 실패로 분류하거나 실패 record를 만들지 않고 `500`
- 위 성공 또는 실패 기록의 **DB 저장 자체가 실패**하면 기록을 남길 수 없으므로 server log에 `db_save_failed`만 기록하고 `500` 반환
- 내부 `error_message`, SQL 오류, stack, 비밀정보는 사용자 응답과 template에 포함하지 않음

## 9. Health API

```json
{"status":"ok"}
```

- `GET /health`, 인증 불필요, 정상 `200`
- OpenAI를 호출하지 않고 초기 버전에서는 DB 연결도 검사하지 않음
