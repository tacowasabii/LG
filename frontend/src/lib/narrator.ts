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
 * ── 어떻게 사람 목소리에 가깝게 만드는가
 *
 * 처음에는 `ko-KR` 목소리 중 브라우저가 먼저 주는 것을 그냥 썼다. 윈도우에서는
 * 그게 SAPI5 내장 음성(Heami)이라 또박또박 읽는 기계 소리가 났다. 같은 브라우저가
 * 훨씬 사람 같은 목소리를 이미 들고 있는데도 그랬다. 그래서 세 가지를 고친다.
 *
 *   1. 목소리를 점수로 고른다 — 신경망 음성(엣지의 `Natural`, 크롬의 Google
 *      한국어)이 있으면 그것을 먼저 쓴다 (pickVoice)
 *   2. 문장 단위로 끊어 읽고 사이에 숨을 넣는다 — 한 발화로 밀어 넣으면
 *      쉼표까지 한 호흡으로 읽어 낭독이 아니라 목록 읽는 소리가 된다 (toChunks)
 *   3. 글자를 소리용으로 고친다 — `**굵게**` 표기, `이(가)` 같은 양쪽 조사,
 *      `2003-05-17` 같은 날짜는 그대로 읽으면 말이 무너진다 (toSpeech)
 *
 * 어떤 목소리가 깔려 있는지는 브라우저와 OS가 정하므로, 같은 화면이 기기마다
 * 다르게 들린다. 고를 수 있는 것 중 가장 나은 것을 고르는 것까지가 여기 몫이다.
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

/**
 * 이 목소리가 얼마나 사람 같은지 점수를 매긴다.
 *
 * 이름으로 판별하는 것이 정확하지는 않다. 규격에 "신경망인가"를 묻는 자리가
 * 없어서(SpeechSynthesisVoice는 name·lang·localService·default뿐이다) 지금
 * 브라우저들이 실제로 쓰는 이름을 보고 고른다.
 */
function voiceScore(voice: SpeechSynthesisVoice): number {
  const name = voice.name.toLowerCase()
  let score = 0

  // 엣지가 노출하는 Azure 신경망 음성 (SunHi/InJoon "Natural").
  // 지금 브라우저에서 들을 수 있는 한국어 중 가장 사람에 가깝다.
  if (name.includes('natural')) score += 50
  // 크롬의 "Google 한국의" — 서버에서 합성해 내려주는 목소리
  if (name.includes('google')) score += 35
  // macOS·iOS의 Siri 계열
  if (name.includes('yuna') || name.includes('siri')) score += 30
  // 엣지에서 신경망 음성에 함께 붙는 표기
  if (name.includes('online')) score += 20
  // 서버 합성은 대체로 신경망이다. 이름으로 못 걸러낸 것을 여기서 줍는다
  if (!voice.localService) score += 10
  // 윈도우에 기본으로 깔린 SAPI5 음성. 끊기지 않고 잘 읽지만 기계 소리가 난다
  if (name.includes('heami')) score -= 15
  // 동점이면 브라우저가 기본으로 삼은 것을 존중한다
  if (voice.default) score += 1

  return score
}

/** 한국어 목소리 중 가장 자연스러운 것을 고른다. 없으면 브라우저 기본값(null) */
function pickVoice(): SpeechSynthesisVoice | null {
  const korean = window.speechSynthesis
    .getVoices()
    .filter((v) => v.lang.toLowerCase().startsWith('ko'))
  if (korean.length === 0) return null

  return korean.reduce((best, v) => (voiceScore(v) > voiceScore(best) ? v : best))
}

/**
 * 소리로 읽을 글자로 고친다.
 *
 * 화면에 그리는 글자와 읽는 글자가 같을 수 없다. RichText가 굵게 그리는 `**`,
 * 어느 조사든 맞게 만들려고 붙인 `이(가)`, 기록에서 온 `2003-05-17`은 눈으로는
 * 읽히지만 소리로는 말이 끊기거나 기호가 그대로 읽힌다.
 */
