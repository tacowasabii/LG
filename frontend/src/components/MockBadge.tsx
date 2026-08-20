/**
 * 목데이터 표시
 *
 * 이 단계에서는 화면 설계를 확정하는 것이 목적이라 값이 가짜인 영역이 많다.
 * 가짜 값을 실제 측정값으로 착각하지 않도록 해당 영역마다 이 뱃지를 붙인다.
 * 실기능 연동이 끝난 영역에서는 뱃지를 지운다.
 *
 * 경고색을 쓰지 않는다. 이건 오류가 아니라 각주이고, 화면의 강조색 예산은
 * 정말 주의를 끌어야 하는 곳(가족이 다르게 기억하는 추억)에 남겨 둔다.
 */
export default function MockBadge({ label = '목데이터' }: { label?: string }) {
  return (
    <span
      className="inline-flex items-center whitespace-nowrap rounded-full bg-ink-50 px-2 py-0.5
                 text-[10px] font-medium normal-case tracking-normal text-ink-400"
    >
      {label}
    </span>
  )
}
