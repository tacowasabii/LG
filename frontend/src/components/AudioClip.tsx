/**
 * 실제 가족 음성 재생 (기획안 대표 경험 · 진정성 원칙)
 *
 * clip.file_path가 있으면 실제 파일을 재생한다. 없으면 진행만 흉내 낸다 —
 * 파일이 지워졌거나 아직 업로드되지 않은 클립에서도 조판이 흔들리지 않게 한다.
 *
 * 전사문을 접어 두지 않는다. 목소리가 이 제품의 핵심 자산이고, 무엇을 말한
 * 기록인지 읽지 않고는 재생할 가치를 판단할 수 없다. 인터뷰 녹음은 그 답을 부른
 * 질문도 함께 밝힌다 — 답만 있으면 "모르겠어요" 한 마디는 읽을 수 없다.
 *
 * AI가 만들어낸 목소리는 이 컴포넌트로 재생하지 않는다. 여기 오는 것은 언제나
 * 가족이 실제로 남긴 원본이고, 화자와 출처를 항상 함께 밝힌다.
 */

import { useEffect, useRef, useState } from 'react'
import { VoiceClip, mediaUrl } from '../lib/api'

/** 기록이 어디서 왔는지 — 서버의 source 값을 사람 말로 */
const SOURCE_LABEL: Record<string, string> = {
  interview: 'AI 인터뷰 녹음',
  ai_stt: '음성 메모',
  home_video: '홈비디오 음성',
  voice_memo: '음성 메모',
  user_input: '가족이 올린 음성',
}

interface Props {
  clip: VoiceClip & { source?: string }
  /** TV 화면처럼 어두운 배경에 올릴 때 */
  dark?: boolean
  /** 채팅 답변·인물 상세처럼 다른 내용 사이에 끼울 때 한 단계 작게 */
  compact?: boolean
  /**
   * 이 목소리가 나기 시작했는지·멈췄는지 알린다.
   *
   * Memory Film이 배경 음악을 낮추는 데 쓴다. 가족의 목소리를 앱이 만든 소리가
   * 덮으면, 이 제품에서 가장 중요한 자산을 우리가 가린 셈이 된다. 재생 상태는
   * 이 컴포넌트만 알고 있어서(오디오 요소가 여기 있다) 밖으로 알려 준다.
   */
  onPlayingChange?: (playing: boolean) => void
}

