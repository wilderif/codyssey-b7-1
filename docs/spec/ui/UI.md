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

## 2. 화면별 API 경로와 응답 형식

### `/`

#### 화면 진입 (`GET`)

##### 사용할 API 경로

- 추후 추가 예정입니다.

##### 응답 JSON

- JSON 응답은 사용하지 않습니다.
- 로그인 사용자는 `303 /chat`, 비로그인 사용자는 `303 /login`으로 이동합니다.

### `/signup`

#### 화면 조회 (`GET`)

##### 사용할 API 경로

- 추후 추가 예정입니다.

##### 응답 JSON

- JSON 응답은 사용하지 않고 `200 signup.html`을 rendering합니다.

#### 회원가입 제출 (`POST`)

##### 사용할 API 경로

- 추후 추가 예정입니다.

##### 응답 JSON

- JSON 응답은 사용하지 않습니다.
- 성공하면 자동 login 없이 `303 /login`으로 이동합니다.
- 중복 username이나 길이 오류가 발생하면 사용자용 message와 함께 같은 화면을 `400`으로
  rendering합니다.

### `/login`

#### 화면 조회 (`GET`)

##### 사용할 API 경로

- 추후 추가 예정입니다.

##### 응답 JSON

- JSON 응답은 사용하지 않고 `200 login.html`을 rendering합니다.

#### Login 제출 (`POST`)

##### 사용할 API 경로

- 추후 추가 예정입니다.

##### 응답 JSON

- JSON 응답은 사용하지 않습니다.
- 성공하면 session을 생성하고 `303 /chat`으로 이동합니다.
- 인증에 실패하면 `아이디 또는 비밀번호가 올바르지 않습니다.` message와 함께 같은 화면을
  `400`으로 rendering합니다.

### `/chat`

#### 화면 조회 (`GET`)

##### 사용할 API 경로

- 추후 추가 예정입니다.

##### 응답 JSON

- JSON 응답은 사용하지 않고 `200 chat.html`을 rendering합니다.
- `chat_exchanges` template variable에는 `chat_exchange_id`, `question`, `answer`, `status`,
  `created_at` field가 포함됩니다.
- 비로그인 사용자는 `303 /login`으로 이동합니다.

#### 질문 전송 (`POST`)

##### 사용할 API 경로

- `POST /api/chat`

##### 성공 응답 JSON

```json
{
  "chat_exchange_id": 15,
  "answer": "FastAPI는 Python 기반의 웹 프레임워크입니다.",
  "created_at": "2026-08-04T06:00:00Z"
}
```

##### 오류 응답 JSON

```json
{
  "code": "...",
  "detail": "..."
}
```

