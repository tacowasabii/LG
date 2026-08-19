/**
 * 시작하기 — 콜드스타트 온보딩 (기획안 10장 리스크 "데이터가 처음엔 없음")
 *
 * 기획안의 대응 방향은 "사진 3장으로 시작, 질문하고 답하며 데이터가 쌓이는 온보딩"이다.
 * 완성된 그래프만 보여주면 첫 사용자가 무엇을 하는지 알 수 없으므로, 빈 상태에서
 * 첫 사건 하나가 만들어지는 과정을 그대로 걷게 한다.
 *
 * 흉내가 아니라 실제로 올린다. 업로드 응답에 담긴 촬영 시점·사건 연결 결과를
 * 그대로 보여주므로, EXIF가 없는 사진에서는 "정보 필요"가 정직하게 뜬다.
 * 이어지는 질문도 실제 인터뷰 세션이고, 답변은 지금 사용 중인 사람의 기억으로 남는다.
 *
 * 단계 표시를 카드나 화살표로 잇지 않는다. 알약 네 개를 나란히 두고 색으로만
 * 지난 단계(teal) · 지금 단계(강조색) · 남은 단계(잉크)를 구분하는 편이, 화면의
 * 나머지가 매 단계 크게 바뀌는 흐름에서 훨씬 조용하게 읽힌다.
 */

import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  InterviewStartResult,
  MediaUploadResult,
  startInterview,
  submitInterviewAnswer,
  uploadMedia,
} from '../lib/api'
import { useCurrentUser } from '../lib/currentUser'
import { invalidateEvents } from '../lib/useGraphData'
import { Page, PageHeader, StatRow } from '../components/Page'
import RichText from '../components/RichText'

const STEPS = ['사진 고르기', '읽는 중', '첫 질문', '첫 기록 완성']

/** 한 번에 올릴 사진 수 — 기획안이 정한 "사진 3장으로 시작" */
const PICK_LIMIT = 3

const NEXT_STEPS = [
  { to: '/verify', label: 'AI가 추정한 것을 확인하기' },
  { to: '/upload', label: '남은 사진에 정보 알려주기' },
  { to: '/chat', label: '기억에 물어보기' },
]

interface Picked {
  file: File
  previewUrl: string
}