export default function AudioClip({
  clip,
  dark = false,
  compact = false,
  onPlayingChange,
}: Props) {
  const [playing, setPlaying] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const [failed, setFailed] = useState(false)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const timer = useRef<number | null>(null)

  // 파일이 있으면 실제 재생, 없으면 진행만 흉내 낸다
  const src = clip.file_path && !failed ? mediaUrl(clip.file_path) : null
  const simulated = !src

  // 길이는 파일에서 읽은 값이 가장 정확하다. 없으면 서버가 준 값을 쓴다.
  const [duration, setDuration] = useState(clip.duration_sec || 0)

  useEffect(() => {
    setPlaying(false)
    setElapsed(0)
    setFailed(false)
    setDuration(clip.duration_sec || 0)
  }, [clip.id, clip.duration_sec])

  // 재생 상태를 밖으로 알린다 (배경 음악을 낮추는 쪽이 듣는다)
  useEffect(() => {
    onPlayingChange?.(playing)
    // onPlayingChange를 의존성에 넣지 않는다. 부르는 쪽이 인라인 함수를 넘기면
    // 매 렌더마다 다시 돌아, 재생 중이 아닌데도 계속 알리게 된다.
  }, [playing])

  // 화면에서 사라질 때는 소리도 사라진다 (오디오 요소가 함께 없어진다).
  // 알리지 않으면 듣는 쪽이 낮춘 음량을 그대로 들고 있게 된다.
  useEffect(() => {
    return () => onPlayingChange?.(false)
  }, [])

  // 흉내 재생 타이머 (파일이 없는 클립에서만 돈다)
  useEffect(() => {
    if (!playing || !simulated) return

    timer.current = window.setInterval(() => {
      setElapsed((prev) => {
        const next = prev + 0.1
        if (next >= duration) {
          setPlaying(false)
          return duration
        }
        return next
      })
    }, 100)

    return () => {
      if (timer.current) window.clearInterval(timer.current)
    }
  }, [playing, simulated, duration])

  const toggle = () => {
    const audio = audioRef.current

    if (simulated || !audio) {
      if (elapsed >= duration) setElapsed(0)
      setPlaying((p) => !p)
      return
    }

    if (playing) {
      audio.pause()
      return
    }
    if (audio.ended) audio.currentTime = 0
    void audio.play().catch((e) => {
      console.warn('[audio] 재생하지 못했습니다', e)
      setFailed(true)
    })
  }

  const progress = duration > 0 ? Math.min(1, elapsed / duration) : 0
  const btn = compact ? 30 : 34

  // 파형이 없는 클립(파형 계산 실패)에서도 자리가 비지 않게 한다
  const bars = clip.waveform.length > 0 ? clip.waveform : new Array(56).fill(0.18)

  const sourceLabel = clip.source ? SOURCE_LABEL[clip.source] : null
  const meta = [clip.event_title, sourceLabel, clip.recorded_at ? clip.recorded_at + ' 녹음' : null]
    .filter(Boolean)
    .join(' · ')

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
      {src && (
        <audio
          ref={audioRef}
          src={src}
          preload="metadata"
          onPlay={() => setPlaying(true)}
          onPause={() => setPlaying(false)}
          onEnded={() => setPlaying(false)}
          onTimeUpdate={(e) => setElapsed(e.currentTarget.currentTime)}
          onLoadedMetadata={(e) => {
            const value = e.currentTarget.duration
            // webm 녹음은 duration이 Infinity로 오는 브라우저가 있다
            if (Number.isFinite(value) && value > 0) setDuration(value)
          }}
          onError={() => setFailed(true)}
        />
      )}

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
            {clip.speaker_name || '가족'}
            <span
              className="t-mono ml-2 text-[11px] font-normal"
              style={{ color: dark ? 'rgba(250,250,247,0.45)' : 'var(--ink-300)' }}
            >
              {Math.round(duration)}초
            </span>
          </p>
          {meta && (
            <p
              className="t-caption m-0 mt-0.5"
              style={{ color: dark ? 'rgba(250,250,247,0.5)' : 'var(--ink-300)' }}
            >
              {meta}
            </p>
          )}
        </div>
      </div>

      {/*
        파형은 진행률까지만 강조색으로 채운다. 재생 위치를 별도의 재생 헤드로
        표시하지 않는 편이 조각이 작아졌을 때 훨씬 잘 읽힌다.
      */}
      <div className="mt-3.5 flex items-end gap-[2px]" style={{ height: compact ? 22 : 30 }}>
        {bars.map((peak, i) => {
          const played = i / bars.length <= progress
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

      {/*
        무슨 질문에 답한 목소리인지. 답만 보여주면 "모르겠어요" 한 마디가 무슨
        이야기인지 읽을 수 없다 — 채팅 답변 아래 붙는 클립에서 특히 그렇다.
        답보다 앞에 두고 한 단계 여리게 둔다. 이 자리의 주인은 가족의 말이다.
      */}
      {clip.question && (
        <p
          className="t-caption m-0 mt-3.5"
          style={{
            color: dark ? 'rgba(250,250,247,0.5)' : 'var(--ink-300)',
            textWrap: 'pretty',
          }}
        >
          질문 “{clip.question}”
        </p>
      )}

      {clip.transcript ? (
        <>
          <p
            className={`t-body-sm m-0 ${clip.question ? 'mt-1.5' : 'mt-3.5'}`}
            style={{
              color: dark ? 'rgba(250,250,247,0.8)' : 'var(--ink-500)',
              textWrap: 'pretty',
            }}
          >
            {clip.transcript}
          </p>
          {/* 목소리는 가족이 남긴 것이지만 글은 기계가 옮겼을 수 있다. 어느
              쪽인지 밝히지 않으면 잘못 들은 문장이 가족의 말로 읽힌다. */}
          {clip.transcript_source === 'ai_stt' && (
            <p
              className="t-caption m-0 mt-1.5"
              style={{ color: dark ? 'rgba(250,250,247,0.45)' : 'var(--ink-300)' }}
            >
              AI가 옮긴 글입니다. 목소리가 원본입니다.
            </p>
          )}
        </>
      ) : (
        <p
          className={`t-caption m-0 ${clip.question ? 'mt-1.5' : 'mt-3.5'}`}
          style={{ color: dark ? 'rgba(250,250,247,0.45)' : 'var(--ink-300)' }}
        >
          아직 글로 옮기지 않았습니다. 목소리는 그대로 남아 있습니다.
        </p>
      )}

      {failed && (
        <p className="t-caption m-0 mt-2" style={{ color: 'var(--critical-ink)' }}>
          음성 파일을 불러오지 못했습니다.
        </p>
      )}
    </div>
  )
}
