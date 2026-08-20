import { useEffect, useRef, useState } from 'react'
import {
  startInterview,
  submitInterviewAnswer,
  uploadVoice,
  InterviewStartResult,
  InterviewAnswerResult,
  mediaUrl,
} from '../lib/api'
import RichText from '../components/RichText'
import { Page, PageHeader } from '../components/Page'
import { useCurrentUser } from '../lib/currentUser'
import { Recording, VoiceRecorder, isRecordingSupported } from '../lib/recorder'
import { invalidateEvents, invalidateVoiceClips } from '../lib/useGraphData'

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
 * 녹음은 MediaRecorder로 실제 저장한다. 파형과 길이는 브라우저가 계산해 함께
 * 올리고(lib/recorder.ts), 서버는 파일과 숫자 배열만 받는다.
 *
 * 전사(음성 → 글)는 아직 없다. ASR을 붙이기 전까지는 화면이 직접 적게 하고
 * 목소리 원본을 그대로 보관한다 — 없는 기능을 있는 것처럼 보이게 하지 않는다.
 * 붙일 자리: stopRecording() 안에서 blob을 전사 API로 보내 setInput에 채운다.
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
  const { current } = useCurrentUser()
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
  /** 녹음이 끝난 뒤 답변과 함께 올릴 음성 */
  const [pending, setPending] = useState<Recording | null>(null)
  const [recordError, setRecordError] = useState<string | null>(null)
  const recorder = useRef<VoiceRecorder | null>(null)
  const canRecord = isRecordingSupported()

  // 녹음 경과 시간
  useEffect(() => {
    if (!recording) return
    const timer = window.setInterval(() => setRecordSec((s) => s + 0.1), 100)
    return () => window.clearInterval(timer)
  }, [recording])

  // 화면을 떠날 때 마이크를 놓아준다
  useEffect(() => {
    return () => {
      recorder.current?.cancel()
      recorder.current = null
    }
  }, [])

  const toggleRecording = async () => {
    setRecordError(null)

    if (recording) {
      try {
        const result = await recorder.current!.stop()
        setPending(result)
      } catch (e) {
        console.error(e)
        setRecordError('녹음을 저장하지 못했습니다.')
      } finally {
        recorder.current = null
        setRecording(false)
      }
      return
    }

    try {
      recorder.current = new VoiceRecorder()
      await recorder.current.start()
      setPending(null)
      setRecordSec(0)
      setRecording(true)
    } catch (e) {
      console.error(e)
      recorder.current = null
      setRecordError('마이크를 쓸 수 없습니다. 브라우저 권한을 확인해 주세요.')
    }
  }

  const discardRecording = () => {
    if (pending) URL.revokeObjectURL(pending.previewUrl)
    setPending(null)
    setRecordSec(0)
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
    const recorded = pending
    const byVoice = !!recorded
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
        speaker_name: current?.name,
      }
      return updated
    })

    try {
      // 음성이 있으면 먼저 올리고, 그 id를 답변에 매달아 기억의 근거로 잇는다
      let audioMediaId: string | undefined
      if (recorded) {
        try {
          const uploaded = await uploadVoice(recorded.blob, {
            durationSec: recorded.durationSec,
            waveform: recorded.waveform,
            transcript: answer,
            speakerId: current?.id,
            eventId: context?.target_id,
          })
          audioMediaId = uploaded.id
        } catch (e) {
          // 음성 업로드가 실패해도 답변 자체는 남긴다
          console.error('[interview] 음성 업로드 실패', e)
          setRecordError('음성을 저장하지 못했습니다. 글로 남긴 답변은 저장됩니다.')
        }
        URL.revokeObjectURL(recorded.previewUrl)
        setPending(null)
      }

      const result: InterviewAnswerResult = await submitInterviewAnswer(
        sessionId,
        answer,
        current?.id,
        audioMediaId,
      )
      setUpdatedCount((prev) => prev + result.updated_nodes.length)

      // 기억·음성이 늘었으니 다른 화면이 다시 받아야 한다
      invalidateEvents()
      if (audioMediaId) invalidateVoiceClips()

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
    recorder.current?.cancel()
    recorder.current = null
    if (pending) URL.revokeObjectURL(pending.previewUrl)
    setPending(null)
    setRecordError(null)
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

      {/*
        답하는 사람은 로그인한 본인이다 — 기억은 사람에게 귀속되는 데이터라서
        (기획안 08장), 다른 구성원을 골라 그 사람의 기억으로 적을 수는 없다.
      */}
      <div className="surface mt-8 px-6 py-5">
        <div className="flex flex-wrap items-center justify-between gap-5">
          <div>
            <p className="m-0 text-sm text-ink-700">
              지금 답하는 사람 · <span className="font-semibold">{current?.name ?? '—'}</span>
            </p>
            <p className="t-caption m-0 mt-[3px]">
              {current ? current.name + '님의 기억으로 저장됩니다.' : '구성원을 불러오는 중입니다.'}
            </p>
          </div>
          {/* 누를 수 없는 표시다 — .chip은 고르는 알약이라 여기 쓰지 않는다 */}
          <div
            className="flex items-center gap-1.5 rounded-full py-1 pl-1 pr-3 text-xs text-ink-500"
            style={{ border: '1px solid var(--border)' }}
          >
            {current?.thumbnail_url ? (
              <img
                src={mediaUrl(current.thumbnail_url)}
                alt=""
                className="h-5 w-5 rounded-full bg-ink-50 object-cover"
              />
            ) : (
              <span
                className="flex h-5 w-5 items-center justify-center rounded-full
                           bg-ink-50 text-[9px] text-ink-300"
              >
                {current?.name.slice(0, 1) || '·'}
              </span>
            )}
            {current?.relation ?? '—'}
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
            {current?.name ?? '지금 답하는 사람'}님의 기억으로 저장됩니다.
          </p>
          <button
            onClick={handleStart}
            disabled={loading || !current}
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
              </div>

              {mode === 'voice' && (
                <div className="surface mt-4 px-5 py-4">
                  {canRecord ? (
                    <div className="flex items-center gap-4">
                      <button
                        onClick={toggleRecording}
                        aria-label={recording ? '녹음 중지' : '녹음 시작'}
                        className="h-10 w-10 shrink-0 cursor-pointer rounded-full text-[11px]"
                        style={{
                          border: '1px solid var(--accent)',
                          background: recording ? 'var(--accent)' : 'transparent',
                          color: recording ? 'var(--accent-fg)' : 'var(--accent-ink)',
                        }}
                      >
                        {recording ? '■' : '●'}
                      </button>

                      <div className="min-w-0 flex-1">
                        {/*
                          녹음 중에는 아직 파형을 알 수 없다. 되감아 그릴 수 있는
                          것은 녹음이 끝난 뒤이므로, 진행 중에는 맥박만 보여주고
                          끝나면 실제 파형으로 바꾼다.
                        */}
                        <div className="flex h-[26px] items-end gap-[2px]">
                          {(pending?.waveform.length
                            ? pending.waveform
                            : new Array(56).fill(0.5)
                          ).map((peak: number, i: number) => {
                            const total = pending?.waveform.length || 56
                            const active = pending
                              ? true
                              : recording && i / total <= (recordSec % 3) / 3
                            return (
                              <span
                                key={i}
                                className="flex-1 rounded-[1px]"
                                style={{
                                  height:
                                    Math.round(
                                      (pending ? peak : recording ? peak * 0.6 : 0.18) * 100,
                                    ) + '%',
                                  background: active ? 'var(--accent)' : 'var(--ink-200)',
                                }}
                              />
                            )
                          })}
                        </div>

                        <p className="t-caption m-0 mt-2">
                          {recording
                            ? '녹음 중 · ' + recordSec.toFixed(1) + '초'
                            : pending
                              ? '녹음 완료 · ' +
                                pending.durationSec.toFixed(1) +
                                '초 · 답변을 남기면 목소리도 함께 저장됩니다'
                              : '누르고 말하면 목소리 원본이 그대로 보관됩니다'}
                        </p>
                      </div>
                    </div>
                  ) : (
                    <p className="t-body-sm m-0 text-ink-400">
                      이 브라우저에서는 녹음을 쓸 수 없습니다. 글로 답해 주세요.
                    </p>
                  )}

                  {pending && (
                    <div className="mt-3 flex items-center gap-3">
                      <audio src={pending.previewUrl} controls className="h-8 flex-1" />
                      <button onClick={discardRecording} className="btn-quiet shrink-0">
                        다시 녹음
                      </button>
                    </div>
                  )}

                  {recordError && (
                    <p className="t-caption m-0 mt-2" style={{ color: 'var(--critical-ink)' }}>
                      {recordError}
                    </p>
                  )}

                  <p className="t-caption m-0 mt-2">
                    말한 내용은 아래에 직접 적어 주세요. 자동 전사는 아직 붙지 않았습니다.
                  </p>
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
                      ? '말한 내용을 여기에 적어 주세요'
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
