# Frontend UI 계약

> 🖥️ 이 페이지가 화면 구조, Browser 상태, interaction, 접근성, responsive 동작의 단일
> 기준입니다. HTTP status·request·response·오류 `code`는 [API 계약](../api/API.md),
> module 의존 방향은 [Architecture](../ARCHITECTURE.md)를 따릅니다. 현재는 계약만 확정되었고
> 구현 결과를 의미하지 않습니다.

## 1. 범위와 기술 경계

- `app/ui`가 Jinja2로 HTML을 server rendering하고 Browser JavaScript가 `POST /api/chat`을
  호출합니다.
- Frontend는 별도 build 과정 없이 HTML, CSS, vanilla JavaScript로 구성합니다.
- 화면 router는 Auth·Chat Service만 호출하고 Repository와 OpenAI를 직접 호출하지 않습니다.
- 초기 버전에는 React 등 UI framework, 상태관리 library, toast package, streaming, 자동 retry,
  별도 animation library를 도입하지 않습니다.
- 구체적인 색상, spacing, typography 값은 구현 세부사항입니다. 다만 모든 화면에서 같은 시각
  규칙을 사용하고 상태·focus를 명확히 구분해야 합니다.

## 2. 화면과 접근 조건

| 경로 | 화면·동작 | 접근 조건 |
| --- | --- | --- |
| `GET /` | 별도 화면 없이 인증 상태에 따라 이동 | 로그인 사용자는 `/chat`, 비로그인 사용자는 `/login` |
| `GET /signup` | 회원가입 화면 | 공개 |
| `GET /login` | Login 화면 | 공개 |
| `GET /chat` | 이전 대화와 질문 입력을 함께 제공하는 Chat 화면 | 로그인 필수 |
| `GET /admin/logs` | 사용자별 채팅 운영 metadata 조회 화면 | 관리자 필수 |
| `POST /logout` | Session을 삭제하고 Login 화면으로 이동 | 비로그인 요청도 동일하게 처리 |

