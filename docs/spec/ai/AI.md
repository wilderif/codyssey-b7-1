# AI 호출 계약

이 문서는 Chat module이 OpenAI 요청을 구성하는 규칙을 정의합니다. 사용 model, system prompt,
conversation context 선택, OpenAI message role과 순서는 이 문서의 책임입니다. HTTP 결과는
[API 계약](../api/API.md), persistence schema와 저장 동작은 [DB schema 계약](../db/DB.md),
environment variable의 정확한 key와 실행 환경별 값은 [실행·배포 계약](../DEPLOYMENT.md)을
따릅니다.

## 1. 사용 model

Chat은 application 실행 설정에 구성된 OpenAI model을 사용합니다. Model은 user request나 Browser
입력으로 선택하거나 변경할 수 없습니다. 현재 실행 환경에서 사용하는 model 값과 설정 key는
[실행·배포 계약](../DEPLOYMENT.md)을 따릅니다. Chat module은 configured model을 모든 OpenAI
요청에 사용합니다.

## 2. System prompt

모든 OpenAI 요청의 첫 message는 다음 고정 system prompt입니다.

```text
You are a helpful assistant. Answer clearly and concisely in the user's language. Use plain text only and do not use Markdown formatting.
```

이 prompt는 user question과 이전 대화보다 앞에 한 번만 포함합니다.

## 3. Conversation context 선택

Chat Service는 현재 login 사용자 ID로 성공한 `ChatExchange`만 조회합니다. 조회 대상은 최신순으로
정렬된 최대 5건이며, OpenAI message를 만들 때는 이를 과거순으로 다시 정렬합니다.

- 다른 사용자의 대화는 context에 포함하지 않습니다.
- `failed` record는 context query에서 제외합니다. 성공 record에 answer가 없으면 message를 만들지 않고
  오류로 처리합니다.
- 이전 성공 대화가 없으면 system prompt와 현재 question만으로 요청을 구성합니다.

저장 record의 status와 query 정책은 [DB schema 계약](../db/DB.md)을 따릅니다.

## 4. Message role과 순서

각 이전 성공 대화는 질문을 `user`, 답변을 `assistant` role로 추가합니다. 현재 question은 항상
마지막 `user` message입니다.

```text
1. system: 고정 system prompt
2. user: 가장 오래된 이전 성공 question
3. assistant: 해당 question의 answer
4. ... 최대 5건의 이전 성공 대화 반복 ...
5. user: 현재 question
```

이 순서는 이전 대화가 최신순으로 API에 전달되는 것을 방지하고, 현재 question이 답변을 생성할
대상임을 보장합니다. 현재 question은 validation과 normalization을 거친 뒤 항상 마지막 `user`
message로 추가합니다. request payload와 validation의 HTTP 계약은 [API 계약](../api/API.md)을
따릅니다.

## 5. 실패·timeout 정책

OpenAI 요청은 최초 1회만 수행하며 자동 재시도하지 않습니다. SDK client의 재시도 횟수는 0회입니다.

timeout 기준에 도달하기 전의 응답 지연에는 speculative retry나 중복 요청을 수행하지 않고 기존
요청의 완료를 기다립니다.

| 상황 | 재시도 | 대체 AI 응답 | 처리 |
| --- | ---: | --- | --- |
| 응답 지연 | 0회 | 없음 | 완료 또는 timeout까지 기존 요청 대기 |
| Timeout | 0회 | 없음 | 실패 처리 |
| OpenAI API 오류 | 0회 | 없음 | 실패 처리 |
| 비정상·빈 응답 | 0회 | 없음 | 실패 처리 |

응답의 첫 choice content가 비어 있지 않은 text인 경우에만 answer로 사용합니다. 실패를 성공으로
위장하는 fallback answer는 생성하지 않습니다. 안전하게 저장 가능한 경우 실패 `ChatExchange`를
기록합니다. 사용자에게 반환하는 HTTP status, error code와 안전 오류 message는
[API 계약](../api/API.md)을 따릅니다.

timeout 값과 API key를 포함한 실행 설정은 [실행·배포 계약](../DEPLOYMENT.md)을 따릅니다.
