# CLAUDE.md — prompthon-2026

## 검증은 얕게, 깊은 검증은 요청할 때

이 저장소에서는 만드는 속도가 우선이다. 무거운 검증을 매번 돌리면 코드를 쓴
시간보다 확인한 시간이 길어진다 — `npm run build`는 여기서 7분 12초 걸린다.

전역 `~/.claude/RULES.md`의 Workflow Rules 중 "Validation Gates"와
"Quality Checks: Run lint/typecheck before marking tasks complete"는
이 저장소에서 아래 규칙으로 대체된다. 나머지 전역 규칙은 그대로 적용된다.

### 작업 직후 — 기본은 타입 체크뿐

바꾼 것이 타입 수준에서 성립하는지만 본다. 그 외에는 돌리지 않는다.

| 무엇을 고쳤나 | 무엇을 돌리나 |
| --- | --- |
| `frontend/**/*.ts(x)` | `cd frontend && npx tsc --noEmit` — 수 초 |
| `backend/**/*.py` | 바꾼 모듈 import 확인, 또는 직접 관련된 테스트 **한 개**<br>(`python tests/test_family_visibility.py` 처럼 파일 단위) |
| 문서·주석·설정 | 아무것도 돌리지 않는다 |

### 요청할 때만 돌리는 것

"빌드해봐 / 테스트 돌려 / 검증해줘 / 실행해봐"처럼 사용자가 말할 때만.

- `npm run build` — 프로덕션 빌드. 약 7분
- `tests/` 전체 회귀 (README "검증" 절의 목록 전부)
- `DATABASE_URL`·`TEST_DATABASE_URL`을 붙인 Postgres 경로 회귀
- 앱 띄우기, 스크린샷, 배포 확인, Trust Harness

커밋 요청도 같다. **커밋 전에 검증을 끼워 넣지 않는다** — `git diff`로 스테이징할
것만 확인하고 바로 커밋한다.

### 대신 안 돌린 것을 밝힌다

작업 보고 끝에 한 줄로 적는다: "타입 체크만 했고 빌드·테스트는 안 돌렸다."
돌리지 않은 것을 통과했다고 쓰지 않는다. 얕게 보는 것과 확인했다고 말하는
것은 다르다.

### 예외 — 요청 없이도 돌린다

- **되돌리기 어려운 것**: 데이터 마이그레이션, 파일·레코드 삭제, 배포, 스키마 변경
- **이미 실패하는 것을 고칠 때**: 고치기 전에 그 실패를 재현하고, 고친 뒤 같은
  것을 다시 돌린다. 재현 없이 고치면 무엇을 고쳤는지 알 수 없다
- **사용자가 동작 확인 자체를 목표로 잡았을 때**: "이거 되는지 봐줘"

## 브랜치는 development 하나

이 저장소에서는 피처 브랜치를 만들지 않는다. 모든 작업을 `development`에서
직접 커밋한다.

전역 `~/.claude/RULES.md`의 Git Workflow 중 **"Feature Branches Only: Create
feature branches for ALL work, never work on main/master"** 는 이 저장소에서
아래 규칙으로 대체된다. 같은 절의 나머지(작업 시작 시 `git status` 확인, 잦은
커밋, 커밋 전 `git diff` 검토, 위험한 작업 전 복원 지점)는 그대로 적용된다.

### 왜

여러 세션이 같은 작업트리에서 동시에 일한다. 브랜치를 나누면 그 하나가
체크아웃할 때 다른 세션이 열어 둔 파일과 부딪히고, 실제로 머지가 반쯤 적용된
채로 페이지 네 개가 디스크에서 사라진 적이 있다 (Vite dev 서버가 파일 핸들을
잡고 있었다). 배포도 `development`만 본다 — Railway가 그 브랜치를 따라간다.
브랜치를 만들면 옮기고 지우는 일이 매번 따라붙는다.

### 그래서 이렇게 한다

- 작업 전 `git branch --show-current`로 `development`인지 본다. 아니면 옮긴다
- 커밋은 `development`에 바로 한다. `git checkout -b`를 하지 않는다
- 배포는 `git push origin development` — Railway가 자동으로 다시 뜬다
- 프론트는 별도로 `cd frontend && npx vercel --prod`

### 커밋할 때 조심할 것

같은 트리에서 다른 세션이 동시에 일한다. `git add -A`나 `git add <디렉터리>`는
남의 진행 중인 파일을 함께 담는다 — 실제로 한 번 섞였다. **고친 파일을 이름으로
스테이징한다.** 커밋 전 `git status --short`로 담긴 것이 내 것만인지 본다.

작업트리에 남의 미커밋 변경이 있는 상태로 프론트를 배포하면 (Vercel CLI는
작업트리를 올린다) 그것까지 함께 나간다. 커밋된 상태만 올리려면 임시 워크트리를
쓴다: `git worktree add --detach <임시경로> HEAD` 후 `frontend/.vercel`을
복사해 거기서 배포하고, 끝나면 `git worktree remove --force`.
