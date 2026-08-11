# 실행·배포 계약

이 문서는 application environment variable, local 실행과 Railway 배포 구성을 정의합니다. 설정 변경으로
계약이 달라지는 경우 code, `.env.example`과 이 문서를 같은 변경에서 함께 갱신합니다. 아래 내용은
배포 target configuration이며 특정 environment의 배포 완료 상태를 의미하지 않습니다.

## 1. Environment variable

```text
SESSION_SECRET=
OPENAI_API_KEY=
OPENAI_MODEL=gpt-5-nano
OPENAI_TIMEOUT_SECONDS=30
DATABASE_URL=sqlite:///./data/chatbot.db
APP_ENV=local
LOG_LEVEL=INFO
ADMIN_USERNAME=admin
ADMIN_INITIAL_PASSWORD=
PORT=
```

| 이름 | 기본값·허용값 | 용도와 관리 원칙 |
| --- | --- | --- |
| `SESSION_SECRET` | 기본값 없음 | Signed session cookie에 사용하는 secret. Application 시작 전에 비어 있지 않은 값을 제공하고 repository에 실제 값을 기록하지 않음 |
| `OPENAI_API_KEY` | 기본값 없음 | Server의 OpenAI API 인증 secret. Browser에 노출하거나 repository에 실제 값을 기록하지 않음 |
| `OPENAI_MODEL` | 설정값: `gpt-5-nano` | Chat answer 생성에 사용할 OpenAI model. 현재 비용 우선 선택값 |
| `OPENAI_TIMEOUT_SECONDS` | `30` | OpenAI request timeout. 0보다 큰 숫자만 허용 |
| `DATABASE_URL` | `sqlite:///./data/chatbot.db` | Local SQLite 연결 URL |
| `APP_ENV` | `local`; `production` 허용 | 실행 environment를 구분. `production`에서는 production 보안·설정 validation을 적용 |
| `LOG_LEVEL` | `INFO` | Application log level |
| `ADMIN_USERNAME` | `admin` | 자동 생성하는 초기 관리자 username. 기본값은 `admin`이며 앞뒤 공백 제거 후 3~30자를 허용 |
| `ADMIN_INITIAL_PASSWORD` | 기본값 없음 | 관리자 역할 계정이 없을 때 초기 관리자 bootstrap에 사용하는 secret. 실제 값을 repository에 기록하지 않음 |
| `PORT` | 기본값 없음 | Railway Variables에서 직접 설정하는 HTTP server port |

`ADMIN_INITIAL_PASSWORD`는 관리자 역할 계정이 하나도 없을 때 Auth startup use case가 사용합니다.
기존 관리자 처리, 누락·유효성 실패와 logging 규칙은 [Architecture](ARCHITECTURE.md)에서 정의합니다.

## 2. Local 실행

1. Python dependency를 설치합니다.

   ```bash
   uv sync
   ```

2. `.env.example`을 `.env`로 복사합니다. Application 시작에는 `SESSION_SECRET`을, Chat 사용에는
   `OPENAI_API_KEY`와 `OPENAI_MODEL`을 설정합니다. 초기 admin이 없는 DB에서는
   `ADMIN_INITIAL_PASSWORD`도 설정합니다. `.env`는 commit하지 않습니다.

3. Application을 실행합니다.

   ```bash
   uv run uvicorn app.main:app --reload
   ```

기본 SQLite file은 repository의 `data/chatbot.db`에 생성됩니다. Schema와 SQLite connection 동작은
[DB schema 계약](db/DB.md)을 따릅니다.

## 3. Railway 배포

### Variables

- `APP_ENV=production`
- `DATABASE_URL=sqlite:////data/chatbot.db`
- `ADMIN_USERNAME=admin`
- `OPENAI_MODEL=gpt-5-nano`
- `PORT`는 Railway Variables에서 사용할 port number를 직접 설정합니다.
- `SESSION_SECRET`, `OPENAI_API_KEY`, `ADMIN_INITIAL_PASSWORD`는 Railway Variables에서 실제 값을
  제공합니다.
- `OPENAI_TIMEOUT_SECONDS`와 `LOG_LEVEL`은 공통 기본값을 사용하거나 Railway Variables에서 유효한
  값으로 override할 수 있습니다.

### Persistent Volume

- Railway Volume mount path는 `/data`입니다.
- SQLite file은 `/data/chatbot.db`를 사용합니다.
- Service restart와 새 deployment 후에도 기존 SQLite data가 유지되어야 합니다.

### Start와 healthcheck

Start Command:

```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Healthcheck path:

```text
/health
```

Healthcheck의 HTTP response contract는 [API 계약](api/API.md#8-health-api)을 따릅니다.

## 4. Deployment URL과 external smoke test

### 실제 배포 URL 기록

배포 URL: 미작성 (Railway 배포 완료 후 실제 URL 입력)

Production service URL은 Railway service에 연결한 public HTTPS domain입니다. 실제 URL은 deployment가
생성하는 environment-specific 값이므로 source code나 environment 공통 기본값으로 고정하지 않습니다.

### Process 접근성 smoke test

외부 network에서 발급된 URL을 사용해 다음 smoke test를 실행합니다.

```bash
DEPLOYMENT_URL=https://<railway-public-domain>
curl --fail --silent --show-error "$DEPLOYMENT_URL/health"
```

정상 응답은 API Health 계약과 일치해야 합니다. 이 확인은 process 접근성을 검증하며 OpenAI 호출이나
DB read/write 상태를 검사하지 않습니다.

### 배포 후 기능 smoke test

`/health` 확인과 별도로, 외부 Browser에서 실제 service 기능을 다음 순서로 확인합니다.

1. `/signup`과 `/login`에 접근해 일반 사용자 회원가입과 login 흐름을 확인합니다.
2. Login한 사용자로 `/chat`에 접근해 질문을 전송하고 AI 답변이 화면에 표시되는지 확인합니다.
3. 관리자 계정으로 login한 뒤 `/admin/logs`에 접근해 관리자 운영 metadata 화면이 표시되는지
   확인합니다.

이 검증은 인증, Chat request·response와 관리자 권한이 배포 environment에서 함께 동작하는지 확인합니다.
