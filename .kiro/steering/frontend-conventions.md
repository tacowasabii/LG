---
inclusion: fileMatch
fileMatchPattern: "**/*.{ts,tsx}"
---

# Frontend 개발 규칙 (React + TypeScript)

## 파일 구조

```
frontend/src/
  App.tsx            라우팅 정의
  main.tsx           진입점
  layouts/           레이아웃 컴포넌트
    AppLayout.tsx      사이드바 포함 일반 레이아웃
    TVLayout.tsx       풀스크린 TV 전용 레이아웃
  pages/             페이지 컴포넌트 (*Page.tsx)
  lib/
    api.ts           모든 API 호출 함수 + TypeScript 인터페이스
  index.css          Tailwind directives + 글로벌 스타일
```

## 네이밍 규칙

| 대상 | 규칙 | 예시 |
|------|------|------|
| 페이지 컴포넌트 | PascalCase + "Page" 접미사 | `HomePage.tsx`, `ChatPage.tsx` |
| 레이아웃 | PascalCase + "Layout" 접미사 | `AppLayout.tsx` |
| API 함수 | camelCase 동사 시작 | `getEvents()`, `sendChat()`, `uploadMedia()` |
| 인터페이스 | PascalCase | `MediaItem`, `GraphNode`, `ChatResponse` |
| 파일명 | PascalCase (컴포넌트), camelCase (유틸) | `HomePage.tsx`, `api.ts` |

## API 호출 규칙

모든 API 통신은 `src/lib/api.ts`를 통해 수행한다. 컴포넌트에서 직접 fetch 하지 않는다.

```typescript
// ✅ 올바른 사용
import { getEvents, sendChat } from '../lib/api';

// ❌ 금지 — 컴포넌트에서 직접 fetch
const res = await fetch('/api/graph/events');
```

**새 API 연동 추가 시**:
1. `api.ts`에 인터페이스 정의 (백엔드 schemas.py와 매칭)
2. `api.ts`에 함수 추가
3. 정적 모드 대응이 필요하면 `fetchJSON` 내 `mockMap`에 추가

## 정적 모드 (Static Mode)

`VITE_STATIC_MODE=true`이면 백엔드 없이 `public/mock/` JSON을 읽어서 동작.
Vercel 배포 시 사용.

- 새 API 추가 시 mock JSON도 함께 만들기
- `mediaUrl()` 함수로 미디어 경로 변환 (정적/동적 자동 분기)

## 스타일링 (Tailwind CSS)

- **기본 도구**: Tailwind 유틸리티 클래스만 사용 (별도 CSS 파일 금지)
- **테마 색상**:
  - `primary-600` = LG Red (#a50034) — 강조, 브랜드
  - `gray-500` = LG Grey (#6b6b6b) — 보조 텍스트
  - `primary-50` ~ `primary-100` — 배경 하이라이트
- **폰트**: Noto Sans KR (한글) + Inter (영문), `font-sans`로 자동 적용
- **반응형**: 필수 아님 (데모용), 하지만 기본적인 flex/grid 레이아웃 사용

```tsx
// ✅ 색상 예시
<button className="bg-primary-600 hover:bg-primary-700 text-white rounded-lg px-4 py-2">
  확인
</button>
<p className="text-gray-500 text-sm">보조 설명</p>
```

## 라우팅

- `react-router-dom` v6 사용
- 일반 페이지: `<AppLayout>` 안에 중첩
- TV 페이지: `<TVLayout>` 사용 (풀스크린, 사이드바 없음)
- 새 페이지 추가 시 `App.tsx`에 Route 등록

## 아이콘

```tsx
import { Camera, MessageCircle, Users } from 'lucide-react';
// className으로 사이즈/색상 조절
<Camera className="w-5 h-5 text-gray-400" />
```

## UI 텍스트

- 모든 사용자 노출 텍스트는 **한국어**
- placeholder, label, 에러 메시지, 버튼 텍스트 모두 한국어
- 변수명/주석은 영어

## 컴포넌트 작성 패턴

```tsx
// 함수형 컴포넌트 + 기본 export
function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  // ...
  return <div>...</div>;
}
export default ChatPage;
```

- React hooks 사용 (useState, useEffect, useCallback 등)
- class 컴포넌트 사용하지 않음
- props가 복잡하면 interface로 타입 정의

## 의존성 관리

현재 주요 의존성:
- `react-router-dom` — 라우팅
- `react-force-graph-2d` — Graph 시각화
- `lucide-react` — 아이콘

새 패키지 추가 전에 기존 패키지로 해결 가능한지 먼저 확인.
