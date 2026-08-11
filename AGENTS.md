# AGENTS.md

## 목적

이 file은 AI agent가 repository 작업을 시작할 때 확인하는 기준 문서입니다. 세부 규칙,
작업 절차, project 정보는 `docs/`에서 관리합니다.

## 시작 전 확인

1. issue 또는 사용자의 명시적인 요청을 확인합니다.
2. 사용자가 범위를 확장하지 않는 한 요청 범위 안에서만 작업합니다.

Git 또는 GitHub 작업 전에는 작업에 따라
[Git 규칙](docs/rules/git-rules.md) 또는
[GitHub 규칙](docs/rules/github-rules.md)을 확인합니다.

## PR 생성 전 확인

1. [PR template](.github/pull_request_template.md)의 내용을 확인합니다.
2. 다음 command를 모두 실행합니다.

   ```bash
   uv run ruff check .
   uv run ruff format --check .
   uv run pyright
   ```

3. 검사에서 발견된 문제를 수정하고 모든 command가 통과한 후 PR을 생성합니다.

## 문서 안내

| 구분 | 기준 문서 |
| --- | --- |
| Service 요구사항 | [`docs/spec/SPEC.md`](docs/spec/SPEC.md) |
| Architecture·module 경계 | [`docs/spec/ARCHITECTURE.md`](docs/spec/ARCHITECTURE.md) |
| API 계약 | [`docs/spec/api/API.md`](docs/spec/api/API.md) |
| DB schema 계약 | [`docs/spec/db/DB.md`](docs/spec/db/DB.md) |
| AI 호출 계약 | [`docs/spec/ai/AI.md`](docs/spec/ai/AI.md) |
| Frontend UI 계약 | [`docs/spec/ui/UI.md`](docs/spec/ui/UI.md) |
| 실행·배포 계약 | [`docs/spec/DEPLOYMENT.md`](docs/spec/DEPLOYMENT.md) |
| Git·GitHub 규칙 | [`docs/rules/git-rules.md`](docs/rules/git-rules.md), [`docs/rules/github-rules.md`](docs/rules/github-rules.md) |

## 저장소 규칙

- 각 변경은 작고 명확하며 독립적으로 검토할 수 있어야 합니다.
- 요청과 무관한 설정, 도구, refactoring, 실행 동작을 추가하지 않습니다.
- commit message와 file name은 영어로, 그 외 내용은 한글로 작성합니다.
- 기술 용어와 제품·protocol 이름은 문서에서도 English 표기를 사용합니다.
- 비밀정보, credential, 개인 메모, 특정 기기에 종속된 정보를 commit하지 않습니다.
- 지속적으로 필요한 지침은 local 메모가 아닌 해당 기준 문서에 추가합니다.
