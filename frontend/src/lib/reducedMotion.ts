/**
 * 움직임을 줄이도록 설정한 사용자인가
 *
 * index.css는 `prefers-reduced-motion`에서 CSS 애니메이션(motion-*)을 끈다.
 * 그런데 영상 재생은 CSS로 멈출 수 없어서, 생성 클립을 쓰는 화면은 이 값을
 * 직접 읽어 같은 취지를 지켜야 한다.
 *
 * 라벨에도 쓰인다. 화면이 멈춰 있는데 "AI 생성 미세 움직임"이라고 적으면
 * 적용된 것을 드러낸다는 원칙이 반대로 뒤집힌다 — 걸지 않은 효과를 밝히는 셈이다.
 *
 * Film과 TV가 함께 쓴다. 두 곳에 같은 훅을 두면 한쪽만 고쳐지는 일이 생긴다.
 */

import { useEffect, useState } from 'react'

const QUERY = '(prefers-reduced-motion: reduce)'

export function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false)

  useEffect(() => {
    const query = window.matchMedia(QUERY)
    setReduced(query.matches)
    const onChange = () => setReduced(query.matches)
    query.addEventListener('change', onChange)
    return () => query.removeEventListener('change', onChange)
  }, [])

  return reduced
}
