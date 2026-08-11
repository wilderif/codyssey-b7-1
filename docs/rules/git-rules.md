# Git 규칙

## Branch

- 장기 branch는 `main`만 사용합니다.
- 작업 branch는 `feature/*` 형식으로 만듭니다.
- `develop` branch는 만들지 않습니다.
- `main` 직접 push를 금지합니다.

## Commit

- `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:` 형식을 사용합니다.
- `test:`는 test code의 추가·수정·정리에 사용합니다.
- `refactor:`는 동작 변경 없는 production code 구조 개선에 사용합니다.
- 한 commit은 한 가지 목적만 가지며, 단순 줄바꿈이나 file 이동만으로 수를 채우지 않습니다.

```text
feat: description

- Detail 1
- Detail 2
- Detail 3
```
