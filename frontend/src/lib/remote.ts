/**
 * 리모컨 입력 (기획안 06장 LG PRODUCT LINKAGE · LG TV / webOS)
 *
 * TV에는 마우스도 키보드도 없다. 쓸 수 있는 입력은 방향키 4개 + OK + BACK,
 * 여기에 재생/일시정지까지가 전부다. 화면 설계가 이 범위를 넘지 않도록
 * 입력 해석을 한 곳에 모아 두었다. 새 조작을 추가하려면 여기부터 막힌다.
 *
 * 실기기 연동 시 교체 지점:
 *   WEBOS_KEYCODE -> Magic Remote 포인터·휠 이벤트 추가
 *   'back'        -> webOS는 브라우저 히스토리와 별개로 keyCode 461을 쏜다
 *   음성 입력      -> webOS Voice Intent (별도 서비스 호출, 키 이벤트가 아니다)
 */

import { useCallback, useEffect, useRef, useState } from 'react'

export type RemoteKey = 'left' | 'right' | 'up' | 'down' | 'ok' | 'back' | 'playpause'

/** webOS 리모컨이 쏘는 keyCode. 브라우저 표준 key 이름이 없는 버튼들이 있다 */
const WEBOS_KEYCODE: Record<number, RemoteKey> = {
  461: 'back', // BACK 버튼
  415: 'playpause', // MediaPlay
  19: 'playpause', // MediaPause
  413: 'back', // MediaStop
}

/** 개발·발표용 브라우저 키보드 매핑 */
const BROWSER_KEY: Record<string, RemoteKey> = {
  ArrowLeft: 'left',
  ArrowRight: 'right',
  ArrowUp: 'up',
  ArrowDown: 'down',
  Enter: 'ok',
  Escape: 'back',
  Backspace: 'back',
  ' ': 'playpause',
}

function toRemoteKey(e: KeyboardEvent): RemoteKey | null {
  return WEBOS_KEYCODE[e.keyCode] ?? BROWSER_KEY[e.key] ?? null
}

/**
 * 리모컨 키 하나를 받아 처리한다. 핸들러는 ref로 잡아 두므로 매 렌더마다
 * 리스너를 다시 붙이지 않는다 (슬라이드가 바뀔 때 키가 씹히던 문제).
 */
export function useRemote(handler: (key: RemoteKey) => void) {
  const ref = useRef(handler)
  ref.current = handler

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      const key = toRemoteKey(e)
      if (!key) return
      // 스페이스 스크롤, 백스페이스 뒤로가기 같은 브라우저 기본 동작을 막는다
      e.preventDefault()
      ref.current(key)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])
}

/**
 * 줄(rail)로 나뉜 목록 위의 포커스 이동.
 *
 * 격자는 항목이 늘어나면 타일을 잘게 쪼갠다 — 3m 거리에서 읽을 수 없는 크기가
 * 된다. 줄로 깔면 타일 크기를 지키면서 개수를 늘릴 수 있고, TV에는 잡을 수 있는
 * 스크롤바가 없으니 포커스가 곧 스크롤이 된다 (화면 밖 타일은 ▶로 끌어온다).
 *
 * ▲▼로 줄을 옮길 때는 있던 열을 그대로 들고 간다. 매번 왼쪽 끝으로 튀면 방금
 * 어디를 보고 있었는지 잃는다.
 *
 * 자리는 저장할 때가 아니라 읽을 때 범위 안으로 접는다. 목록이 늦게 도착하는
 * 화면이라(추억을 API로 받는다) 그 사이에 담긴 자리가 빈 칸을 가리킬 수 있다.
 */
export function useRailFocus(counts: number[]) {
  const [pos, setPos] = useState({ rail: 0, index: 0 })
  /** move()를 누른 횟수 — 리모컨으로 움직였을 때만 줄을 밀기 위해 센다 */
  const [moves, setMoves] = useState(0)

  const rail = Math.max(0, Math.min(pos.rail, counts.length - 1))
  const index = Math.max(0, Math.min(pos.index, (counts[rail] ?? 0) - 1))

  // 접힌 자리와 지금 개수를 ref로 들고 있어서 move()가 렌더마다 새로 생기지 않는다
  const now = useRef({ rail, index, counts })
  now.current = { rail, index, counts }

  const move = useCallback((key: RemoteKey) => {
    setMoves((n) => n + 1)
    const { rail: r, index: i, counts: sizes } = now.current
    if (key === 'left') setPos({ rail: r, index: Math.max(0, i - 1) })
    else if (key === 'right') setPos({ rail: r, index: Math.min((sizes[r] ?? 0) - 1, i + 1) })
    else if (key === 'up' && r > 0) setPos({ rail: r - 1, index: i })
    else if (key === 'down' && r < sizes.length - 1) setPos({ rail: r + 1, index: i })
  }, [])

  /** 마우스로 짚었을 때 — 줄을 밀지 않는다 (커서 아래에서 타일이 도망간다) */
  const focus = useCallback((toRail: number, toIndex: number) => {
    setPos({ rail: toRail, index: toIndex })
  }, [])

  return { rail, index, moves, move, focus }
}