export function toSpeech(text: string): string {
  return (text || '')
    // RichText가 그리는 표기. 소리에는 굵게가 없다
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/`([^`]+)`/g, '$1')
    // "하늘이(가) 함께했습니다" — 괄호를 읽으면 이름 뒤에서 두 번 끊긴다
    .replace(/([가-힣])\((?:이|가|은|는|을|를|와|과|로|으로|아|야)\)/g, '$1')
    // 2003-05-17 · 2003.5.17 -> 2003년 5월 17일
    .replace(
      /(\d{4})[-.](\d{1,2})[-.](\d{1,2})\.?/g,
      (_, y, m, d) => `${y}년 ${Number(m)}월 ${Number(d)}일`,
    )
    // 2003-05 -> 2003년 5월 (뒤에 날짜가 더 붙지 않을 때만)
    .replace(/(\d{4})[-.](\d{1,2})(?![-.\d])/g, (_, y, m) => `${y}년 ${Number(m)}월`)
    // 1,200 의 쉼표를 읽으면 숫자 중간에서 쉰다
    .replace(/(\d),(\d{3})/g, '$1$2')
    .replace(/[ \t]+/g, ' ')
    .replace(/\n{2,}/g, '\n')
    .trim()
}

/**
 * 한 발화가 이보다 길면 나눈다.
 *
 * 크롬에는 긴 발화가 중간에 끊기는 문제가 있고, 길이와 무관하게 한 호흡으로
 * 200자를 읽으면 낭독으로 들리지 않는다.
 */
const MAX_CHUNK = 120

/** 이보다 짧은 조각은 앞 문장에 붙인다. 한 마디만 떼어 읽으면 숨이 겉돈다 */
const MIN_CHUNK = 8

/** 문장 단위로 끊는다. 여기서 나눈 조각 사이에 숨이 들어간다 */
export function toChunks(text: string): string[] {
  const body = text.trim()
  if (!body) return []

  const chunks: string[] = []
  // 문장 부호와 뒤에 붙는 닫는 따옴표까지 한 조각으로 가져온다
  // (lookbehind를 쓰지 않는다 — 사파리 16.4 이전에 없다)
  for (const piece of body.match(/[^.!?…。\n]+[.!?…。]*[”’"')\]』」]*/g) ?? [body]) {
    const sentence = piece.trim()
    if (!sentence) continue

    const prev = chunks[chunks.length - 1]
    if (prev && (sentence.length < MIN_CHUNK || prev.length < MIN_CHUNK)) {
      chunks[chunks.length - 1] = `${prev} ${sentence}`
      continue
    }

    if (sentence.length <= MAX_CHUNK) {
      chunks.push(sentence)
      continue
    }

    // 한 문장이 너무 길면 쉼표에서 나눈다
    let buffer = ''
    for (const part of sentence.split(/\s*[,，]\s*/)) {
      if (!part) continue
      if (buffer && (buffer + part).length > MAX_CHUNK) {
        chunks.push(buffer)
        buffer = ''
      }
      buffer += (buffer ? ', ' : '') + part
    }
    if (buffer) chunks.push(buffer)
  }

  return chunks
}

/**
 * 대상 세대에 맞춘 낭독.
 *
 * film_composer.AUDIENCE_PACE가 장면 길이에 쓰는 배수와 같은 방향이다 —
 * 어르신에게는 천천히, 아이에게는 조금 빠르게. 여기서는 속도라 역수가 된다.
 *
 * 속도를 0.82까지 내려 봤더니 어르신용이 더 알아듣기 어려웠다. 브라우저 음성은
 * 많이 늦추면 음절이 늘어져 뭉개진다. 대신 문장 사이 숨(gapMs)을 길게 둔다 —
 * 한 문장을 또박또박 읽고 쉬는 쪽이 느리게 읽는 것보다 잘 들린다.
 */
export const NARRATION_PROSODY: Record<
  string,
  { rate: number; pitch: number; gapMs: number }
> = {
  child: { rate: 1.04, pitch: 1.06, gapMs: 170 },
  adult: { rate: 0.98, pitch: 1.0, gapMs: 220 },
  elder: { rate: 0.88, pitch: 0.98, gapMs: 330 },
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
  /**
   * 지금 낭독의 세대. stop()이나 새 speak()가 올린다.
   *
   * cancel()은 읽고 있던 발화의 onend·onerror를 부른다. 세대를 보지 않으면
   * 끊어 놓은 낭독의 콜백이 다음 문장을 이어 읽는다.
   */
  const generation = useRef(0)
  /** 문장 사이 숨을 재는 타이머 */
  const timer = useRef<number | null>(null)

  const clearTimer = useCallback(() => {
    if (timer.current !== null) {
      window.clearTimeout(timer.current)
      timer.current = null
    }
  }, [])

  useEffect(() => {
    if (!supported) return

    const load = () => {
      voice.current = pickVoice()
    }
    load()
    window.speechSynthesis.addEventListener('voiceschanged', load)

    return () => {
      window.speechSynthesis.removeEventListener('voiceschanged', load)
      // 화면을 떠나도 소리가 남으면 다른 화면에서 계속 들린다
      generation.current += 1
      clearTimer()
      window.speechSynthesis.cancel()
    }
  }, [supported, clearTimer])

  const stop = useCallback(() => {
    if (!supported) return
    generation.current += 1
    clearTimer()
    window.speechSynthesis.cancel()
    setSpeaking(false)
  }, [supported, clearTimer])

  const speak = useCallback(
    (text: string, options?: SpeakOptions) => {
      if (!supported) return
      const chunks = toChunks(toSpeech(text))
      if (chunks.length === 0) return

      const prosody =
        NARRATION_PROSODY[options?.audience ?? 'adult'] ?? NARRATION_PROSODY.adult

      // 겹쳐 읽으면 두 문장이 섞여 알아들을 수 없다
      generation.current += 1
      const mine = generation.current
      clearTimer()
      window.speechSynthesis.cancel()
      setSpeaking(true)

      let index = 0
      const next = () => {
        if (mine !== generation.current) return
        if (index >= chunks.length) {
          setSpeaking(false)
          return
        }
        // 목소리 목록이 이 시점에야 채워지는 브라우저가 있다
        if (!voice.current) voice.current = pickVoice()

        const utterance = new SpeechSynthesisUtterance(chunks[index])
        index += 1
        utterance.lang = 'ko-KR'
        utterance.rate = prosody.rate
        utterance.pitch = prosody.pitch
        if (voice.current) utterance.voice = voice.current

        utterance.onend = () => {
          if (mine !== generation.current) return
          timer.current = window.setTimeout(next, prosody.gapMs)
        }
        utterance.onerror = () => {
          if (mine !== generation.current) return
          setSpeaking(false)
        }
        window.speechSynthesis.speak(utterance)
      }

      // cancel() 직후에 speak()하면 첫 문장을 잃는 크롬이 있다
      timer.current = window.setTimeout(next, 60)
    },
    [supported, clearTimer],
  )

  return { speaking, supported, speak, stop }
}
