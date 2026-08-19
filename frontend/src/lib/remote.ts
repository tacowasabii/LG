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
 * 격자 위의 포커스 이동. TV에서 포커스는 "지금 어디에 있는가"를 알려주는
 * 유일한 신호이므로 경계에서 튀지 않게 한다 (끝에서 반대편으로 감기지 않음).
 */
export function useGridFocus(count: number, cols: number) {
  const [index, setIndex] = useState(0)

  // 목록이 짧아지면 포커스가 빈 칸에 남지 않게 당겨 온다
  useEffect(() => {
    setIndex((i) => Math.max(0, Math.min(i, count - 1)))
  }, [count])

  const move = useCallback(
    (key: RemoteKey) => {
      setIndex((i) => {
        const col = i % cols
        const lastRow = Math.floor((count - 1) / cols)
        const row = Math.floor(i / cols)

        if (key === 'left') return col > 0 ? i - 1 : i
        if (key === 'right') return col < cols - 1 && i + 1 < count ? i + 1 : i
        if (key === 'up') return row > 0 ? i - cols : i
        if (key === 'down') return row < lastRow ? Math.min(i + cols, count - 1) : i
        return i
      })
    },
    [count, cols],
  )

  return { index, setIndex, move }
}
