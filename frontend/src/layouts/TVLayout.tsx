import { Outlet } from 'react-router-dom'

/**
 * TV 전용 레이아웃 (기획안 06장 LG TV / webOS)
 *
 * 사이드바도 스크롤도 없는 한 장짜리 화면이다. TV에는 스크롤 조작이 없어서
 * 화면이 넘치면 그 부분은 영원히 볼 수 없다. 그래서 overflow를 잠그고,
 * 각 화면이 스스로 100vh 안에 들어오게 만든다.
 *
 * data-theme="dark"로 강조색을 갈아 끼운다. 와인색(#8A1538)은 잉크색 배경에서
 * 거의 보이지 않아, 어두운 면에서는 같은 계열의 밝은 베리색이 대신 나간다.
 * 배경은 순검정이 아니라 잉크 900 — 사진의 검은 부분이 배경에 녹아 사라지지
 * 않게 한다.
 *
 * 글자 선택 커서가 사진 위에 나타나면 대기화면이 웹 페이지처럼 보이므로 끈다.
 */
export default function TVLayout() {
  return (
    <div
      data-theme="dark"
      className="h-screen w-screen select-none overflow-hidden"
      style={{ background: 'var(--ink-900)' }}
    >
      <Outlet />
    </div>
  )
}
