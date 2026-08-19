/**
 * 실제 가족 음성 재생 (기획안 대표 경험 · 진정성 원칙)
 *
 * 지금은 오디오 파일이 없어서 재생을 타이머로 흉내만 낸다.
 * 실기능 개발 시 교체 지점:
 *   - useEffect의 setInterval  ->  <audio ref> 의 timeupdate 이벤트
 *   - clip.duration_sec        ->  audio.duration
 *   - 진행률 계산              ->  audio.currentTime / audio.duration
 * 레이아웃(파형·화자·출처·전사문)은 그대로 두고 재생 엔진만 바꾸면 된다.
 *
 * 전사문을 접어 두지 않는다. 목소리가 이 제품의 핵심 자산이고, 무엇을 말한
 * 기록인지 읽지 않고는 재생할 가치를 판단할 수 없다.
 *
 * AI가 만들어낸 목소리는 이 컴포넌트로 재생하지 않는다. 여기 오는 것은 언제나
 * 가족이 실제로 남긴 원본이고, 화자와 출처를 항상 함께 밝힌다.
 */

import { useEffect, useRef, useState } from 'react'
import { VoiceClip, VOICE_SOURCE_LABEL } from '../mock/voice'

interface Props {
  clip: VoiceClip
  /** TV 화면처럼 어두운 배경에 올릴 때 */
  dark?: boolean
  /** 채팅 답변·인물 상세처럼 다른 내용 사이에 끼울 때 한 단계 작게 */
  compact?: boolean
}

export default function AudioClip({ clip, dark = false, compact = false }: Props) {
  const [playing, setPlaying] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const timer = useRef<number | null>(null)

  useEffect(() => {
    if (!playing) return

    timer.current = window.setInterval(() => {
      setElapsed((prev) => {
        const next = prev + 0.1
        if (next >= clip.duration_sec) {
          setPlaying(false)
          return clip.duration_sec
        }
        return next
      })
    }, 100)

    return () => {
      if (timer.current) window.clearInterval(timer.current)
    }
  }, [playing, clip.duration_sec])

  // 다른 클립으로 바뀌면 처음부터
  useEffect(() => {
    setPlaying(false)
    setElapsed(0)
  }, [clip.id])

  const toggle = () => {
    if (elapsed >= clip.duration_sec) setElapsed(0)
    setPlaying((p) => !p)
  }

  const progress = clip.duration_sec > 0 ? elapsed / clip.duration_sec : 0
  const btn = compact ? 30 : 34

  return (
    <div
      className="rounded-lg p-4"
      style={
        dark
          ? { background: 'rgba(250,250,247,0.08)' }
          : {
              background: 'var(--paper-pure)',
              border: '1px solid var(--border)',
              padding: compact ? '14px 16px' : 20,
            }
      }
    >
      <div className="flex items-center gap-3">
        <button
          onClick={toggle}
          aria-label={playing ? '일시정지' : '재생'}
          className="shrink-0 cursor-pointer rounded-full leading-none"
          style={{
            width: btn,
            height: btn,
            fontSize: compact ? 10 : 11,
            border: '1px solid var(--accent)',
            background: playing ? 'var(--accent)' : 'transparent',
            color: playing ? 'var(--accent-fg)' : 'var(--accent-ink)',
          }}
        >
          {playing ? '■' : '▶'}
        </button>

        <div className="min-w-0 flex-1">
          <p
            className="m-0 text-[13px] font-semibold"
            style={{ color: dark ? 'var(--accent-ink)' : 'var(--ink-700)' }}
          >
            {clip.speaker_name}
            <span
              className="t-mono ml-2 text-[11px] font-normal"
              style={{ color: dark ? 'rgba(250,250,247,0.45)' : 'var(--ink-300)' }}
            >
              {clip.duration_sec}초
            </span>
          </p>
          <p
            className="t-caption m-0 mt-0.5"
            style={{ color: dark ? 'rgba(250,250,247,0.5)' : 'var(--ink-300)' }}
          >
            {clip.event_title} · {VOICE_SOURCE_LABEL[clip.source]} · {clip.recorded_at} 녹음
          </p>
        </div>
      </div>

      {/*
        파형은 진행률까지만 강조색으로 채운다. 재생 위치를 별도의 재생 헤드로
        표시하지 않는 편이 조각이 작아졌을 때 훨씬 잘 읽힌다.
      */}
      <div
        className="mt-3.5 flex items-end gap-[2px]"
        style={{ height: compact ? 22 : 30 }}
      >
        {clip.waveform.map((peak, i) => {
          const played = i / clip.waveform.length <= progress
          return (
            <span
              key={i}
              className="flex-1 rounded-[1px]"
              style={{
                height: Math.round(peak * 100) + '%',
                background: played
                  ? 'var(--accent)'
                  : dark
                    ? 'rgba(250,250,247,0.25)'
                    : 'var(--ink-200)',
              }}
            />
          )
        })}
      </div>

      <p
        className="t-body-sm m-0 mt-3.5"
        style={{
          color: dark ? 'rgba(250,250,247,0.8)' : 'var(--ink-500)',
          textWrap: 'pretty',
        }}
      >
        {clip.transcript}
      </p>
    </div>
  )
}
