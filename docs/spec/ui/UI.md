# Frontend UI 계약

이 문서는 화면 구조, form layout, Browser 상태, interaction, 접근성과 responsive 동작을 정의합니다.
HTTP status·request·response·오류 `code`는 [API 계약](../api/API.md), module 의존 방향은
[Architecture](../ARCHITECTURE.md)를 따릅니다. 이 문서는 구현 완료 상태를 의미하지 않습니다.

## 1. 범위와 기술 경계

- `app/ui`가 Jinja2로 HTML을 server rendering하고 Browser JavaScript가 `POST /api/chat`을
  호출합니다.
- Frontend는 별도 build 과정 없이 HTML, CSS, vanilla JavaScript로 구성합니다.
- `app/ui/router.py`는 `GET /`, 회원가입·Login·Logout form route와 `GET /chat`을 소유합니다.
  `/admin/logs`는 중복 등록하지 않습니다.
- 화면 router는 Auth public helper·Chat Service만 호출하고 Repository, ORM model과 OpenAI를 직접
  호출하지 않습니다.
  관리자 화면의 `/admin/logs` route와 관리자 데이터 조합은 `app/admin/router.py`가 소유하며,
  `app/ui`는 `admin_logs.html`과 공통 CSS·JavaScript 등 표현 자원만 제공합니다.
- 최소 UI file은 `router.py`, `templates/signup.html`, `templates/login.html`,
  `templates/chat.html`, 기존 `templates/admin_logs.html`, `static/styles.css`,
  `static/chat.js`입니다. 공통 base template 사용 여부는 구현 세부사항입니다.
- `app/main.py`는 UI router를 한 번 등록하고 `app/ui/static`을 `/static`에 mount합니다. Template은
  `/static/styles.css`를 사용하고 Chat 화면만 `/static/chat.js`를 추가로 사용합니다.
- 보호 HTML 화면은 Auth의 `require_authenticated_user()`가 반환하는 `user_id`와 `is_admin`만
  사용합니다. 이 public interface가 Auth module에 먼저 추가되어야 하며 UI가 Auth Repository 직접
  조회로 우회하지 않습니다.
- 초기 버전에는 React 등 UI framework, 상태관리 library, toast package, streaming, 자동 retry,
  별도 animation library를 도입하지 않습니다.
- 구체적인 색상, spacing, typography 값은 구현 세부사항입니다. 다만 모든 화면에서 같은 시각
  규칙을 사용하고 상태·focus를 명확히 구분해야 합니다.

## 2. 화면과 server 경로 연결

이 section은 각 화면이 server 경로를 어떻게 사용하는지 설명합니다. 정확한 HTTP method, status,
redirect, request와 response schema는 [API 계약](../api/API.md)을 따릅니다.

### `/`

- 별도 page를 rendering하지 않으며, server가 실제 User가 확인된 session이면 Chat 화면으로, 그 외에는
  Login 화면으로 `303` 이동시킵니다. 대응 User가 없는 stale session은 제거합니다.

### `/signup`

- `signup.html`에 username·password form과 Login 화면 link를 rendering합니다.
- 유효한 login session으로 접근하면 form을 rendering하지 않고 `/chat`으로 `303` 이동합니다.
- Form은 같은 경로로 제출합니다. 성공 시 Browser는 Login 화면으로 이동하고, 입력 오류 시 같은
  화면에 안전한 message를 표시합니다.