정확한 HTTP status와 redirect는 [API 계약의 HTML·form 경로](../api/API.md#2-html폼-경로)를
따릅니다. Browser의 화면 표시만으로 접근을 허용하지 않으며, 인증과 관리자 권한은 server가
최종 판별합니다.

## 3. 공통 UI 기준

### Layout과 문구

- 각 화면은 하나의 명확한 page heading과 주요 content를 포함합니다.
- 모든 form control에는 화면에 보이는 label을 연결합니다. Placeholder만 label로 사용하지
  않습니다.
- 고정 UI 문구는 한국어로 작성합니다. JSON API의 사용자용 `detail`은 server가 반환한 언어를
  변환하지 않고 그대로 표시합니다.
- UTC 시각은 `UTC`임을 사용자가 알 수 있게 표시하고, 원본 값은 가능한 경우 `time` element의
  `datetime` attribute에 유지합니다.
- 질문, 답변, username, User-Agent, API `detail`은 신뢰할 수 없는 text로 취급합니다. Jinja2
  autoescape를 유지하고 JavaScript에서는 HTML로 삽입하지 않고 text로 rendering합니다.

### 상태 안내

- Loading과 처리 결과를 전달하는 공통 status 영역을 두고 `aria-live="polite"`를 적용합니다.
- 즉시 확인해야 하는 form·request 오류는 `role="alert"`로 알립니다.
- 오류와 성공 상태를 색상만으로 구분하지 않고 text 또는 icon의 accessible name을 함께
  제공합니다.
- Disabled button에는 실제 `disabled` attribute를 사용합니다.

## 4. 회원가입 화면

### 기본 상태

- Username과 password 입력, 회원가입 button, Login 화면으로 이동하는 link를 제공합니다.
- Username은 앞뒤 공백 제거 후 3~30자, password는 8~72자입니다. 최종 검증 규칙과 오류
  처리는 [API 계약](../api/API.md#2-html폼-경로)을 따릅니다.

### 오류와 성공

- 중복 username 또는 길이 오류는 같은 화면의 form과 연결된 오류 영역에 표시합니다.
- 오류가 발생하면 사용자가 입력한 username은 유지할 수 있지만 password는 HTML이나 template
  context로 다시 전달하거나 채우지 않습니다.
- 성공하면 자동 login하지 않고 `/login`으로 이동합니다.

## 5. Login 화면

### 기본 상태

- Username과 password 입력, Login button, 회원가입 화면으로 이동하는 link를 제공합니다.
- Form은 keyboard만으로 입력하고 제출할 수 있어야 합니다.

### 오류와 성공

- 인증 실패는 username 존재 여부를 구분하지 않고
  `아이디 또는 비밀번호가 올바르지 않습니다.`만 표시합니다.
- 인증 실패 후 username은 유지할 수 있지만 password는 다시 채우지 않습니다.
- 성공하면 `/chat`으로 이동합니다.

## 6. Chat 화면

### Server rendering data

`GET /chat`은 다음 `chat_exchanges`를 최신순으로 전달합니다.

| Field | 화면 표시 |
| --- | --- |
| `chat_exchange_id` | record 식별에 사용하며 반드시 본문에 노출할 필요는 없음 |
| `question` | 사용자 질문 text |
| `answer` | 성공한 AI 답변 text |
| `status` | `success` 또는 `failed` 상태 표시 |
| `created_at` | UTC 시각 |

- 기록이 없으면 입력 form을 그대로 제공하고 `아직 대화 기록이 없습니다.`를 표시합니다.
- `answer=null`이고 `status=failed`이면 답변 대신 `답변을 생성하지 못했습니다.`를 표시합니다.
- 내부 `error_message`와 운영 metadata는 template에 전달하거나 DOM에 포함하지 않습니다.
- 사용자용 별도 `/logs` 화면은 만들지 않습니다. 이 화면이 본인의 대화 기록 조회 역할을 함께
  수행합니다.

### 입력 form

- 질문 text control, 전송 button, request 상태 영역을 제공합니다.
- 질문 control에는 `required`와 `maxlength="1000"`을 적용합니다.
- 제출 시 JavaScript가 값을 `trim()`하고, 결과가 1~1000자가 아니면 API를 호출하지 않습니다.
- 공백 입력에는 `질문을 입력해주세요.`, 1000자 초과 입력에는
  `질문은 1000자 이하로 입력해주세요.`를 표시합니다.
- Multiline 입력의 Enter key는 줄바꿈으로 유지하며, form 제출은 전송 button으로 수행합니다.

### Browser 상태 전이

| 상태 | 동작 |
| --- | --- |
| Idle | 입력과 전송 button을 사용할 수 있고 이전 status 안내를 정리함 |
| Submitting | 전송 button을 비활성화하고 `답변 생성 중…`을 표시하며 추가 submit을 무시함 |
| Success | 전송한 질문과 응답을 최신 record로 최상단에 추가한 뒤 입력값을 비움 |
| Error | 기존 입력값을 유지하고 안전한 오류 message를 표시함 |
| Restored | 성공·실패 처리 후 button과 입력 상태를 복구하고 질문 control에 focus를 이동함 |

- 한 번에 하나의 `POST /api/chat` request만 진행할 수 있습니다.
- 성공 응답의 `chat_exchange_id`, `answer`, `created_at`과 전송한 질문을 사용해 새 record를
  rendering합니다.
- 오류 응답은 성공 record를 임의로 만들지 않습니다. Server에 저장된 실패 record는 이후
  `GET /chat` rendering에서 확인합니다.
- 성공·실패와 관계없이 상태 복구는 JavaScript의 공통 종료 경로에서 수행합니다.
- 자동 retry는 하지 않습니다. 실패한 질문은 입력값이 유지된 상태에서 사용자가 직접 다시
  전송합니다.

### JSON 오류 처리

Frontend는 `detail` 문자열을 비교하지 않고 안정적인 `code`로 동작을 결정합니다.

| `code`·상황 | Browser 동작 |
| --- | --- |
| `validation_error` | 안전한 `detail`을 form 오류로 표시 |
| `not_authenticated` | `/login`으로 이동 |
| `forbidden`, `conversation_not_found` | 안전한 `detail` 표시 |
| `db_save_error`, `internal_error`, `openai_api_error`, `openai_timeout` | 안전한 `detail`을 request 오류로 표시하고 입력 유지 |
| Network 오류, JSON이 아닌 응답, 문자열이 아닌 `detail`, 알 수 없는 `code` | `요청을 처리하지 못했습니다.` 표시 |

정확한 status·`code`·`detail`은 [API 계약의 오류 응답](../api/API.md#6-오류-응답)을
따릅니다. 내부 예외, SQL, stack, cookie, key, 내부 `error_message`는 화면에 표시하지 않습니다.

## 7. 관리자 운영 metadata 화면

- `/admin/logs`는 server runtime log file이 아니라 `chat_exchanges`에 저장된 사용자별 운영
  metadata를 읽기 전용 table로 표시합니다.
- 기본 column은 `user_id`, `chat_exchange_id`, `created_at`, `request_id`, `user_agent`,
  `response_time_ms`, `status`, `error_code`입니다.
- Nullable 값은 빈 cell 대신 `-`처럼 값이 없음을 알 수 있는 text로 표시합니다.
- Record가 없으면 table 대신 `표시할 운영 기록이 없습니다.`를 표시합니다.
- `status`와 `error_code`는 색상만으로 구분하지 않고 text를 그대로 제공합니다.
- 질문·답변 원문, 내부 `error_message`, password와 `password_hash`는 표시하거나 DOM에 포함하지
  않습니다.
- 수정·삭제 action, 고급 검색, pagination은 제공하지 않습니다.
- 좁은 화면에서는 table column을 숨겨 의미를 잃게 하지 않고 table container에 가로 scroll을
  제공합니다.

## 8. Responsive·접근성 기준

- 최소 360px 너비의 mobile viewport부터 desktop까지 주요 content와 form을 사용할 수 있어야
  합니다.
- 화면 너비가 줄어들어도 form control과 button이 viewport 밖으로 잘리지 않아야 합니다.
- Heading hierarchy, landmark, label, button, table header를 의미에 맞는 semantic HTML로
  작성합니다.
- Keyboard focus 순서는 화면의 읽기 순서와 일치해야 하며 focus indicator를 제거하지 않습니다.
- Loading 중에도 현재 상태를 screen reader가 확인할 수 있어야 합니다.
- 관리자 table에는 내용을 설명하는 caption과 column별 header를 제공합니다.

## 9. 수동 검증 checklist

### 인증 화면

- [ ] `/`가 인증 상태에 맞는 화면으로 이동함
- [ ] 회원가입·Login 성공 시 계약된 경로로 이동함
- [ ] 회원가입 오류와 Login 오류가 같은 화면에 안전하게 표시됨
- [ ] 오류 후 password가 HTML과 DOM에 다시 채워지지 않음
- [ ] 비로그인 사용자가 `/chat`과 `/admin/logs`에 접근할 수 없음
- [ ] 일반 사용자가 `/admin/logs`에 접근하면 `403`으로 차단됨

### Chat 화면

- [ ] 이전 대화가 본인 record만 최신순으로 표시됨
- [ ] 빈 history와 실패 record가 계약된 안내 문구로 표시됨
- [ ] 빈 문자열·공백·1자·1000자·1000자 초과 입력을 검증함
- [ ] Request 중 button이 비활성화되고 중복 전송이 차단됨
- [ ] 성공 후 새 record가 최상단에 표시되고 입력값이 비워짐
- [ ] 실패 후 안전한 `detail`이 표시되고 입력값이 유지됨
- [ ] Network·비정상 응답에서 기본 오류 문구와 상태 복구가 동작함
- [ ] `not_authenticated` 응답에서 Login 화면으로 이동함
- [ ] 질문·답변·오류 text가 HTML로 실행되지 않음

### 관리자·공통 UI

- [ ] 관리자 table에 허용된 운영 metadata만 표시됨
- [ ] 질문·답변·내부 오류·민감정보가 관리자 DOM에 포함되지 않음
- [ ] 360px mobile 화면에서 form을 사용할 수 있고 table을 가로 scroll할 수 있음
- [ ] Keyboard만으로 주요 action을 실행할 수 있음
- [ ] Loading·오류 상태를 `aria-live` 또는 `role="alert"`로 확인할 수 있음