- 정확한 HTTP status와 `code`·`detail`은
  [API 계약의 오류 응답](../api/API.md#6-오류-응답)을 따릅니다.

### `/admin/logs`

#### 화면 조회 (`GET`)

##### 사용할 API 경로

- 추후 추가 예정입니다.

##### 응답 JSON

- JSON 응답은 사용하지 않고 관리자에게 `200 admin_logs.html`을 rendering합니다.
- 비로그인 사용자는 `303 /login`으로 이동하고 비관리자는 `403`을 반환합니다.
- 관리자 화면에는 `user_id`, `username`, `chat_exchange_id`, `created_at`, `request_id`,
  `user_agent`, `response_time_ms`, `status`, `error_code` field를 제공합니다.

### `/logout`

#### Logout 제출 (`POST`)

##### 사용할 API 경로

- 추후 추가 예정입니다.

##### 응답 JSON

- JSON 응답은 사용하지 않습니다.
- 로그인 여부와 관계없이 session을 삭제하고 `303 /login`으로 이동합니다.

정확한 HTTP status와 redirect는 [API 계약의 HTML·form 경로](../api/API.md#2-html폼-경로)를
따릅니다. Browser의 화면 표시만으로 접근을 허용하지 않으며, 인증과 관리자 권한은 server가
최종 판별합니다.

## 3. 공통 UI 기준

### Layout과 content

- 각 화면은 하나의 명확한 page heading과 주요 content를 포함합니다.
- 고정 UI 문구는 한국어로 작성합니다. JSON API의 사용자용 `detail`은 server가 반환한 언어를
  변환하지 않고 그대로 표시합니다.
- UTC 시각은 `UTC`임을 사용자가 알 수 있게 표시하고, 원본 값은 가능한 경우 `time` element의
  `datetime` attribute에 유지합니다.

### 안전한 text rendering

- 질문, 답변, username, User-Agent, API `detail`은 신뢰할 수 없는 text로 취급합니다. Jinja2
  autoescape를 유지하고 JavaScript에서는 HTML로 삽입하지 않고 text로 rendering합니다.
- 질문, 답변, API `detail`은 Markdown이나 HTML로 parsing하지 않는 plain text입니다. 원문의
  줄바꿈은 보존하고 공백 없는 긴 문자열도 viewport를 넘지 않도록 wrapping합니다.

### Responsive·접근성

- 최소 360px 너비의 mobile viewport부터 desktop까지 주요 content와 form을 사용할 수 있어야
  합니다.
- 화면 너비가 줄어들어도 form control과 button이 viewport 밖으로 잘리지 않아야 합니다.
- Heading hierarchy, landmark, label, button, table header를 의미에 맞는 semantic HTML로
  작성합니다.
- 모든 form control에는 화면에 보이는 label을 연결합니다. Placeholder만 label로 사용하지
  않습니다.
- Keyboard focus 순서는 화면의 읽기 순서와 일치해야 하며 focus indicator를 제거하지 않습니다.
- 상태를 색상만으로 구분하지 않고 text 또는 icon의 accessible name을 함께 제공합니다.
- 비활성화한 button에는 실제 `disabled` attribute를 사용합니다.

## 4. 회원가입 화면

### 기본 상태

- Username과 password 입력, 회원가입 button, Login 화면으로 이동하는 link를 제공합니다.
- Username은 앞뒤 공백 제거 후 3~30자, password는 8~72자입니다. 최종 검증 규칙과 오류
  처리는 [API 계약](../api/API.md#2-html폼-경로)을 따릅니다.

### 오류 표시

- 중복 username 또는 길이 오류는 같은 화면의 form과 연결된 오류 영역에 표시합니다.
- 오류가 발생하면 사용자가 입력한 username은 유지할 수 있지만 password는 HTML이나 template
  context로 다시 전달하거나 채우지 않습니다.

## 5. Login 화면

### 기본 상태

- Username과 password 입력, Login button, 회원가입 화면으로 이동하는 link를 제공합니다.

### 오류 표시

- 인증 실패는 username 존재 여부를 구분하지 않고
  `아이디 또는 비밀번호가 올바르지 않습니다.`만 표시합니다.
- 인증 실패 후 username은 유지할 수 있지만 password는 다시 채우지 않습니다.

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

- 화면은 전달받은 `chat_exchanges`를 역순으로 rendering해 과거 대화를 위쪽에, 최신 대화를
  최하단에 표시합니다.
- 각 Chat 항목은 사용자 질문을 오른쪽에, server가 반환한 AI 답변 또는 실패 안내를 왼쪽에
  배치해 발화 주체를 구분합니다.
- 기록이 없으면 입력 form을 그대로 제공하고 `아직 대화 기록이 없습니다.`를 표시합니다.
- `answer=null`이고 `status=failed`이면 답변 대신 `답변을 생성하지 못했습니다.`를 표시합니다.
- 내부 `error_message`와 운영 metadata는 template에 전달하거나 DOM에 포함하지 않습니다.
- 사용자용 별도 `/logs` 화면은 만들지 않습니다. 이 화면이 본인의 대화 기록 조회 역할을 함께
  수행합니다.

### Navigation

- Logout button은 `POST /logout` form으로 동작합니다.
- Server가 현재 사용자를 관리자로 판별한 경우에만 `/admin/logs`로 이동하는
  `관리자 운영 기록` link를 button 형태로 제공합니다. 일반 사용자에게는 이 link를
  rendering하거나 DOM에 포함하지 않습니다.

### 입력 form

- 질문 `textarea`, 전송 button, form 오류 영역을 제공합니다.
- 질문 control에는 `required`와 `maxlength="1000"`을 적용합니다.
- `maxlength="1000"`은 일반적인 입력 과정에서 1000자 초과 작성을 제한합니다. JavaScript의
  길이 검증은 programmatic value 변경처럼 HTML constraint를 우회한 상황을 위한 방어입니다.
- 제출 시 JavaScript가 값을 `trim()`하고, 결과가 1~1000자가 아니면 API를 호출하지 않습니다.
- 공백 입력에는 `질문을 입력해주세요.`, 1000자 초과 입력에는
  `질문은 1000자 이하로 입력해주세요.`를 표시합니다.
- 유효한 질문은 공백을 제거한 전송값을 별도로 보관한 뒤 질문 control에서 즉시 제거합니다.
  client validation에 실패한 값은 제거하지 않습니다.
- Multiline 입력의 Enter key는 줄바꿈으로 유지하며, form 제출은 전송 button으로 수행합니다.

### Browser 상태 전이

| 상태 | 동작 |
| --- | --- |
| Idle | 진행 중인 request가 없고 질문 control과 전송 button을 사용할 수 있음 |
| Submitting | 전송 button을 비활성화하고 질문을 오른쪽에 즉시 추가하며 왼쪽 AI 답변 위치에 `답변 생성 중…`을 표시하고 추가 submit을 무시함 |

- 한 번에 하나의 `POST /api/chat` request만 진행할 수 있습니다.
- Submitting 중에도 질문 control은 활성 상태로 유지해 다음 질문 draft를 작성할 수 있습니다.
- Submitting을 시작할 때 전송한 질문과 AI Loading 영역으로 구성한 pending Chat 항목을
  최하단에 추가하고 빈 대화 기록 안내를 제거합니다.
- 성공하면 pending Chat 항목의 Loading을 응답 `answer`로 교체하고 `chat_exchange_id`와
  `created_at`을 해당 항목에 연결합니다. 같은 질문을 포함한 새 항목을 중복 생성하지 않으며
  별도 성공 status도 표시하지 않습니다.
- 처리 오류는 pending Chat 항목의 Loading을 안전한 오류 message로 교체합니다. 실패 Chat
  항목에는 임의의 `chat_exchange_id`나 시각을 만들지 않습니다.
- Pending Chat 항목에 표시된 실패 결과 자체는 영구 저장의 증거가 아닙니다. 일부 server 오류는
  [API 계약의 저장 정책](../api/API.md#7-문맥openai저장-정책)에 따라 실패 record로 저장될 수
  있으며, 새로고침 후에는 `GET /chat`이 rendering한 실제 server history만 표시합니다.
- 성공·실패와 관계없이 현재 작성 중인 다음 질문 draft를 비우거나 전송한 질문을 복원하지
  않습니다.
- Redirect를 제외한 공통 종료 경로는 Loading 상태를 정리하고 전송 button을 다시 활성화한 뒤
  질문 control에 focus를 이동합니다.
- AI 답변 위치의 Loading 영역에는 `aria-live="polite"`, 즉시 확인해야 하는 form 오류와 실패
  Chat 항목에는 `role="alert"`를 적용합니다.
- 성공은 별도 status 문구 없이 pending Chat 항목의 Loading을 실제 답변으로 교체해 표시합니다.
- 자동 retry는 하지 않습니다.

### Chat API 오류 처리

Frontend는 `detail` 문자열을 비교하지 않고 안정적인 `code`로 동작을 결정합니다.
Request 전 client validation 오류는 pending Chat 항목을 만들지 않고 form 오류로 표시합니다.
Request를 시작한 뒤 받은 `POST /api/chat` 오류는 다음 기준으로 pending 항목을 처리합니다.

| `code`·상황 | Browser 동작 |
| --- | --- |
| `validation_error` | pending Chat 항목의 AI 답변을 안전한 `detail`로 교체 |
| `not_authenticated` | `/login`으로 이동 |
| `db_save_error`, `internal_error`, `openai_api_error`, `openai_timeout` | pending Chat 항목의 AI 답변을 안전한 `detail`로 교체 |
| network 오류, JSON이 아닌 응답, 문자열이 아닌 `detail`, 알 수 없는 `code` | pending Chat 항목의 AI 답변을 `요청을 처리하지 못했습니다.`로 교체 |

정확한 status·`code`·`detail`은 [API 계약의 오류 응답](../api/API.md#6-오류-응답)을
따릅니다. 내부 예외, SQL, stack, cookie, key, 내부 `error_message`는 화면에 표시하지 않습니다.

## 7. 관리자 운영 metadata 화면

- `/admin/logs`는 server runtime log file이 아니라 `chat_exchanges`에 저장된 사용자별 운영
  metadata를 읽기 전용 table로 표시합니다.
- Logout button은 `POST /logout` form으로 동작하며, `/chat`으로 돌아가는 link를 함께
  제공합니다.
- 기본 column은 `user_id`, `username`, `chat_exchange_id`, `created_at`, `request_id`, `user_agent`,
  `response_time_ms`, `status`, `error_code`입니다.
- Nullable 값은 빈 cell 대신 `-`처럼 값이 없음을 알 수 있는 text로 표시합니다.
- Record가 없으면 table 대신 `표시할 운영 기록이 없습니다.`를 표시합니다.
- `status`와 `error_code`는 색상만으로 구분하지 않고 text를 그대로 제공합니다.
- 질문·답변 원문, 내부 `error_message`, password와 `password_hash`는 표시하거나 DOM에 포함하지
  않습니다.
- 수정·삭제 action, 고급 검색, pagination은 제공하지 않습니다.
- Table에는 내용을 설명하는 caption과 column별 header를 제공합니다.
- 좁은 화면에서는 table column을 숨겨 의미를 잃게 하지 않고 table container에 가로 scroll을
  제공합니다.

## 8. 수동 검증 checklist

### 인증 화면

- [ ] `/`가 인증 상태에 맞는 화면으로 이동함
- [ ] 회원가입 성공은 `/login`, 일반 사용자·관리자 Login 성공은 `/chat`으로 이동함
- [ ] 회원가입·Login 오류가 같은 화면에 안전하게 표시되고 password가 다시 채워지지 않음
- [ ] 비로그인 사용자의 보호 화면 접근과 일반 사용자의 `/admin/logs` 접근이 계약대로 차단됨

### Chat 화면

- [ ] 본인의 이전 대화만 과거부터 최신 순서로 표시되고 빈 기록·실패 record 안내가 동작함
- [ ] 빈 문자열·공백·1자·1000자·1000자 초과 입력을 검증함
- [ ] 전송 직후 pending Chat 항목과 `답변 생성 중…`이 표시되고 중복 전송이 차단됨
- [ ] 성공·실패 후 같은 pending 항목이 교체되고 작성 중인 다음 draft가 유지됨
- [ ] 실패 항목에 임의 ID·시각이 없으며 새로고침 후 실제 server history만 표시됨
- [ ] network·비정상 응답에서 기본 오류 문구와 상태 복구가 동작함
- [ ] `not_authenticated` 응답에서 Login 화면으로 이동함
- [ ] 질문·답변·오류의 줄바꿈과 긴 문자열이 표시되고 HTML·Markdown으로 실행되지 않음

### 관리자·공통 UI

- [ ] 관리자 table에 허용된 운영 metadata만 표시됨
- [ ] 질문·답변·내부 오류·민감정보가 관리자 DOM에 포함되지 않음
- [ ] `/chat`에서 관리자에게만 `관리자 운영 기록` button이 표시됨
- [ ] 보호 화면에서 Logout할 수 있고 관리자 화면에서 `/chat`으로 이동할 수 있음
- [ ] 360px mobile 화면에서 form을 사용할 수 있고 table을 가로 scroll할 수 있음
- [ ] Keyboard만으로 주요 action을 실행하고 Loading·오류 상태를 보조 기술로 확인할 수 있음
