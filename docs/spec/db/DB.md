# DB schema 계약

> 🗄️ 이 페이지가 SQLite table, 저장 실패 정책, 평가자 DB 확인 방법의 단일 기준입니다.
> 현재는 schema 계약이며 구현 결과가 아닙니다.

## 1. Model 원칙

- `users 1 : N chat_exchanges`
- `chat_exchanges` 한 record는 사용자 질문과 AI 답변 한 쌍이며 해당 채팅 요청의 운영
  metadata를 함께 저장합니다.
- 운영 metadata를 위한 별도 log table은 만들지 않습니다.
- 사용자별 하나의 연속 chat만 제공하므로 대화방과 message table을 분리하지 않습니다.
- 초기 table 생성은 `Base.metadata.create_all()`을 사용하고 Alembic은 도입하지 않습니다.
- SQLAlchemy `Base`와 DB session은 `app/core/database.py`에서 제공하며 다른 module은 import해서 사용합니다.

## 2. Table schema

### `users`

| Field | Type | 조건 |
| --- | --- | --- |
| `id` | Integer | PK |
| `username` | String | Unique, Not Null |
| `password_hash` | String | Not Null |
| `role` | String | Not Null. 사용자 역할 저장 |
| `created_at` | DateTime | Not Null, UTC |

일반 회원가입 계정은 일반 사용자 역할로 저장합니다. 초기 관리자 계정의 username은 `admin` 하나이며
관리자 역할로 저장합니다.

### `chat_exchanges`

| Field | Type | 조건 |
| --- | --- | --- |
| `id` | Integer | PK. API의 `chat_exchange_id` |
| `user_id` | Integer | FK → `users.id`, Not Null |
| `question` | Text | Not Null |
| `answer` | Text | 성공 시 답변, 실패 시 Null 가능 |
| `status` | String | Not Null, `success` 또는 `failed` |
| `error_message` | Text | Nullable, 안전한 내부 요약만 저장 |
| `created_at` | DateTime | Not Null, UTC |
| `request_id` | String(64) | Unique, Not Null. 채팅 요청 추적 ID |
| `user_agent` | String(512) | Nullable. User-Agent, 최대 512자 |
| `response_time_ms` | Integer | Not Null, 0 이상. Chat Service 질문 처리 시작부터 성공/실패 ChatExchange를 DB에 저장하기 위해 Repository에 전달하는 시점까지의 application 처리 시간(ms). DB `commit()` 시간은 제외 |
| `error_code` | String(50) | Nullable. 실패 원인 분류 code, 성공 시 Null |

## 3. 상태와 운영 metadata 불변식

| status | answer | error_message | error_code |
| --- | --- | --- | --- |
| `success` | Not Null | Null | Null |
| `failed` | Null | Not Null | 실패 원인 code |

DB schema는 `CheckConstraint`로 status 값과 answer·error message 조합을 함께 강제합니다.

- `request_id`: 최대 64자, `UNIQUE`, `NOT NULL`. server log와 DB record를 연결하는 요청별 ID입니다.
- `response_time_ms`: `NOT NULL`, 0 이상의 정수입니다. Chat Service 질문 처리 시작부터 성공/실패
  ChatExchange를 DB에 저장하기 위해 Repository에 전달하는 시점까지를 기록하며 DB `commit()` 시간은
  포함하지 않습니다. commit 완료 시각을 기록하기 위한 추가 `UPDATE`나 두 번째 `commit()`은 하지
  않습니다.
- `error_code`: 최대 50자이며 성공 시 Null입니다.
- `user_agent`: 최대 512자이며 header가 없으면 Null을 허용합니다.
- raw header, Cookie, Authorization, session ID, OpenAI API key, password와 `password_hash`는
  운영 metadata에 저장하지 않습니다.
- `request_method`, `request_path`는 채팅 요청에서 고정이므로 `chat_exchanges`에 저장하지 않습니다.

## 4. 조회 정책

### OpenAI 문맥 조회

```sql
SELECT id, question, answer, created_at
FROM chat_exchanges
WHERE user_id = :user_id
  AND status = 'success'
ORDER BY created_at DESC, id DESC
LIMIT 5;
```

동일한 `created_at`에서는 `id DESC`를 결정적인 tie-breaker로 사용하고, application에서 결과를
오래된 순서로 뒤집어 OpenAI에 전달합니다.

### 사용자 대화 기록 조회

```sql
SELECT id, question, answer, status, created_at
FROM chat_exchanges
WHERE user_id = :user_id
ORDER BY created_at DESC, id DESC;
```

사용자 화면과 API projection은 `error_message`와 운영 metadata를 제외합니다.

