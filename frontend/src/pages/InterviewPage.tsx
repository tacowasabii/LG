import { useEffect, useState } from 'react'
import {
  startInterview,
  submitInterviewAnswer,
  InterviewStartResult,
  InterviewAnswerResult,
  mediaUrl,
} from '../lib/api'
import RichText from '../components/RichText'
import MockBadge from '../components/MockBadge'
import { Page, PageHeader } from '../components/Page'
import { useCurrentUser } from '../lib/currentUser'
import { MOCK_RECORDING_WAVEFORM, MOCK_TRANSCRIBED } from '../mock/voice'

/**
 * AI 기억 인터뷰
 *
 * 기획안이 "핵심 독자 데이터"로 지목한 화면이다. 두 가지를 더했다.
 *  1. 지금 답하는 사람을 화면에 명시한다. 기억은 사람에게 귀속되는 데이터이므로
 *     누가 답했는지가 화면에서 분명해야 한다 (기획안 08장).
 *  2. 말로 답하는 경로. 기획안은 답변을 "원본 음성으로 저장"한다고 못 박았다.
 *
 * 질문과 답변을 말풍선으로 마주 세우지 않는다. 이건 대화가 아니라 기록을 남기는
 * 일이고, 질문은 왼쪽 여백의 얇은 라벨로 물러나고 답변만 강조색 면에 남는다 —
 * 화면에서 무게를 갖는 것은 가족이 남긴 문장이어야 한다.
 *
 * 실기능 개발 시 교체 지점:
 *   녹음        -> MediaRecorder로 실제 녹음 + POST /api/media/upload (audio)
 *   전사        -> ASR 결과로 MOCK_TRANSCRIBED 대체
 *   화자 귀속   -> POST /api/interview/answer 에 speaker_id 파라미터 추가 필요.
 *                 지금 백엔드는 Gap이 지목한 인물에게 자동 귀속한다.
 */

interface QA {
  question: string
  answer?: string
  /** 음성으로 답했는지 — 실기능에서는 저장된 오디오 id가 들어간다 */
  by_voice?: boolean
  speaker_name?: string
}

type InputMode = 'text' | 'voice'

/** 백엔드가 세션당 다섯 문제를 낸다 */
const QUESTION_TOTAL = 5