- Template context와 `RegistrationReason`별 message는
  [API 계약의 form contract](../api/API.md#form-request와-template-context)를 그대로 사용합니다.

### `/login`

- `login.html`에 username·password form과 회원가입 화면 link를 rendering합니다.
- 유효한 login session으로 접근하면 form을 rendering하지 않고 `/chat`으로 `303` 이동합니다.
- Form은 같은 경로로 제출합니다. 성공 시 Browser는 Chat 화면으로 이동하고, 인증 실패 시 같은
  화면에 안전한 message를 표시합니다.
- Template context는 [API 계약의 form contract](../api/API.md#form-request와-template-context)를
  그대로 사용합니다.

### `/chat`

- `chat.html`에 질문 form과 로그인 사용자의 이전 대화를 함께 rendering합니다.
- `chat_exchanges` template variable에는 `chat_exchange_id`, `question`, `answer`, `status`,
  `created_at` field가 포함됩니다.
- `is_admin: bool` template variable로 관리자 navigation rendering 여부를 결정합니다.
- Browser JavaScript는 `POST /api/chat`을 호출해 pending Chat 항목을 실제 답변 또는 오류로
  교체합니다. 사용하는 JSON field와 오류 contract는 [API 계약](../api/API.md)을 따릅니다.

### `/admin/logs`

- 별도 JSON API를 사용하지 않고 `admin_logs.html`에 허용된 read-only 운영 metadata를 table로
  rendering합니다.
- `app/admin/router.py`가 전달하는 template variable 이름은 `items`입니다. UI는 이 context 이름이나
  field를 임의로 바꾸지 않습니다.
- 표시 가능한 projection field는 [DB schema 계약](../db/DB.md#관리자-운영-metadata-조회)을
  따릅니다.
- `app/ui`는 `/admin/logs`의 접근 제어와 관리자 데이터 조합을 담당하지 않습니다.

### `/logout`

- Logout button은 `/logout` form을 제출하고 server 응답에 따라 Login 화면으로 이동합니다.
- JavaScript logout이나 `GET /logout`은 제공하지 않습니다.

Browser의 화면 표시만으로 접근을 허용하지 않으며, 인증과 관리자 권한은 server가 최종 판별합니다.

## 3. 공통 UI 기준

### Layout과 content

- 각 화면은 하나의 명확한 page heading과 주요 content를 포함합니다.
- 고정 UI 문구는 한국어로 작성합니다. JSON API의 사용자용 `detail`은 server가 반환한 언어를
  변환하지 않고 그대로 표시합니다.
- DB·API의 UTC 시각은 화면에서 `YYYY-MM-DD HH:mm:ss KST`로 변환해 표시하고, 원본 UTC 값은
  `time` element의 `datetime` attribute에 유지합니다.
- 인증 form과 보호 HTML response는 `Cache-Control: no-store`를 사용합니다. 모든 UI 화면은
  BFCache에서 복원되면 content를 숨긴 뒤 reload하여 server가 현재 session을 다시 확인하게 합니다.

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
- Browser form control은 [API 계약](../api/API.md#2-html폼-경로)의 username·password 검증 조건을
  반영합니다. 최종 검증은 server가 수행합니다.
- Form은 `method="post"`, `action="/signup"`이고 input 이름은 `username`, `password`입니다.
- Username에는 `required`, `minlength="3"`, `maxlength="30"`, `autocomplete="username"`을,
  password에는 `required`, `minlength="8"`, `maxlength="72"`, `autocomplete="new-password"`를
  적용합니다.

### 오류 표시

- 중복 username 또는 길이 오류는 같은 화면의 form과 연결된 오류 영역에 표시합니다.
- 오류가 발생하면 사용자가 입력한 username은 유지할 수 있지만 password는 HTML이나 template
  context로 다시 전달하거나 채우지 않습니다.
- 오류 영역은 message가 있을 때 `role="alert"`를 사용하고 관련 control과 `aria-describedby`로
  연결합니다.

## 5. Login 화면

### 기본 상태

- Username과 password 입력, Login button, 회원가입 화면으로 이동하는 link를 제공합니다.
- Form은 `method="post"`, `action="/login"`이고 input 이름은 `username`, `password`입니다.
- Username에는 `required`, `maxlength="30"`, `autocomplete="username"`을, password에는
  `required`, `maxlength="72"`, `autocomplete="current-password"`를 적용합니다. Login 실패의
  최종 판별과 message 통일은 server가 담당합니다.

### 오류 표시

- 인증 실패는 username 존재 여부를 구분하지 않고
  `아이디 또는 비밀번호가 올바르지 않습니다.`만 표시합니다.
- 인증 실패 후 username은 유지할 수 있지만 password는 다시 채우지 않습니다.
- 오류 영역은 message가 있을 때 `role="alert"`를 사용하고 username·password control과
  `aria-describedby`로 연결합니다.

## 6. Chat 화면

### Server rendering data

`GET /chat`은 다음 `chat_exchanges`를 최신순으로 전달합니다.

| Field | 화면 표시 |
| --- | --- |
| `chat_exchange_id` | record 식별에 사용하며 반드시 본문에 노출할 필요는 없음 |
| `question` | 사용자 질문 text |
| `answer` | 성공한 AI 답변 text |
| `status` | `success` 또는 `failed` 상태 표시 |
| `created_at` | 원본 UTC 시각을 KST로 변환해 표시 |

- 같은 context의 `is_admin`은 Auth가 검증한 boolean이며, UI가 role 문자열이나 DB record를 직접
  판별하지 않습니다.
- 화면은 전달받은 `chat_exchanges`를 역순으로 rendering해 과거 대화를 위쪽에, 최신 대화를
  최하단에 표시합니다.
- Chat header와 질문 form은 viewport 안에 유지하고, 대화 기록 영역만 독립적으로 세로 scroll합니다.
  대화 기록이 있으면 최초 rendering 후 최신 대화가 보이도록 scroll합니다.
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
- 질문 아래에는 `현재 글자 수 / 1000` 형식의 counter를 항상 표시하고 `aria-describedby`로 질문
  control과 연결합니다. Counter는 매 입력을 live announcement하지 않습니다.
- 질문 `textarea`는 2줄 기준으로 시작합니다. Desktop에서는 기존 `7rem` 최소 높이를 유지하고,
  `30rem` 이하 mobile viewport에서는 `4.75rem` 최소 높이로 줄여 대화 기록 영역을 확보합니다.
- `maxlength="1000"`은 일반적인 입력 과정에서 1000자 초과 작성을 제한합니다. JavaScript의
  길이 검증은 programmatic value 변경처럼 HTML constraint를 우회한 상황을 위한 방어입니다.
- 제출 시 JavaScript가 값을 `trim()`하고, 결과가 1~1000자가 아니면 API를 호출하지 않습니다.
- 공백 입력에는 `질문을 입력해주세요.`, 1000자 초과 입력에는
  `질문은 1000자 이하로 입력해주세요.`를 표시합니다.
- 유효한 질문은 공백을 제거한 전송값을 별도로 보관한 뒤 질문 control에서 즉시 제거합니다.
  Counter도 즉시 `0 / 1000`으로 되돌립니다. Client validation에 실패한 값과 count는 유지합니다.
- Primary pointer가 fine인 환경에서는 Enter가 form을 제출하고 Shift+Enter가 줄바꿈을 유지합니다.
  Primary pointer가 coarse인 환경에서는 Enter가 줄바꿈을 유지하고 전송 button으로 제출합니다.
- IME composition 중인 Enter는 제출하지 않습니다. Keyboard 제출 동작은 유지하지만 별도 입력 방식
  helper 문구는 표시하지 않습니다.

### Browser 상태 전이

| 상태 | 동작 |
| --- | --- |
| Idle | 진행 중인 request가 없고 질문 control과 전송 button을 사용할 수 있음 |
| Submitting | 전송 button을 비활성화하고 질문을 오른쪽에 즉시 추가하며 왼쪽 AI 답변 위치에 `답변 생성 중…`을 표시하고 추가 submit을 무시함 |

- 한 번에 하나의 `POST /api/chat` request만 진행할 수 있습니다.
- Request는 `fetch("/api/chat")`에 `method: "POST"`, `Content-Type: application/json`,
  `Accept: application/json`, `credentials: "same-origin"`을 사용하고 body는 정확히
  `{"message": trimmedQuestion}`입니다.
- Submitting 중에도 질문 control은 활성 상태로 유지해 다음 질문 draft를 작성할 수 있습니다.
- Submitting을 시작할 때 전송한 질문과 AI Loading 영역으로 구성한 pending Chat 항목을
  최하단에 추가하고 빈 대화 기록 안내를 제거한 뒤 최신 항목으로 scroll합니다.
- 성공하면 pending Chat 항목의 Loading을 응답 `answer`로 교체하고 `chat_exchange_id`와
  `created_at`을 해당 항목에 연결합니다. 같은 질문을 포함한 새 항목을 중복 생성하지 않으며
  별도 성공 status도 표시하지 않습니다.
- 성공 response의 `answer`는 text로 삽입합니다. `created_at` 원본 UTC 값은 `time[datetime]`에 유지하고
  화면 text만 `Asia/Seoul` 기준 KST로 변환합니다. Response field가 누락되거나 type이 계약과 다르면
  비정상 응답으로 처리합니다.
- 처리 오류는 pending Chat 항목의 Loading을 안전한 오류 message로 교체합니다. 실패 Chat
  항목에는 임의의 `chat_exchange_id`나 시각을 만들지 않습니다.
- Pending Chat 항목에 표시된 실패 결과 자체는 영구 저장의 증거가 아닙니다. 일부 server 오류는
  [DB schema 계약의 저장 정책](../db/DB.md#5-저장-정책)에 따라 실패 record로 저장될 수
  있으며, 새로고침 후에는 `GET /chat`이 rendering한 실제 server history만 표시합니다.
- 성공·실패와 관계없이 현재 작성 중인 다음 질문 draft를 비우거나 전송한 질문을 복원하지
  않습니다.
- 응답을 교체하기 직전 대화 기록이 bottom에서 `48px` 이내라면 교체 후 최신 항목을 계속
  표시합니다. 사용자가 그보다 위의 기록을 읽고 있으면 현재 scroll 위치를 강제로 바꾸지 않습니다.
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
- `app/admin/router.py`가 route와 `require_admin` 기반 접근 제어를 소유하고, `app/ui`는
  `admin_logs.html`과 공통 static 표현 자원만 제공합니다.
- Logout button은 `POST /logout` form으로 동작하며, `/chat`으로 돌아가는 link를 함께
  제공합니다.
- [DB schema 계약](../db/DB.md#관리자-운영-metadata-조회)에 정의된 안전한 projection field를
  각각 table column으로 표시합니다.
- Nullable 값은 빈 cell 대신 `-`처럼 값이 없음을 알 수 있는 text로 표시합니다.
- Record가 없으면 table 대신 `표시할 운영 기록이 없습니다.`를 표시합니다.
- `status`와 `error_code`는 색상만으로 구분하지 않고 text를 그대로 제공합니다.
- 질문·답변 원문, 내부 `error_message`, password와 `password_hash`는 표시하거나 DOM에 포함하지
  않습니다.
- 별도 관리자 JSON API, 수정·삭제 CRUD, 고급 검색·pagination, 별도 운영 log table은 제공하지
  않습니다.
- Table에는 내용을 설명하는 caption과 column별 header를 제공합니다.
- 좁은 화면에서는 table column을 숨겨 의미를 잃게 하지 않고 table container에 가로 scroll을
  제공합니다.
- Table 위에 `표를 좌우로 스크롤하면 모든 열을 확인할 수 있습니다.`를 표시하고 scroll region의
  accessible description으로 연결합니다. Scrollbar의 track과 thumb도 구분해 가로 scroll 가능성을
  드러냅니다.
- Table은 `72rem`의 적정 최소 너비를 유지하며 header와 짧은 identifier·status 값은 줄바꿈하지
  않습니다. `request_id`는 최소 `16rem`에서 자연스러운 구분점으로만 줄바꿈하고,
  `user_agent`는 `20rem` 너비 안에서 긴 technical token을 wrapping합니다.

현재 `admin_logs.html`은 Admin route와 safe projection을 검증하기 위한 최소 template입니다. UI 작업은
route·context ownership을 바꾸지 않고 navigation, 빈 상태, nullable `-` 표시, caption, responsive table과
공통 style을 이 section의 최종 계약에 맞게 보완합니다.

## 8. 구현 handoff

UI/FE 담당 범위는 다음과 같습니다.

1. `app/ui/router.py`에 `/`, Auth form route, `/logout`, `/chat`을 구현합니다.
2. `signup.html`, `login.html`, `chat.html`, `styles.css`, `chat.js`를 추가하고 기존
   `admin_logs.html`을 이 문서에 맞게 보완합니다.
3. `app/main.py`에 UI router와 `/static` mount를 연결합니다. `app/main.py` 소유자와 공용 file 변경을
   합의하고 Admin·Chat route를 중복 등록하지 않습니다.
4. HTML route test, template의 민감정보 미노출 test, Chat Browser 상태를 검증하는 JavaScript 또는
   수동 test를 추가합니다.

착수 전 integration prerequisite는 Auth module의 `require_authenticated_user()`와
`AuthenticatedUser(user_id, is_admin)`입니다. Chat history·JSON API와 Admin route는 기존 public
interface를 그대로 사용하며 UI 작업에서 schema나 route ownership을 변경하지 않습니다.

## 9. 수동 검증 checklist

### 인증 화면

- [ ] `/`가 인증 상태에 맞는 화면으로 이동함
- [ ] 회원가입 성공은 `/login`, 일반 사용자·관리자 Login 성공은 `/chat`으로 이동함
- [ ] 로그인 사용자의 `/login`·`/signup` 접근은 `/chat`으로 이동하고 stale session은 form을 표시함
- [ ] 회원가입·Login 오류가 같은 화면에 안전하게 표시되고 password가 다시 채워지지 않음
- [ ] 비로그인 사용자의 보호 화면 접근과 일반 사용자의 `/admin/logs` 접근이 계약대로 차단됨

### Chat 화면

- [ ] 본인의 이전 대화만 과거부터 최신 순서로 표시되고 빈 기록·실패 record 안내가 동작함
- [ ] 대화 기록이 길어도 header와 질문 form은 보이며 기록 영역만 scroll되고 최초 진입 시 최신 대화가 표시됨
- [ ] 빈 문자열·공백·1자·1000자·1000자 초과 입력을 검증함
- [ ] Mobile textarea가 2줄 높이로 시작하고 Counter가 입력과 전송 후 초기화 상태를 반영하며 Desktop Enter·Shift+Enter·IME와 Mobile Enter가 계약대로 동작함
- [ ] 전송 직후 pending Chat 항목과 `답변 생성 중…`이 표시되고 중복 전송이 차단됨
- [ ] 성공·실패 후 같은 pending 항목이 교체되고 작성 중인 다음 draft가 유지됨
- [ ] 실패 항목에 임의 ID·시각이 없으며 새로고침 후 실제 server history만 표시됨
- [ ] network·비정상 응답에서 기본 오류 문구와 상태 복구가 동작함
- [ ] `not_authenticated` 응답에서 Login 화면으로 이동함
- [ ] Chat 시각은 KST로 보이지만 `time[datetime]`은 UTC 원본을 유지함
- [ ] 질문·답변·오류의 줄바꿈과 긴 문자열이 표시되고 HTML·Markdown으로 실행되지 않음

### 관리자·공통 UI

- [ ] 관리자 table에 허용된 운영 metadata만 표시됨
- [ ] 360px에서 header와 짧은 identifier가 글자 중간에서 끊기지 않고 안내와 scrollbar를 통해 table container의 가로 scroll을 알 수 있음
- [ ] 질문·답변·내부 오류·민감정보가 관리자 DOM에 포함되지 않음
- [ ] `/chat`에서 관리자에게만 `관리자 운영 기록` button이 표시됨
- [ ] 보호 화면에서 Logout할 수 있고 관리자 화면에서 `/chat`으로 이동할 수 있음
- [ ] Login·Logout 후 뒤로가기로 BFCache 화면이 복원되면 server가 session을 다시 확인함
- [ ] 360px mobile 화면에서 form을 사용할 수 있고 table을 가로 scroll할 수 있음
- [ ] Keyboard만으로 주요 action을 실행하고 Loading·오류 상태를 보조 기술로 확인할 수 있음
