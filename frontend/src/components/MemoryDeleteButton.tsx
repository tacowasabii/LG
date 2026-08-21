/**
 * 기억 하나 지우기 (블록 안에 붙는 조용한 단추)
 *
 * 추억 상세와 기억 이어가기 두 곳이 함께 쓴다. MemoryContextNote를 뺀 것과 같은
 * 이유다 — 되돌릴 수 없는 행위의 문구와 확인 절차가 화면마다 따로 있으면 조용히
 * 갈라진다. 한쪽은 무엇이 남는지 말하고 한쪽은 말하지 않는 상태가 가장 나쁘다.
 *
 * 세 가지를 지킨다.
 *
 *   조용히      기억을 읽는 화면에서 가장 눈에 띄는 것이 지우기여서는 안 된다.
 *               그래서 밑줄 친 11px 회색 글자 하나이고, 알약도 색도 쓰지 않는다.
 *   한 번 더    누르면 그 자리에서 묻는다. 되돌릴 수 없다.
 *   무엇이 가나  목소리로 남긴 기억이면 녹음도 함께 사라지고, 함께 올린 사진·영상은
 *               추억에 남는다. 둘 다 묻는 문장에 적는다 — 어느 쪽이든 모르고
 *               누르면 지운 사람이 나중에 알게 된다.
 *
 * 녹음 개수를 세어 적지 않는다. 인터뷰로 남긴 목소리는 기억 노드의 media_ids가
 * 아니라 근거 엣지에만 걸려 있어서 화면이 세지 못한다 (interview_engine). 세지
 * 못하는 것을 0개라고 적으면 거짓이 되므로, 개수 없이 규칙만 적고 실제로 몇 개가
 * 지워졌는지는 지운 뒤 서버가 밝힌다.
 *
 * 권한은 화면이 판단하지 않는다. 남의 기억이면 서버가 403으로 막고 이유를 함께
 * 보내고("이 기억은 박서연님이 올렸습니다…"), 그 문장을 그대로 적는다. 단추를
 * 미리 감추면 왜 못 지우는지 말할 자리가 없어지고, 권한 규칙이 화면과 서버 두
 * 곳에 생긴다 (사진 삭제와 같은 방식이다).
 */

import { useState } from 'react'
import { Trash2 } from 'lucide-react'
import { MemoryEntry, readDetail } from '../lib/api'

export default function MemoryDeleteButton({
  memory,
  onDelete,
}: {
  memory: MemoryEntry
  /** 지우기. 서버가 막으면 그 이유를 담은 오류를 던진다 (여기서 받아 적는다) */
  onDelete: (memoryId: string) => Promise<void>
}) {
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)
  const [failed, setFailed] = useState<string | null>(null)
  /* 추억에 남는 것 — 목소리는 함께 지워지므로 사진·영상만 센다 */
  const visuals = memory.media.filter((m) => m.media_type !== 'audio').length

  const remove = async () => {
    setBusy(true)
    setFailed(null)
    try {
      await onDelete(memory.id)
    } catch (e) {
      setFailed(readDetail(e, '지우지 못했습니다.'))
      setConfirming(false)
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      {!confirming ? (
        <div className="mt-3 flex items-center justify-end">
          <button
            onClick={() => {
              setConfirming(true)
              setFailed(null)
            }}
            className="btn-link flex items-center gap-1 text-[11px]"
          >
            <Trash2 size={12} />
            지우기
          </button>
        </div>
      ) : (
        <div className="mt-3 rounded px-4 py-3" style={{ background: 'var(--critical-soft)' }}>
          <p className="t-body-sm m-0" style={{ color: 'var(--critical-ink)' }}>
            이 기억을 지웁니다. 되돌릴 수 없습니다.
          </p>
          <p className="t-caption m-0 mt-1" style={{ color: 'var(--critical-ink)' }}>
            목소리로 남긴 기억이면 그 녹음도 함께 지워집니다.
            {visuals > 0
              ? ` 함께 올린 사진·영상 ${visuals}개는 이 추억에 남습니다 — 원본은 사진첩에서 지웁니다.`
              : ' 이 추억의 다른 기억은 그대로 있습니다.'}
          </p>
          <div className="mt-3 flex items-center gap-3">
            <button
              onClick={remove}
              disabled={busy}
              className="cursor-pointer rounded border-0 px-4 py-2 text-[13px] disabled:opacity-40"
              style={{ background: 'var(--critical-ink)', color: 'var(--paper)' }}
            >
              {busy ? '지우는 중…' : '정말 지웁니다'}
            </button>
            <button onClick={() => setConfirming(false)} disabled={busy} className="btn-quiet">
              취소
            </button>
          </div>
        </div>
      )}

      {failed && (
        <p className="t-body-sm m-0 mt-2" style={{ color: 'var(--critical-ink)' }}>
          {failed}
        </p>
      )}
    </>
  )
}