export default function InterviewPage() {
  const { current, members, setCurrentId } = useCurrentUser()
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [context, setContext] = useState<InterviewStartResult['context']>(null)
  const [qaHistory, setQaHistory] = useState<QA[]>([])
  const [currentQuestion, setCurrentQuestion] = useState<string | null>(null)
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [isComplete, setIsComplete] = useState(false)
  const [updatedCount, setUpdatedCount] = useState(0)
  const [mode, setMode] = useState<InputMode>('text')
  const [recording, setRecording] = useState(false)
  const [recordSec, setRecordSec] = useState(0)

  // 녹음 시뮬레이션 — 타이머가 돌고, 멈추면 전사문이 입력창에 들어온다
  useEffect(() => {
    if (!recording) return
    const timer = window.setInterval(() => setRecordSec((s) => s + 0.1), 100)
    return () => window.clearInterval(timer)
  }, [recording])

  const toggleRecording = () => {
    if (recording) {
      setRecording(false)
      setInput((prev) => (prev ? prev + ' ' + MOCK_TRANSCRIBED : MOCK_TRANSCRIBED))
      return
    }
    setRecordSec(0)
    setRecording(true)
  }

  const handleStart = async () => {
    setLoading(true)
    try {
      const result = await startInterview('auto')
      setSessionId(result.session_id)
      setContext(result.context)
      setCurrentQuestion(result.question)
      setQaHistory([{ question: result.question }])
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  const handleAnswer = async () => {
    if (!input.trim() || !sessionId || loading) return

    const answer = input.trim()
    const byVoice = mode === 'voice'
    setInput('')
    setRecordSec(0)
    setLoading(true)

    // 현재 질문에 답변 추가
    setQaHistory((prev) => {
      const updated = [...prev]
      updated[updated.length - 1] = {
        ...updated[updated.length - 1],
        answer,
        by_voice: byVoice,
        speaker_name: current.name,
      }
      return updated
    })

    try {
      const result: InterviewAnswerResult = await submitInterviewAnswer(sessionId, answer)
      setUpdatedCount((prev) => prev + result.updated_nodes.length)

      if (result.is_complete) {
        setIsComplete(true)
        setCurrentQuestion(null)
      } else if (result.next_question) {
        setCurrentQuestion(result.next_question)
        setQaHistory((prev) => [...prev, { question: result.next_question! }])
      }
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  const reset = () => {
    setSessionId(null)
    setContext(null)
    setQaHistory([])
    setCurrentQuestion(null)
    setIsComplete(false)
    setUpdatedCount(0)
    setRecordSec(0)
    setRecording(false)
  }

  const answered = qaHistory.filter((qa) => qa.answer).length
  const step = Math.min(qaHistory.length, QUESTION_TOTAL)

  return (
    <Page width={760}>
      <PageHeader
        eyebrow="AI Interview"
        title="AI 기억 인터뷰"
        lead="AI가 기억의 빈 곳을 찾아 질문합니다. 답변은 답한 사람의 기억으로 저장됩니다."
      />

      {/* 지금 답하는 사람 — 기억은 사람에게 귀속되는 데이터다 (기획안 08장) */}
      <div className="surface mt-8 px-6 py-5">
        <div className="flex flex-wrap items-center justify-between gap-5">
          <div>
            <p className="m-0 text-sm text-ink-700">
              지금 답하는 사람 · <span className="font-semibold">{current.name}</span>
            </p>
            <p className="t-caption m-0 mt-[3px]">{current.name}님의 기억으로 저장됩니다.</p>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {members.map((m) => (
              <button
                key={m.id}
                onClick={() => setCurrentId(m.id)}
                className={`chip flex items-center gap-1.5 py-1 pl-1 pr-2.5 ${
                  current.id === m.id ? 'chip-on' : ''
                }`}
              >
                {m.thumbnail_url ? (
                  <img
                    src={mediaUrl(m.thumbnail_url)}
                    alt=""
                    className="h-5 w-5 rounded-full bg-ink-50 object-cover"
                  />
                ) : (
                  <span
                    className="flex h-5 w-5 items-center justify-center rounded-full
                               bg-ink-50 text-[9px] text-ink-300"
                  >
                    {m.name.slice(0, 1)}
                  </span>
                )}
                {m.name}
              </button>
            ))}
          </div>
        </div>
      </div>

      {!sessionId ? (
        <div
          className="mt-8 rounded-lg px-8 py-14 text-center"
          style={{ border: '1px dashed var(--border-strong)' }}
        >
          <p className="m-0 text-xl font-semibold text-ink-900">
            AI가 고른 사건에서 시작합니다
          </p>
          <p className="t-body-sm mx-auto mt-2.5 max-w-[44ch]">
            기억이 가장 비어 있는 사건을 찾아 질문 {QUESTION_TOTAL}개로 채웁니다. 답변은{' '}
            {current.name}님의 기억으로 저장됩니다.
          </p>
          <button
            onClick={handleStart}
            disabled={loading}
            className="btn-primary mt-7 px-7 py-3 text-[15px]"
          >
            {loading ? '준비 중…' : '인터뷰 시작하기'}
          </button>
        </div>
      ) : (
        <>
          <div className="mt-8 flex items-center gap-3">
            <div className="h-0.5 flex-1" style={{ background: 'var(--ink-100)' }}>
              <div
                className="h-0.5 transition-all"
                style={{
                  background: 'var(--accent)',
                  width: (step / QUESTION_TOTAL) * 100 + '%',
                }}
              />
            </div>
            <span className="t-mono text-[11px] text-ink-400">
              {step} / {QUESTION_TOTAL} 질문
            </span>
          </div>

          {context?.target_title && (
            <p className="t-caption mt-3">주제 · {context.target_title}</p>
          )}

          <div className="mt-6 flex flex-col gap-5">
            {qaHistory.map((qa, i) => (
              <div key={i}>
                <div className="flex gap-3.5">
                  <span className="t-eyebrow w-7 shrink-0 pt-1">AI</span>
                  {/* 질문은 EXAONE이 생성하므로 마크다운·줄바꿈이 섞여 온다 */}
                  <p
                    className="m-0 whitespace-pre-wrap text-base leading-relaxed text-ink-900"
                    style={{ textWrap: 'pretty' }}
                  >
                    <RichText text={qa.question} />
                  </p>
                </div>

                {qa.answer && (
                  <div
                    className="ml-[42px] mt-3.5 rounded-lg px-5 py-4"
                    style={{ background: 'var(--accent-soft)' }}
                  >
                    <p className="t-caption m-0 mb-1 text-accent-ink">
                      {qa.speaker_name}
                      {qa.by_voice && ' · 음성으로 답함'}
                    </p>
                    {/* 답변은 사용자가 입력한 평문이므로 마크다운 해석 없이 줄바꿈만 보존한다 */}
                    <p className="m-0 whitespace-pre-wrap text-[15px] leading-relaxed text-ink-700">
                      {qa.answer}
                    </p>
                  </div>
                )}
              </div>
            ))}
          </div>

          {isComplete ? (
            <div
              className="mt-7 rounded-lg p-8 text-center"
              style={{ background: 'var(--positive-soft)' }}
            >
              <p className="m-0 text-xl font-semibold" style={{ color: 'var(--positive-ink)' }}>
                인터뷰가 끝났습니다
              </p>
              <p className="t-body-sm m-0 mt-2" style={{ color: 'var(--positive-ink)' }}>
                {updatedCount}개의 새로운 기억이 Memory Graph에 추가되었습니다.
              </p>
              <button
                onClick={reset}
                className="mt-5 cursor-pointer rounded bg-transparent px-5 py-2.5 text-[13px]"
                style={{
                  border: '1px solid var(--positive)',
                  color: 'var(--positive-ink)',
                }}
              >
                새 인터뷰 시작
              </button>
            </div>
          ) : (
            <div className="mt-7 pt-6" style={{ borderTop: '1px solid var(--border)' }}>
              <div className="flex items-center gap-1.5">
                <button
                  onClick={() => setMode('text')}
                  className={`tab tab-sm ${mode === 'text' ? 'tab-on' : ''}`}
                >
                  글로 답하기
                </button>
                <button
                  onClick={() => setMode('voice')}
                  className={`tab tab-sm ${mode === 'voice' ? 'tab-on' : ''}`}
                >
                  말로 답하기
                </button>
                {mode === 'voice' && <MockBadge label="녹음 목데이터" />}
              </div>

              {mode === 'voice' && (
                <div className="surface mt-4 flex items-center gap-4 px-5 py-4">
                  <button
                    onClick={toggleRecording}
                    aria-label={recording ? '녹음 중지' : '녹음 시작'}
                    className="h-10 w-10 shrink-0 cursor-pointer rounded-full text-[11px]"
                    style={{
                      border: '1px solid var(--accent)',
                      background: 'var(--accent)',
                      color: 'var(--accent-fg)',
                    }}
                  >
                    {recording ? '■' : '●'}
                  </button>
                  <div className="min-w-0 flex-1">
                    <div className="flex h-[26px] items-end gap-[2px]">
                      {MOCK_RECORDING_WAVEFORM.map((peak, i) => {
                        const active =
                          recording &&
                          i / MOCK_RECORDING_WAVEFORM.length <= (recordSec % 6) / 6
                        return (
                          <span
                            key={i}
                            className="flex-1 rounded-[1px]"
                            style={{
                              height: Math.round(peak * 100) + '%',
                              background: active ? 'var(--accent)' : 'var(--ink-200)',
                            }}
                          />
                        )
                      })}
                    </div>
                    <p className="t-caption m-0 mt-2">
                      {recording
                        ? '녹음 중 · ' +
                          recordSec.toFixed(1) +
                          '초 · 목소리 원본이 함께 보관됩니다'
                        : '누르고 말하면 목소리가 그대로 저장되고, 글로도 옮겨 적습니다'}
                    </p>
                  </div>
                </div>
              )}

              <div className="mt-4 flex gap-2">
                <input
                  type="text"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && handleAnswer()}
                  placeholder={
                    mode === 'voice'
                      ? '녹음을 멈추면 옮겨 적은 글이 들어옵니다'
                      : '답변을 입력하세요'
                  }
                  className="field flex-1"
                  disabled={loading}
                />
                <button
                  onClick={handleAnswer}
                  disabled={!input.trim() || loading}
                  className="btn-primary shrink-0"
                >
                  남기기 →
                </button>
              </div>

              {currentQuestion && (
                <p className="t-caption mt-2.5">
                  기억이 나지 않으면 “모르겠어요”라고 답해도 됩니다. 그대로 기록됩니다.
                </p>
              )}
            </div>
          )}
        </>
      )}
    </Page>
  )
}
