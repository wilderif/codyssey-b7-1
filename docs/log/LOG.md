# Server log 기록 항목

Application logging output에는 다음 event를 기록합니다.

- `request_received`
- `ai_call_started`
- `ai_call_succeeded`
- `ai_call_failed`
- `db_save_succeeded`
- `db_save_failed`

각 event에는 상황에 따라 다음 field를 함께 기록합니다.

- `event`, `request_id`, `user_id`, `chat_exchange_id`
- HTTP method·path와 성공·실패 상태
- 처리 시간
- 안전한 오류 code 또는 예외 class
