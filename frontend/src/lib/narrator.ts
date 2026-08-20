/**
 * 내레이션을 소리로 읽는다 (브라우저 speechSynthesis)
 *
 * Memory Film과 TV의 내레이션은 글로만 나왔다. 거실에서 3m 떨어져 보는 화면에서
 * 글을 읽게 만드는 것은 그 화면이 하려는 일과 어긋난다.
 *
 * TTS API 키는 없다. 브라우저가 이미 목소리를 들고 있으므로 그것을 쓴다 —
 * 파형(lib/recorder)·전사(lib/transcriber)·영상 정보(lib/videoMeta)와 같은
 * 분업이다. 서버는 글자만 내려보낸다.
 *
 * ── 지켜야 하는 선 하나
 *
 * 이 목소리를 가족 목소리처럼 들리게 하면 안 된다. AudioClip이 정한 경계다 —
 * 거기 오는 것은 언제나 가족이 실제로 남긴 원본이고, 합성 목소리는 그 컴포넌트로
 * 재생하지 않는다. 그래서 여기서 만든 소리는
 *
 *   - AudioClip을 거치지 않는다 (파형·화자·전사문 UI를 쓰지 않는다)
 *   - 화면이 "AI 음성"이라고 밝힌 자리에서만 난다
 *   - 가족 음성 재생과 동시에 겹치지 않는다 (부르는 쪽이 멈춘다)
 *
 * ── 브라우저 사정
 *
 * getVoices()는 처음에 빈 배열을 준다. 목소리 목록이 비동기로 오므로
 * `voiceschanged`를 기다려야 한국어 목소리를 고를 수 있다.
 *
 * 소리는 사용자 동작 없이 시작할 수 없다(자동재생 정책). 부르는 쪽이 버튼이나
 * 리모컨 입력에 묶어야 한다.
 *
 * 실기능 확장 지점:
 *   서버 TTS(더 자연스러운 한국어 음성)를 붙이면 speak()가 오디오 파일을 받아
 *   재생하는 형태가 된다. 화면 쪽 계약(speak/stop/speaking)은 그대로 쓴다.
 */

import { useCallback, useEffect, useRef, useState } from 'react'

export function isNarrationSupported(): boolean {
  return typeof window !== 'undefined' && 'speechSynthesis' in window
}

/** 한국어 목소리를 고른다. 없으면 브라우저 기본값(null)에 맡긴다 */
function pickKoreanVoice(): SpeechSynthesisVoice | null {
  const voices = window.speechSynthesis.getVoices()
  if (voices.length === 0) return null
  return (
    voices.find((v) => v.lang === 'ko-KR') ??
    voices.find((v) => v.lang.startsWith('ko')) ??
    null
  )
}

/**
 * 대상 세대에 맞춘 낭독 속도.
 *
 * film_composer.AUDIENCE_PACE가 장면 길이에 쓰는 배수와 같은 방향이다 —
 * 어르신에게는 천천히, 아이에게는 조금 빠르게. 여기서는 속도라 역수가 된다.
 */
export const NARRATION_RATE: Record<string, number> = {
  child: 1.05,
  adult: 0.95,
  elder: 0.82,
}

interface SpeakOptions {
  /** 'child' | 'adult' | 'elder'. 없으면 adult */
  audience?: string
}

export interface Narrator {
  /** 지금 읽고 있는가 */
  speaking: boolean
  /** 이 브라우저에서 쓸 수 있는가 */
  supported: boolean
  /** 읽기 시작한다. 이미 읽고 있으면 그것을 끊고 새로 읽는다 */
  speak: (text: string, options?: SpeakOptions) => void
  /** 멈춘다 (남은 문장을 버린다) */
  stop: () => void
}

export function useNarrator(): Narrator {
  const supported = isNarrationSupported()
  const [speaking, setSpeaking] = useState(false)
  /** 목소리 목록이 늦게 오므로 준비되면 여기에 담는다 */
  const voice = useRef<SpeechSynthesisVoice | null>(null)

  useEffect(() => {
    if (!supported) return

    const load = () => {
      voice.current = pickKoreanVoice()
    }
    load()
    window.speechSynthesis.addEventListener('voiceschanged', load)

    return () => {
      window.speechSynthesis.removeEventListener('voiceschanged', load)
      // 화면을 떠나도 소리가 남으면 다른 화면에서 계속 들린다
      window.speechSynthesis.cancel()
    }
  }, [supported])

  const stop = useCallback(() => {
    if (!supported) return
    window.speechSynthesis.cancel()
    setSpeaking(false)
  }, [supported])

  const speak = useCallback(
    (text: string, options?: SpeakOptions) => {
      if (!supported) return
      const body = (text || '').trim()
      if (!body) return

      // 겹쳐 읽으면 두 문장이 섞여 알아들을 수 없다
      window.speechSynthesis.cancel()

      const utterance = new SpeechSynthesisUtterance(body)
      utterance.lang = 'ko-KR'
      utterance.rate = NARRATION_RATE[options?.audience ?? 'adult'] ?? 0.95
      if (voice.current) utterance.voice = voice.current

      utterance.onend = () => setSpeaking(false)
      utterance.onerror = () => setSpeaking(false)

      setSpeaking(true)
      window.speechSynthesis.speak(utterance)
    },
    [supported],
  )

  return { speaking, supported, speak, stop }
}
