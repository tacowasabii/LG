/**
 * 시작하기 — 콜드스타트 온보딩 (기획안 10장 리스크 "데이터가 처음엔 없음")
 *
 * 기획안의 대응 방향은 "사진 3장으로 시작, 질문하고 답하며 데이터가 쌓이는 온보딩"이다.
 * 완성된 그래프만 보여주면 첫 사용자가 무엇을 하는지 알 수 없으므로,
 * 빈 상태에서 첫 사건 하나가 만들어지는 과정을 그대로 화면에 담았다.
 *
 * 단계 표시를 카드나 화살표로 잇지 않는다. 알약 네 개를 나란히 두고 색으로만
 * 지난 단계(teal) · 지금 단계(강조색) · 남은 단계(잉크)를 구분하는 편이, 화면의
 * 나머지가 매 단계 크게 바뀌는 흐름에서 훨씬 조용하게 읽힌다.
 *
 * 실기능 개발 시 교체 지점:
 *   후보 사진 선택 -> 실제 파일 선택 + POST /api/media/upload
 *   분석 체크리스트 -> 업로드 응답(EXIF/이벤트 매칭 결과)에 따라 표시
 *   첫 질문/답변    -> POST /api/interview/start, /api/interview/answer
 */

import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { mediaUrl } from '../lib/api'
import { MOCK_ONBOARDING_CANDIDATES } from '../mock/timeline'
import { useCurrentUser } from '../lib/currentUser'
import { Page, PageHeader, StatRow } from '../components/Page'

/**
 * 온보딩은 실제 업로드가 아니라 처음 오는 사람에게 흐름을 보여주는 안내다.
 * 말로 답하기 시늉을 할 때 채워지는 예시 문장 (실제 녹음·전사는 인터뷰 화면).
 */
const SAMPLE_ANSWER = '그날은 아침에 비가 조금 왔어요. 점심 지나서 개서 그때 바다에 나갔지.'

const STEPS = ['사진 고르기', '읽는 중', '첫 질문', '첫 사건 완성']

const ANALYSIS_TASKS = [
  { label: '촬영 시점 읽기', detail: 'EXIF · 1998-08-13' },
  { label: '장면 이해하기', detail: '해변 · 가족 · 여행' },
  { label: '인물 후보 찾기', detail: '3명 발견 (확인 필요)' },
  { label: '같은 사건으로 묶기', detail: '사진 3장 → 사건 1개' },
]

const NEXT_STEPS = [
  { to: '/verify', label: '인물 후보 3명 확인하기' },
  { to: '/graph', label: '연결된 모습 보기' },
  { to: '/chat', label: '기억에 물어보기' },
]