export default function OnboardingPage() {
  const { current } = useCurrentUser()
  const [step, setStep] = useState(0)
  const [picked, setPicked] = useState<Picked[]>([])
  const [results, setResults] = useState<MediaUploadResult[]>([])
  const [uploadError, setUploadError] = useState<string | null>(null)

  const [session, setSession] = useState<InterviewStartResult | null>(null)
  const [answer, setAnswer] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [memoryCount, setMemoryCount] = useState(0)

  const fileInput = useRef<HTMLInputElement>(null)

  // 미리보기 URL은 화면을 떠날 때 풀어 준다
  useEffect(() => {
    return () => picked.forEach((p) => URL.revokeObjectURL(p.previewUrl))
  }, [picked])

  const choose = (files: FileList | null) => {
    if (!files) return
    const next = Array.from(files)
      .slice(0, PICK_LIMIT)
      .map((file) => ({ file, previewUrl: URL.createObjectURL(file) }))
    setPicked(next)
    setUploadError(null)
  }

  const upload = async () => {
    setStep(1)
    setUploadError(null)
    const uploaded: MediaUploadResult[] = []

    for (const item of picked) {
      try {
        uploaded.push(await uploadMedia(item.file))
        setResults([...uploaded])
      } catch (e) {
        console.error(e)
        setUploadError('사진을 올리지 못했습니다. 파일 형식을 확인해 주세요.')
      }
    }

    invalidateEvents()

    if (uploaded.length === 0) {
      setStep(0)
      return
    }

    // 올린 것을 바탕으로 AI가 물을 것을 고른다
    try {
      setSession(await startInterview('auto'))
      setStep(2)
    } catch (e) {
      console.error(e)
      // 질문을 못 가져와도 올린 것은 남았다. 결과로 넘긴다.
      setStep(3)
    }
  }

  const submit = async () => {
    if (!session || !answer.trim()) return
    setSubmitting(true)
    try {
      const result = await submitInterviewAnswer(session.session_id, answer.trim(), current?.id)
      setMemoryCount(result.updated_nodes.length)
      invalidateEvents()
      setStep(3)
    } catch (e) {
      console.error(e)
    } finally {
      setSubmitting(false)
    }
  }

  const restart = () => {
    picked.forEach((p) => URL.revokeObjectURL(p.previewUrl))
    setPicked([])
    setResults([])
    setSession(null)
    setAnswer('')
    setMemoryCount(0)
    setStep(0)
  }

  const linked = results.filter((r) => r.linked_event_id).length
  const needsInfo = results.filter((r) => r.needs_info).length

  return (
    <Page width={820}>
      <PageHeader
        eyebrow="Getting Started"
        title="사진 3장으로 시작합니다"
        lead="한 번에 전부 정리하지 않아도 됩니다. 첫 기록만 올리고, 나머지는 질문에 답하면서 채워집니다."
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

      {/* STEP 1 — 사진 고르기 */}
      {step === 0 && (
        <div className="mt-8">
          <p className="m-0 text-[19px] font-semibold text-ink-900">
            가장 오래된 사진 3장을 골라주세요
          </p>
          <p className="t-body-sm mt-2 max-w-[56ch]">
            촬영 시점이 남아 있는 사진이면 AI가 사건을 스스로 묶습니다. 스캔한 옛 사진처럼
            시점이 없으면 다음에 직접 알려주게 됩니다.
          </p>

          <input
            ref={fileInput}
            type="file"
            accept="image/*"
            multiple
            onChange={(e) => choose(e.target.files)}
            className="hidden"
          />

          {picked.length === 0 ? (
            <button
              onClick={() => fileInput.current?.click()}
              className="mt-6 w-full cursor-pointer rounded-lg bg-transparent py-14 text-center"
              style={{ border: '1px dashed var(--border-strong)' }}
            >
              <span className="block text-[15px] font-semibold text-ink-900">사진 고르기</span>
              <span className="t-caption mt-1.5 block">최대 {PICK_LIMIT}장 · JPG · PNG</span>
            </button>
          ) : (
            <>
              <div className="mt-6 grid grid-cols-3 gap-3">
                {picked.map((item, index) => (
                  <div
                    key={item.previewUrl}
                    className="relative aspect-square overflow-hidden rounded-lg bg-ink-50"
                  >
                    <img
                      src={item.previewUrl}
                      alt=""
                      className="block h-full w-full object-cover"
                    />
                    <span
                      className="t-mono absolute left-2.5 top-2.5 flex h-[22px] w-[22px]
                                 items-center justify-center rounded-full text-[11px]"
                      style={{ background: 'var(--accent)', color: 'var(--accent-fg)' }}
                    >
                      {index + 1}
                    </span>
                    <span
                      className="absolute inset-x-0 bottom-0 truncate p-1.5 text-[11px]"
                      style={{ background: 'rgba(14,13,11,0.55)', color: 'var(--paper)' }}
                    >
                      {item.file.name}
                    </span>
                  </div>
                ))}
              </div>

              <div className="mt-5 flex items-center justify-between">
                <button onClick={() => fileInput.current?.click()} className="btn-link px-0">
                  다시 고르기
                </button>
                <button onClick={upload} className="btn-primary">
                  올리기 →
                </button>
              </div>
            </>
          )}

          {uploadError && (
            <p className="t-caption mt-4" style={{ color: 'var(--critical-ink)' }}>
              {uploadError}
            </p>
          )}
        </div>
      )}

      {/* STEP 2 — 읽는 중 (실제 업로드 응답을 그대로 보여준다) */}
      {step === 1 && (
        <div className="mt-8">
          <p className="m-0 text-[19px] font-semibold text-ink-900">사진을 읽고 있습니다</p>
          <div className="mt-5 flex flex-col gap-2">
            {picked.map((item, i) => {
              const result = results[i]
              return (
                <div
                  key={item.previewUrl}
                  className="flex items-center gap-3.5 rounded px-4 py-3.5"
                  style={
                    result
                      ? { background: 'var(--positive-soft)', color: 'var(--positive-ink)' }
                      : { background: 'var(--ink-50)', color: 'var(--ink-300)' }
                  }
                >
                  <span className="t-mono w-4 text-[11px] text-current">
                    {result ? '✓' : i + 1}
                  </span>
                  <span className="flex-1 truncate text-sm">{item.file.name}</span>
                  <span className="t-mono text-[11px] text-current opacity-70">
                    {!result
                      ? '올리는 중…'
                      : result.exif_date
                        ? result.exif_date.slice(0, 10) +
                          (result.linked_event_id ? ' · 사건 연결' : '')
                        : '촬영 시점 없음 · 정보 필요'}
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

      {/* STEP 3 — 첫 질문 (실제 인터뷰 세션) */}
      {step === 2 && session && (
        <div className="surface mt-8 p-7">
          <p className="t-caption m-0">
            {current?.name ?? '지금 보는 사람'}님께 묻습니다 · 이 답변은 그 사람의 기억으로
            저장됩니다
          </p>
          <p className="m-0 mt-2.5 whitespace-pre-wrap text-[19px] font-semibold leading-normal text-ink-900">
            <RichText text={session.question} />
          </p>

          <textarea
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
            rows={3}
            placeholder="말하듯이 적어도 됩니다."
            className="field mt-5 w-full"
          />

          <div className="mt-4 flex flex-wrap items-center justify-between gap-4">
            <p className="t-caption m-0">
              목소리로 남기려면 인터뷰 화면에서 말로 답하기를 쓰세요.
            </p>
            <button
              onClick={submit}
              disabled={!answer.trim() || submitting}
              className="btn-primary disabled:opacity-40"
            >
              {submitting ? '남기는 중…' : '기억 남기기'}
            </button>
          </div>
        </div>
      )}

      {/* STEP 4 — 완성 */}
      {step === 3 && (
        <div className="mt-8">
          <p className="m-0 text-2xl font-bold tracking-[-0.02em] text-ink-900">
            첫 기록이 들어왔습니다
          </p>

          <div className="mt-7">
            <StatRow
              size={36}
              cells={[
                { value: results.length, label: '올린 사진' },
                { value: linked, label: '사건 연결' },
                { value: needsInfo, label: '정보 필요' },
                { value: memoryCount, label: '남긴 기억' },
              ]}
            />
          </div>

          {needsInfo > 0 && (
            <p className="t-body-sm mt-5 max-w-[60ch]">
              촬영 시점이 없는 사진 {needsInfo}장은 아직 사건에 붙지 못했습니다. 업로드 화면에서
              날짜나 사건을 알려주면 연결됩니다.
            </p>
          )}

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

          <button onClick={restart} className="btn-link mt-6">
            사진을 더 올리기
          </button>
        </div>
      )}
    </Page>
  )
}