### 관리자 운영 metadata 조회

`app/admin/repository.py`는 `chat_exchanges`를 기준으로 `users`를
`ChatExchange.user_id == User.id` 조건으로 `LEFT JOIN`하는 read-only query를 수행합니다. Admin
Repository는 `app.auth.models.User`와 `app.chat.models.ChatExchange` ORM model을 직접 read-only로
사용할 수 있으며 Auth·Chat Service 또는 Repository를 호출하지 않습니다.

관리자 projection은 정확히 `user_id`, `username`, `chat_exchange_id`, `created_at`, `request_id`,
`user_agent`, `response_time_ms`, `status`, `error_code`만 반환합니다. 대응 User가 없는
ChatExchange record도 유지하고 `username: str | None`을 허용합니다. `question`, `answer`,
`error_message`, `password_hash`와 그 밖의 민감정보는 select·projection에 포함하지 않습니다.

이 조회를 위해 별도 관리자 JSON API, 수정·삭제 CRUD, 고급 검색·pagination, 별도 운영 log table은
추가하지 않습니다.

## 5. 저장 정책

### 성공

- `status=success`, `answer`와 UTC `created_at` 저장
- `request_id`, 선택적 `user_agent`, `response_time_ms` 저장
- `error_message=null`, `error_code=null`

### AI 오류·timeout

- `status=failed`, `answer=null`, 안전한 내부 `error_message`, UTC `created_at` 저장
- `request_id`, 선택적 `user_agent`, `response_time_ms` 저장
- OpenAI API 오류는 `error_code=openai_api_error`, timeout은 `error_code=openai_timeout`

### 예상하지 못한 내부 오류

- API는 `internal_error`를 사용합니다.
- 질문 수신 후 발생했고 실패 record를 안전하게 저장할 수 있으면
  `ChatExchange.error_code=internal_error`를 저장할 수 있습니다.
- 검증·인증·조회·권한 단계의 `validation_error`, `not_authenticated`,
  `conversation_not_found`, `forbidden`은 일반적으로 ChatExchange를 생성하지 않습니다.

### DB 저장 자체 실패

해당 record는 저장할 수 없습니다. server log에 `db_save_failed` event를 남기고 API는 다음
응답을 반환합니다.

```json
{"code":"db_save_error","detail":"서버 오류가 발생했습니다. 잠시 후 다시 시도해주세요."}
```

`db_save_error`는 DB 저장 자체가 실패했으므로 `ChatExchange.error_code`에 저장하지 않습니다.
내부 SQL 오류, 전체 stack, 비밀정보는 응답에 포함하지 않으며 `error_message`는 화면과 API에
노출하지 않습니다.

## 6. SQLite 위치와 영속성

- local: `DATABASE_URL=sqlite:///./data/chatbot.db`
- 배포: `DATABASE_URL=sqlite:////data/chatbot.db`
- Railway·Render 어느 platform을 선택하더라도 SQLite persistent Volume 또는 Disk mount path는
  `/data`로 설정합니다.
- 최종 평가 배포에서는 service 재시작 후에도 SQLite data가 유지되어야 합니다.

## 7. 평가자 확인 방법

> 🔎 아래 명령은 구현 후 실제 DB file이 생성된 뒤 실행합니다. `scripts/check_logs.sql`은
> 운영 확인에 필요한 안전한 field만 출력합니다.

### sqlite3 CLI

```bash
sqlite3 data/chatbot.db < scripts/check_logs.sql
```

script는 사용자 역할, 최근 ChatExchange, 실패 ChatExchange의 `answer_is_null` 불변식,
사용자별 ChatExchange 수, 운영 metadata, Admin 9-field projection을 순서대로 조회합니다.
Admin projection은 `chat_exchanges LEFT JOIN users`를 기준으로 최신순이며 다음 field만
출력합니다.

```text
user_id
username
chat_exchange_id
created_at
request_id
user_agent
response_time_ms
status
error_code
```

`password_hash`, 질문·답변 원문, 내부 오류 내용, Cookie, Authorization, secret은 script
출력에 포함하지 않습니다.

확인 항목:

- `users.role`에 일반 사용자와 초기 `admin` 관리자의 역할이 구분되어 저장됨
- `chat_exchanges.user_id`가 로그인 사용자 `users.id`와 연결됨
- 성공 record에 UTC 시각·`request_id`·`response_time_ms`가 존재함
- 실패 record는 `answer IS NULL`, `status='failed'`이며 `error_code`로 실패 원인을 분류함
- `request_method`, `request_path`는 DB 운영 metadata에 저장하지 않음
- 사용자별 조회 결과가 서로 섞이지 않음
