/**
 * 답변 하나에서 그래프에 반영된 것
 *
 * 추정으로 넣었다는 사실을 숨기지 않는다. 여기 붙은 인물·장소·날짜는 확인
 * 화면에서 가족이 "맞음"을 누를 때 사실이 된다 (기획안 STEP 04).
 * 그래프에 없어서 잇지 못한 표현도 함께 밝힌다 — 없는 사람을 만들지 않는다.
 *
 * 모으기(첫 질문)와 AI 인터뷰가 같은 것을 보여줘야 해서 여기 둔다. 한쪽에만
 * 있으면 같은 답변인데 화면마다 다르게 동작한다 (실제로 그랬다).
 */

import { Link } from 'react-router-dom'
import { ExtractedFromAnswer } from '../lib/api'

const FILLED_LABEL: Record<string, string> = {
  date_start: '날짜',
  location_id: '장소',
}

export default function LearnedFromAnswer({
  learned,
  className = 'ml-[42px] mt-2.5',
}: {
  learned: ExtractedFromAnswer
  /** 화면마다 들여쓰기가 달라서 바깥에서 정한다 */
  className?: string
}) {
  const linked = [
    ...learned.persons.map((p) => p.name),
    learned.place?.name,
    learned.date,
  ].filter(Boolean) as string[]

  if (linked.length === 0 && learned.unmatched.length === 0) return null

  return (
    <div className={className}>
      {linked.length > 0 && (
        <p className="t-caption m-0">
          이 답변에서 알아낸 것 · {linked.join(' · ')}
          {learned.filled.length > 0 && (
            <span style={{ color: 'var(--accent-ink)' }}>
              {' '}
              — 비어 있던 {learned.filled.map((f) => FILLED_LABEL[f] || f).join('·')}를
              채웠습니다 (추정)
            </span>
          )}
        </p>
      )}
      {learned.unmatched.length > 0 && (
        <p className="t-caption m-0 mt-1 text-ink-300">
          {learned.unmatched.join(' · ')} 은 아직 가족 공간에 없어 잇지 않았습니다.
        </p>
      )}
      <Link to="/continue" className="t-caption text-accent-ink">
        기억 이어가기에서 보기 →
      </Link>
    </div>
  )
}
