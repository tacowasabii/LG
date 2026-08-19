/**
 * 리모컨 조작 안내 (기획안 06장 LG TV / webOS)
 *
 * TV 화면에는 마우스 커서가 없어서 "무엇을 누르면 되는지"를 화면이 직접
 * 알려주지 않으면 사용자가 멈춘다. 그래서 대기화면·메뉴·재생 세 화면 모두
 * 같은 자리(하단)에 같은 모양으로 조작 안내를 깐다.
 *
 * 실기기 연동 시 교체 지점:
 *   버튼 글리프 -> webOS 리모컨 아이콘 폰트 (모델별로 버튼 모양이 다르다)
 */

interface Hint {
  /** 리모컨 버튼 표기 (OK, BACK, ▲▼◀▶ 등) */
  key: string
  label: string
}

interface Props {
  hints: Hint[]
  /** 대기화면처럼 배경 사진 위에 얹을 때 */
  onPhoto?: boolean
}

export default function RemoteHint({ hints, onPhoto = false }: Props) {
  return (
    <div className="flex flex-wrap items-center justify-center gap-x-[2.5vw] gap-y-2">
      {hints.map((hint) => (
        <span key={hint.key + hint.label} className="inline-flex items-center gap-2">
          <kbd
            className="tv-caption min-w-[3.2vw] rounded-md px-[0.7vw] py-[0.25vh] text-center font-semibold"
            style={
              onPhoto
                ? { background: 'rgba(250,250,247,0.9)', color: 'var(--ink-900)' }
                : {
                    background: 'rgba(250,250,247,0.15)',
                    border: '1px solid rgba(250,250,247,0.25)',
                    color: 'var(--paper)',
                  }
            }
          >
            {hint.key}
          </kbd>
          <span
            className="tv-caption"
            style={{ color: onPhoto ? 'var(--paper)' : 'rgba(250,250,247,0.7)' }}
          >
            {hint.label}
          </span>
        </span>
      ))}
    </div>
  )
}
