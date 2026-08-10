# AI chatbot service 명세

이 문서는 project의 제품·system 요구사항과 세부 기술 계약의 index를 제공합니다. 구체적인
HTTP, persistence, module interface, Frontend, 실행·배포 계약은 각 소유 문서에서 정의합니다.

## 1. 목표

팀 단위로 Linux, web, DB, AI API를 통합한 web 기반 AI chatbot을 개발하고 배포한다.

## 2. 최종 결과물

- 정상 동작하는 FastAPI web application 1개
- 운영 환경에서 외부 network로 접속 가능한 service URL
- GitHub repository link와 검증 가능한 문서 package

## 3. 기술 계약 안내

- Application은 Python과 FastAPI 기반의 modular monolith로 구성합니다.
- 대화 기록은 운영자가 확인할 수 있는 persistence storage에 저장합니다.

| 기술 영역 | 상세 계약 |
| --- | --- |
| Architecture와 module interface | [Architecture](ARCHITECTURE.md) |
| HTTP와 API | [API 계약](api/API.md) |
| DB와 persistence | [DB schema 계약](db/DB.md) |
| AI 호출과 message 구성 | [AI 호출 계약](ai/AI.md) |
| Frontend 동작 | [Frontend UI 계약](ui/UI.md) |
| Environment, 실행과 배포 | [실행·배포 계약](DEPLOYMENT.md) |

## 4. 기능 요구사항

### 4.1 Web UI

- 사용자가 text 질문을 입력할 수 있어야 한다.
- 질문 제출 후 같은 화면에서 AI 응답을 확인할 수 있어야 한다.
- 화면 구조, Browser 상태, interaction, 접근성, responsive 동작은
  [Frontend UI 계약](ui/UI.md)을 따른다.

### 4.2 인증과 access control

- 회원가입과 login이 정상 동작해야 한다.
- 인증 상태에 따라 접근 가능한 기능을 구분해야 한다.
- chatbot 질문·응답 기능은 login한 사용자만 사용할 수 있어야 한다.

### 4.3 AI chatbot

- server가 질문을 수신하고 AI API를 호출해 응답을 생성해야 한다.
- AI API 호출과 인증 정보 처리는 server에서 수행하고, client에는 결과만 반환해야 한다.
- 사용자 또는 session의 이전 대화를 활용하는 문맥 유지 전략을 적용해야 한다.

### 4.4 대화 log

- 사용자 질문과 AI 응답을 DB에 누적 저장해야 한다.
- 사용자 식별자, 생성 시각, 질문, 응답을 필수로 저장해야 한다.
- 사용자 기준으로 대화 log를 조회하고 추적할 수 있어야 한다.

### 4.5 입력과 오류 처리

- 사용자 입력 검증을 1개 이상 적용해야 한다.
- AI API 호출에 timeout을 설정해야 한다.
- AI API 실패나 timeout이 발생해도 service가 비정상 종료되지 않아야 한다.
- 오류 발생 사실을 message, status code 또는 안내로 사용자에게 전달해야 한다.

## 5. 운영 요구사항

Server log에 다음 event와 성공·실패 여부를 기록해야 한다.

- 요청 수신
- AI API 호출
- AI API 응답 수신 또는 실패
- DB 저장

## 6. 보안과 설정 관리

- API key와 DB password 등 민감정보를 code와 문서에 직접 작성하지 않는다.
- 민감정보는 environment variable로 관리한다.
- `.env`는 `.gitignore`로 repository에서 제외한다.
- `.env` example file을 제공한다.
- README에 environment variable 이름과 설정 방법을 작성한다.

## 7. 배포 요구사항

- 배포된 service를 외부 network에서 사용할 수 있어야 한다.
- 실행, 배포, environment variable 설정은 [실행·배포 계약](DEPLOYMENT.md)을 따릅니다.

## 8. 협업과 형상관리

- repository의 Git 및 GitHub 규칙에 따라 branch를 운영한다.
- 기능 단위 작업 branch 기록을 남긴다.
- PR 기반 병합 기록을 남긴다.
- 팀 역할과 개인별 작업 요약은 Git 이력과 일치해야 한다.

## 9. 문서 산출물

README 또는 기술 문서에 다음 내용을 포함해야 한다.

- 문제 정의, 대상 사용자, 핵심 scenario를 포함한 project 개요
- system 구조와 주요 component 역할
- 요청·응답 예시를 포함한 API spec
- ERD 또는 table·field 설명을 포함한 DB 구조
- 실행·배포 방법과 environment variable 설정 방법
- 팀 구성원 역할과 개인별 작업 요약
- `.env` example과 `.gitignore` 적용 방법을 포함한 민감정보 관리 방법

대화 log를 검증할 수 있도록 다음 중 하나 이상을 제공해야 한다.

- 요청 예시를 포함한 log 조회 API
- 관리자 또는 내부 log 확인 화면
- 확인용 SQL, script 또는 증빙 자료 link

## 10. 완료 기준

팀원은 다음 내용을 설명할 수 있어야 한다.

- FastAPI의 routing, 요청·응답, web UI 연동 흐름
- 인증과 접근 제어의 적용 이유와 방식
- 질문 수신, AI API 호출, 응답 반환, log 저장의 처리 흐름
- 대화 log의 누적 저장과 사용자 기준 조회 설계
- AI API 오류 처리와 server log를 통한 원인 추적 방법
- branch, PR, 문서화를 통한 협업 품질 관리 방법