export default function OnboardingPage() {
  const { current } = useCurrentUser()
  const [step, setStep] = useState(0)
  const [picked, setPicked] = useState<string[]>([])
  const [doneTasks, setDoneTasks] = useState(0)
  const [answer, setAnswer] = useState('')
  const [recording, setRecording] = useState(false)

  // 분석 단계: 체크리스트를 차례로 채운다
  useEffect(() => {
    if (step !== 1) return
    setDoneTasks(0)

    const timers = ANALYSIS_TASKS.map((_, i) =>
      window.setTimeout(() => setDoneTasks(i + 1), 700 * (i + 1)),
    )
    const advance = window.setTimeout(() => setStep(2), 700 * (ANALYSIS_TASKS.length + 1))

    return () => {
      timers.forEach(window.clearTimeout)
      window.clearTimeout(advance)
    }
  }, [step])

  // 녹음 시뮬레이션: 잠시 뒤 전사문이 채워진다
  useEffect(() => {
    if (!recording) return
    const t = window.setTimeout(() => {
      setRecording(false)
      setAnswer(SAMPLE_ANSWER)
    }, 2400)
    return () => window.clearTimeout(t)
  }, [recording])

  const toggle = (id: string) => {
    setPicked((prev) => {
      if (prev.includes(id)) return prev.filter((p) => p !== id)
      if (prev.length >= 3) return prev
      return [...prev, id]
    })
  }

  return (
    <Page width={820}>
      <PageHeader
        mock
        eyebrow="Getting Started"
        title="사진 3장으로 시작합니다"
        lead="한 번에 전부 정리하지 않아도 됩니다. 첫 사건 하나만 만들고, 나머지는 질문에 답하면서 채워집니다."
      />

      <div className="mt-8 flex flex-wrap items-center gap-2">
        {STEPS.map((label, i) => (
          <span
            key={label}
            className="flex items-center gap-[7px] rounded-full px-3.5 py-[7px] text-xs"
            style={
              i === step
                ? {
                    background: 'var(--accent-soft)',
                    color: 'var(--accent-ink)',
                    fontWeight: 600,
                  }
                : i < step
                  ? { background: 'var(--positive-soft)', color: 'var(--positive-ink)' }
                  : { background: 'var(--ink-50)', color: 'var(--ink-300)' }
            }
          >
            <span className="t-mono text-[10px] text-current">{i < step ? '✓' : i + 1}</span>
            {label}
          </span>
        ))}
      </div>

      {step === 0 && (
        <div className="mt-8">
          <p className="m-0 text-[19px] font-semibold text-ink-900">
            가장 오래된 사진 3장을 골라주세요
          </p>
          <div className="mt-5 grid grid-cols-3 gap-3">
            {MOCK_ONBOARDING_CANDIDATES.map((c) => {
              const index = picked.indexOf(c.id)
              return (
                <button
                  key={c.id}
                  onClick={() => toggle(c.id)}
                  className="relative aspect-square cursor-pointer overflow-hidden
                             rounded-lg bg-ink-50 p-0"
                  style={{
                    border: `2px solid ${index >= 0 ? 'var(--accent)' : 'transparent'}`,
                  }}
                >
                  <img
                    src={mediaUrl(c.path)}
                    alt={c.hint}
                    className="block h-full w-full object-cover"
                  />
                  {index >= 0 && (
                    <span
                      className="t-mono absolute left-2.5 top-2.5 flex h-[22px] w-[22px]
                                 items-center justify-center rounded-full text-[11px]"
                      style={{ background: 'var(--accent)', color: 'var(--accent-fg)' }}
                    >
                      {index + 1}
                    </span>
                  )}
                  <span
                    className="absolute inset-x-0 bottom-0 p-1.5 text-[11px]"
                    style={{ background: 'rgba(14,13,11,0.55)', color: 'var(--paper)' }}
                  >
                    {c.hint}
                  </span>
                </button>
              )
            })}
          </div>

          <div className="mt-5 flex items-center justify-between">
            <span className="t-mono text-xs text-ink-400">{picked.length} / 3 선택</span>
            <button
              disabled={picked.length < 3}
              onClick={() => setStep(1)}
              className="btn-primary disabled:opacity-40"
            >
              다음 →
            </button>
          </div>
        </div>
      )}

      {step === 1 && (
        <div className="mt-8">
          <p className="m-0 text-[19px] font-semibold text-ink-900">사진을 읽고 있습니다</p>
          <div className="mt-5 flex flex-col gap-2">
            {ANALYSIS_TASKS.map((task, i) => {
              const done = i < doneTasks
              return (
                <div
                  key={task.label}
                  className="flex items-center gap-3.5 rounded px-4 py-3.5
                             transition-colors duration-150 ease-out"
                  style={
                    done
                      ? { background: 'var(--positive-soft)', color: 'var(--positive-ink)' }
                      : { background: 'var(--ink-50)', color: 'var(--ink-300)' }
                  }
                >
                  <span className="t-mono w-4 text-[11px] text-current">
                    {done ? '✓' : i + 1}
                  </span>
                  <span className="flex-1 text-sm">{task.label}</span>
                  <span className="t-mono text-[11px] text-current opacity-70">
                    {done ? task.detail : ''}
                  </span>
                </div>
              )
            })}
          </div>
          <p className="t-caption mt-4">
            추정한 정보는 확정하지 않습니다. 다음 단계에서 가족에게 확인을 받습니다.
          </p>
        </div>
      )}

      {step === 2 && (
        <div className="surface mt-8 p-7">
          <p className="t-caption m-0">
            {current.name}님께 묻습니다 · 이 답변은 {current.name}의 기억으로 저장됩니다
          </p>
          <p
            className="m-0 mt-2.5 text-[19px] font-semibold leading-normal text-ink-900"
            style={{ textWrap: 'pretty' }}
          >
            사진 세 장이 같은 날로 보입니다. 1998년 8월, 이날 가장 기억나는 일이 무엇인가요?
          </p>
          <textarea
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
            rows={3}
            placeholder="말하듯이 적어도 됩니다."
            className="field mt-5 resize-y"
            style={{ background: 'var(--paper)' }}
          />
          <div className="mt-4 flex flex-wrap items-center justify-between gap-4">
            <button
              onClick={() => setRecording(true)}
              disabled={recording}
              className="btn-quiet px-[18px] py-2.5 text-[13px]"
            >
              {recording ? '녹음 중…' : '말로 답하기'}
            </button>
            <button
              disabled={!answer.trim()}
              onClick={() => setStep(3)}
              className="btn-primary disabled:opacity-40"
            >
              기억 남기기
            </button>
          </div>
          <p className="t-caption mt-3">음성으로 답하면 목소리 원본이 함께 보관됩니다.</p>
        </div>
      )}

      {step === 3 && (
        <div className="mt-8">
          <p className="m-0 text-2xl font-bold tracking-[-0.02em] text-ink-900">
            첫 사건이 만들어졌습니다
          </p>
          <p className="t-body-sm m-0 mt-2">1998년 8월 · 부산 · 사진 3장 · 기억 1개</p>

          <div className="mt-7">
            <StatRow
              size={36}
              cells={[
                { value: 1, label: '사건' },
                { value: 3, label: '인물 후보' },
                { value: 3, label: '사진' },
                { value: 1, label: '기억' },
              ]}
            />
          </div>

          <p className="t-eyebrow mb-3 mt-9">이어서 하면 좋은 것</p>
          <div className="grid grid-cols-3 gap-3">
            {NEXT_STEPS.map((s) => (
              <Link
                key={s.to}
                to={s.to}
                className="surface hover-border-accent p-5 text-sm text-ink-700
                           no-underline hover:no-underline"
              >
                {s.label}
                <span className="mt-1.5 block text-accent-ink">→</span>
              </Link>
            ))}
          </div>

          <button
            onClick={() => {
              setStep(0)
              setPicked([])
              setAnswer('')
            }}
            className="btn-link mt-6"
          >
            다시 처음부터 보기
          </button>
        </div>
      )}
    </Page>
  )
}
