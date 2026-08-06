# DB schema 계약

> 🗄️ 이 페이지가 SQLite table, 저장 실패 정책, 평가자 DB 확인 방법의 단일
> 기준입니다. 현재는 schema 계약이며 구현 결과가 아닙니다.

## 1. Model 원칙

- `users 1 : N chat_exchanges`
- `chat_exchanges` 한 record는 사용자 질문과 AI 답변 한 쌍입니다.
- 사용자별 하나의 연속 chat만 제공하므로 chat session/message table을 분리하지 않습니다.
- 관리자 권한은 environment variable로 load한 `settings.admin_usernames` allowlist로 판별하며
  `users.is_admin` field나 별도 role table을 추가하지 않습니다.
- 읽기 전용 관리자 화면은 server log를 조회하며 별도 운영 log table을 추가하지 않습니다.
- 초기 table 생성은 `Base.metadata.create_all()`을 사용하고 Alembic은 도입하지 않습니다.
- SQLAlchemy `Base`와 DB session은 `app/core/database.py`에서 제공하며 다른 module은 import해서 사용합니다.

## 2. Table schema

### `users`

| Field | Type | 조건 |
| --- | --- | --- |
| `id` | Integer | PK |
| `username` | String | Unique, Not Null |
| `password_hash` | String | Not Null |
| `created_at` | DateTime | Not Null, UTC |

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

## 3. 상태 불변식

| status | answer | error_message |
| --- | --- | --- |
| `success` | Not Null | Null |
| `failed` | Null | Not Null |

DB schema는 `CheckConstraint`로 status 값과 위 field 조합을 함께 강제합니다.

## 4. 조회 정책

### OpenAI 문맥 조회

DB에서는 login 사용자의 성공 record만 최신순으로 최대 5개 조회합니다.

```sql
SELECT id, question, answer, created_at
FROM chat_exchanges
WHERE user_id = :user_id
  AND status = 'success'
ORDER BY created_at DESC, id DESC
LIMIT 5;
```

application에서 결과를 오래된 순서로 뒤집어 OpenAI에 전달합니다.
동일한 `created_at`에서는 `id DESC`를 결정적인 tie-breaker로 사용합니다.

### 사용자 대화 기록 조회

사용자 화면과 대화 기록 API는 login 사용자의 record만 최신순으로 조회합니다.

```sql
SELECT id, question, answer, status, created_at
FROM chat_exchanges
WHERE user_id = :user_id
ORDER BY created_at DESC, id DESC;
```

내부 `error_message`는 사용자 화면과 API projection에서 제외합니다.

## 5. 저장 정책

### 성공

- `user_id`: login 사용자 ID
- `question`: 사용자 질문
- `answer`: AI 답변
- `status=success`
- `error_message=null`
- `created_at`: UTC

### AI 오류·시간 초과

- `user_id`: login 사용자 ID
- `question`: 사용자 질문
- `answer=null`
- `status=failed`
- `error_message`: 안전한 내부 실패 요약
- `created_at`: UTC

### DB 저장 자체 실패

해당 record는 저장할 수 없습니다. server log에 `db_save_failed` event만 남기고 API는 `500`과 다음 응답을 반환합니다.

```json
{"detail":"서버 오류가 발생했습니다. 잠시 후 다시 시도해주세요."}
```

내부 SQL 오류, 전체 stack, 비밀정보는 응답에 포함하지 않습니다. `error_message`는 화면과 API에 노출하지 않습니다.

## 6. SQLite 위치와 영속성

- local: `DATABASE_URL=sqlite:///./data/chatbot.db`
- 배포: `DATABASE_URL=sqlite:////data/chatbot.db`
- 배포 platform에는 `/data`를 mount path로 사용하는 SQLite 영구 Volume 또는 Disk가 있어야 합니다.
- 최종 평가 배포에서는 service 재시작 후에도 SQLite data가 유지되어야 합니다.

## 7. 평가자 확인 방법

> 🔎 아래 명령은 구현 후 실제 DB file이 생성된 뒤 실행합니다. `password_hash`는 확인
> 출력에 포함하지 않습니다.

### sqlite3 CLI

```bash
sqlite3 data/chatbot.db
.headers on
.mode column
SELECT id, username, created_at FROM users ORDER BY id;
SELECT id, user_id, question, answer, status, created_at
FROM chat_exchanges
ORDER BY created_at DESC, id DESC;
SELECT id, user_id, answer, status, error_message, created_at
FROM chat_exchanges
WHERE status = 'failed'
ORDER BY created_at DESC, id DESC;
SELECT user_id, COUNT(*) AS count
FROM chat_exchanges
GROUP BY user_id
ORDER BY user_id;
```

확인 항목:

- `chat_exchanges.user_id`가 login 사용자 `users.id`와 연결됨
- 성공 기록에 질문·답변·UTC 생성 시각이 존재함
- 실패 기록은 `answer IS NULL`, `status='failed'`
- 사용자별 조회 결과가 서로 섞이지 않음

### Python sqlite3 대체 명령

```bash
python - <<'PY'
import sqlite3

conn = sqlite3.connect("data/chatbot.db")
conn.row_factory = sqlite3.Row

for row in conn.execute(
    "SELECT id, user_id, question, answer, status, created_at "
    "FROM chat_exchanges ORDER BY created_at DESC, id DESC"
):
    print(dict(row))

conn.close()
PY
```
