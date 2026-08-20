/**
 * Memory Film 배경 음악 — 브라우저에서 만든다 (Web Audio)
 *
 * 음원 파일이 없다. 음악 생성 API 키도 없다. 그런데 브라우저는 이미 소리를 만들
 * 수 있으므로 그것을 쓴다 — narrator(speechSynthesis)·recorder·transcriber·
 * videoMeta와 같은 분업이다. 서버는 무드 이름만 내려보낸다.
 *
 * 무엇을 깔지는 서버가 정한다 (backend/services/film_music.py). 여기서 고르면
 * 화면에 적힌 근거와 실제로 나는 소리가 갈라진다 — 카메라 움직임에서 정확히 그
 * 실수를 했다. 무드는 목록 순서가 아니라 열쇠로 찾는다 (MOODS[mood]). 순서로
 * 찾으면 한쪽에 무드를 더하는 순간 전부 어긋난다.
 *
 * ── 지켜야 하는 선
 *
 * 이 소리를 가족의 기록처럼 들리게 하면 안 된다. AudioClip이 정한 경계와 같다.
 *
 *   - 앱이 만든 소리라는 것을 화면이 밝힌다 (FilmPage의 배경 음악 줄)
 *   - 가족의 목소리·낭독이 나는 동안에는 음량을 내린다 (duck). 배경 음악이
 *     할머니 목소리를 덮으면, 이 제품에서 가장 중요한 자산을 우리가 가린 셈이다
 *   - 사용자가 끌 수 있다. 켜고 끄는 것은 화면의 몫이다
 *
 * ── 어떻게 만드는가
 *
 * 무드마다 코드 진행(3성 패드)과 벨이 고를 음(펜타토닉)을 정해 두었다. 패드는
 * 사인+트라이앵글을 겹쳐 느리게 열고 닫고, 벨은 정해진 순서로 음을 하나씩 놓는다.
 * 무작위를 쓰지 않는다 — 같은 사건이 열 때마다 다르게 들리면 그 음악은 이 사건의
 * 것이 아니다 (motion_prompt를 LLM에 맡기지 않는 것과 같은 이유다).
 *
 * 소리는 사용자 동작 없이 시작할 수 없다(자동재생 정책). start()를 버튼 클릭
 * 안에서 불러야 한다. 멈추는 것은 아무 데서나 된다.
 */

import { useCallback, useEffect, useRef } from 'react'

/** 서버가 모르는 무드를 보내도 소리는 나야 한다 */
const FALLBACK_MOOD = 'calm'

/** 미리 채워 두는 시간. 이만큼 앞의 음까지 예약한다 (초) */
const LOOKAHEAD = 1.5
/** 예약하러 깨어나는 주기 (ms). LOOKAHEAD보다 충분히 짧아야 음이 빠지지 않는다 */
const TICK_MS = 250

/** 켜질 때·꺼질 때 음량이 오르내리는 시간 (초). 갑자기 끊으면 딸깍 소리가 난다 */
const FADE_IN = 2.0
const FADE_OUT = 1.2

/** 기본 음량과, 목소리가 날 때 내려가는 비율 */
const BASE_GAIN = 0.8
const DUCK_RATIO = 0.22

/** 코드가 다음 코드와 겹쳐 있는 시간 (초). 사이가 벌어지면 배경이 아니라 끊긴다 */
const PAD_TAIL = 2.6
/** 벨 한 음이 사라지기까지 (초) */
const BELL_DECAY = 3.2

/**
 * pace가 들어올 수 있는 범위. 서버가 주는 값이라(AUDIENCE_PACE) 지금은 0.75~1.35
 * 뿐이지만, 네트워크로 오는 값을 그대로 곱하면 0이 왔을 때 음 간격이 0이 되어
 * 예약 루프가 끝나지 않는다.
 */
function safePace(pace: number): number {
  if (!Number.isFinite(pace) || pace <= 0) return 1
  return Math.min(3, Math.max(0.3, pace))
}

interface MoodSpec {
  /** 코드 진행. 각 코드는 울릴 MIDI 음 세 개 */
  chords: number[][]
  /** 한 코드가 머무는 시간 (초). pace가 곱해진다 */
  chordSec: number
  /** 벨이 고를 음 (MIDI). 무드의 음계다 */
  bells: number[]
  /** bells의 몇 번째를 어떤 순서로 놓을지. 무작위를 쓰지 않는다 */
  bellPattern: number[]
  /** 벨 음 사이의 간격 (초). pace가 곱해진다 */
  bellStep: number
  /** 로우패스 차단 주파수 (Hz). 낮추면 어두워진다 */
  cutoff: number
  /** 패드 한 음의 최대 음량 */
  padGain: number
  /** 벨 한 음의 최대 음량 */
  bellGain: number
}

/**
 * 무드별 음악. 열쇠는 서버의 film_music.MOOD_LABEL과 같다.
 *
 * 음은 MIDI 번호다 (60 = C4). 코드는 근음·5도·3도를 벌려 잡았다 — 좁게 쌓으면
 * 배경이 아니라 화음이 앞에 나선다. 벨은 펜타토닉만 쓴다. 5음계는 어떤 순서로
 * 놓아도 어긋나는 음이 없어서, 정해진 순서를 그냥 돌려도 음악으로 들린다.
 */
const MOODS: Record<string, MoodSpec> = {
  // F major — I vi IV V. 모여서 기리는 자리
  warm: {
    chords: [
      [53, 60, 69], // F3 C4 A4
      [50, 57, 65], // D3 A3 F4
      [58, 65, 74], // Bb3 F4 D5
      [48, 64, 67], // C3 E4 G4
    ],
    chordSec: 7,
    bells: [65, 67, 69, 72, 74, 77], // F major pentatonic
    bellPattern: [0, 2, 3, 1, 4, 2, 5, 3],
    bellStep: 1.6,
    cutoff: 2000,
    padGain: 0.055,
    bellGain: 0.075,
  },

  // D minor — i VI III v. 한 세대가 지난 기록
  nostalgic: {
    chords: [
      [50, 57, 65], // D3 A3 F4
      [58, 65, 74], // Bb3 F4 D5
      [53, 60, 69], // F3 C4 A4
      [57, 64, 72], // A3 E4 C5
    ],
    chordSec: 8,
    bells: [62, 65, 67, 69, 72, 74], // D minor pentatonic
    bellPattern: [0, 3, 2, 4, 1, 3],
    bellStep: 2.2,
    cutoff: 1500,
    padGain: 0.055,
    bellGain: 0.07,
  },

  // G major — I V vi IV. 아이·학교·놀이의 자리
  bright: {
    chords: [
      [55, 62, 71], // G3 D4 B4
      [50, 57, 66], // D3 A3 F#4
      [52, 59, 67], // E3 B3 G4
      [48, 55, 64], // C3 G3 E4
    ],
    chordSec: 6,
    bells: [67, 69, 71, 74, 76, 79], // G major pentatonic
    bellPattern: [0, 2, 4, 3, 5, 2, 1, 3],
    bellStep: 1.2,
    cutoff: 2600,
    padGain: 0.05,
    bellGain: 0.085,
  },

  // C major — I vi IV V, 아주 느리게. 이야기를 방해하지 않는 소리
  calm: {
    chords: [
      [48, 55, 64], // C3 G3 E4
      [57, 64, 72], // A3 E4 C5
      [53, 60, 69], // F3 C4 A4
      [55, 62, 71], // G3 D4 B4
    ],
    chordSec: 9,
    bells: [60, 62, 64, 67, 69, 72], // C major pentatonic
    bellPattern: [0, 2, 4, 1, 3, 5],
    bellStep: 2.6,
    cutoff: 1800,
    padGain: 0.055,
    bellGain: 0.065,
  },

  // A minor — i iv v i. 낮게, 느리게, 벨은 아주 드물게
  solemn: {
    chords: [
      [45, 52, 60], // A2 E3 C4
      [50, 57, 65], // D3 A3 F4
      [52, 59, 67], // E3 B3 G4
      [45, 52, 60], // A2 E3 C4
    ],
    chordSec: 10,
    bells: [57, 60, 62, 64, 67], // A minor pentatonic
    bellPattern: [0, 2, 1, 3],
    bellStep: 3.4,
    cutoff: 1100,
    padGain: 0.065,
    bellGain: 0.045,
  },
}

type AudioContextCtor = typeof AudioContext

function audioContextCtor(): AudioContextCtor | null {
  if (typeof window === 'undefined') return null
  const w = window as unknown as {
    AudioContext?: AudioContextCtor
    webkitAudioContext?: AudioContextCtor
  }
  return w.AudioContext ?? w.webkitAudioContext ?? null
}

export function isFilmMusicSupported(): boolean {
  return audioContextCtor() !== null
}

/** MIDI 번호를 주파수로 (69 = A4 = 440Hz) */
function midiToFreq(midi: number): number {
  return 440 * Math.pow(2, (midi - 69) / 12)
}

/**
 * 소리를 내는 쪽. 화면 상태와 떨어뜨려 둔다 — 오디오 시계는 React 렌더와 다른
 * 시계로 돌고, 음을 예약하는 일에 렌더 주기가 끼면 음이 밀리거나 빠진다.
 */
class FilmMusicEngine {
  private ctx: AudioContext | null = null

  /** 이번 재생의 노드들. 멈출 때 끊는다 */
  private master: GainNode | null = null
  private filter: BiquadFilterNode | null = null
  private send: GainNode | null = null
  private tail: AudioNode[] = []

  private spec: MoodSpec = MOODS[FALLBACK_MOOD]
  private chordSec = MOODS[FALLBACK_MOOD].chordSec
  private bellStep = MOODS[FALLBACK_MOOD].bellStep

  /** 다음 음을 놓을 시각 (AudioContext 시계) */
  private chordAt = 0
  private bellAt = 0
  private chordIndex = 0
  private bellIndex = 0

  private timer: number | null = null
  private suspendTimer: number | null = null
  private ducked = false

  /** 지금 소리를 내고 있는가 (예약이 돌고 있는가) */
  get running(): boolean {
    return this.timer !== null
  }

  /**
   * 재생을 시작한다. 반드시 사용자 동작(클릭) 안에서 불러야 한다 — 그러지 않으면
   * 브라우저가 AudioContext를 열어 주지 않는다.
   */
  start(mood: string, pace = 1): void {
    const Ctor = audioContextCtor()
    if (!Ctor) return

    if (!this.ctx) this.ctx = new Ctor()
    const ctx = this.ctx

    // 꺼지는 중이었다면 그 예약을 거둔다. 새로 시작한 소리를 뒤늦게 멈춘다.
    if (this.suspendTimer !== null) {
      window.clearTimeout(this.suspendTimer)
      this.suspendTimer = null
    }
    if (this.timer !== null) {
      window.clearInterval(this.timer)
      this.timer = null
    }
    this.teardown()
    void ctx.resume()

    this.spec = MOODS[mood] ?? MOODS[FALLBACK_MOOD]
    // 장면이 느려지면 음악도 느려진다 (서버의 AUDIENCE_PACE를 그대로 받는다)
    const rate = safePace(pace)
    this.chordSec = this.spec.chordSec * rate
    this.bellStep = this.spec.bellStep * rate

    const master = ctx.createGain()
    // 이미 낮추라는 요청을 받은 상태라면 낮은 음량으로 올라온다. 목소리가 나는
    // 동안 재생을 시작하면 배경 음악이 그 목소리 위로 올라오게 된다.
    const target = this.ducked ? BASE_GAIN * DUCK_RATIO : BASE_GAIN
    master.gain.setValueAtTime(0.0001, ctx.currentTime)
    master.gain.linearRampToValueAtTime(target, ctx.currentTime + FADE_IN)
    master.connect(ctx.destination)

    // 오실레이터의 높은 배음을 깎는다. 이것 없이는 트라이앵글이 날카롭다.
    const filter = ctx.createBiquadFilter()
    filter.type = 'lowpass'
    filter.frequency.value = this.spec.cutoff
    filter.Q.value = 0.7
    filter.connect(master)

    // 벨에만 걸리는 공간감. 좌우로 번갈아 되울린다 (핑퐁 딜레이).
    const send = ctx.createGain()
    send.gain.value = 0.5
    const left = ctx.createDelay(1)
    left.delayTime.value = 0.33
    const right = ctx.createDelay(1)
    right.delayTime.value = 0.47
    const feedback = ctx.createGain()
    feedback.gain.value = 0.3
    const panLeft = ctx.createStereoPanner()
    panLeft.pan.value = -0.55
    const panRight = ctx.createStereoPanner()
    panRight.pan.value = 0.55

    send.connect(left)
    left.connect(panLeft)
    panLeft.connect(filter)
    left.connect(right)
    right.connect(panRight)
    panRight.connect(filter)
    right.connect(feedback)
    feedback.connect(left)

    this.master = master
    this.filter = filter
    this.send = send
    this.tail = [left, right, feedback, panLeft, panRight]

    this.chordAt = ctx.currentTime + 0.12
    // 벨은 패드가 자리를 잡은 뒤에 들어온다. 같이 시작하면 첫 음이 튄다.
    this.bellAt = ctx.currentTime + 1.4
    this.chordIndex = 0
    this.bellIndex = 0

    this.schedule()
    this.timer = window.setInterval(() => this.schedule(), TICK_MS)
  }

  /** 서서히 사라지게 하고 멈춘다 */
  stop(): void {
    if (this.timer !== null) {
      window.clearInterval(this.timer)
      this.timer = null
    }

    const ctx = this.ctx
    const master = this.master
    if (!ctx || !master) return

    const now = ctx.currentTime
    master.gain.cancelScheduledValues(now)
    master.gain.setValueAtTime(Math.max(master.gain.value, 0.0001), now)
    master.gain.linearRampToValueAtTime(0.0001, now + FADE_OUT)

    // 사라진 뒤에 멈춘다. 바로 suspend하면 페이드가 잘려 딸깍 소리로 끝난다.
    if (this.suspendTimer !== null) window.clearTimeout(this.suspendTimer)
    this.suspendTimer = window.setTimeout(
      () => {
        this.suspendTimer = null
        this.teardown()
        void this.ctx?.suspend()
      },
      (FADE_OUT + 0.2) * 1000,
    )
  }

  /**
   * 가족의 목소리·낭독이 나는 동안 음량을 내린다.
   *
   * 멈추지 않고 낮추는 이유는, 목소리 한 마디마다 음악이 꺼졌다 켜지면 그 편집이
   * 목소리보다 더 들리기 때문이다. 내릴 때는 빠르게(목소리를 덮지 않게), 올릴
   * 때는 느리게 되돌린다.
   */
  duck(on: boolean): void {
    this.ducked = on

    const ctx = this.ctx
    const master = this.master
    // 재생 중이 아니면 기억만 해 둔다. 다음 start()가 이 상태로 올라온다.
    if (!ctx || !master || !this.running) return

    const now = ctx.currentTime
    const target = on ? BASE_GAIN * DUCK_RATIO : BASE_GAIN
    master.gain.cancelScheduledValues(now)
    master.gain.setValueAtTime(master.gain.value, now)
    master.gain.linearRampToValueAtTime(target, now + (on ? 0.35 : 0.9))
  }

  /** 화면을 떠날 때. 열어 둔 AudioContext까지 닫는다 */
  dispose(): void {
    if (this.timer !== null) {
      window.clearInterval(this.timer)
      this.timer = null
    }
    if (this.suspendTimer !== null) {
      window.clearTimeout(this.suspendTimer)
      this.suspendTimer = null
    }
    this.teardown()
    void this.ctx?.close()
    this.ctx = null
  }

  /** 이번 재생의 노드를 끊는다. 예약된 음은 갈 곳이 없어져 소리가 나지 않는다 */
  private teardown(): void {
    this.master?.disconnect()
    this.filter?.disconnect()
    this.send?.disconnect()
    for (const node of this.tail) node.disconnect()
    this.master = null
    this.filter = null
    this.send = null
    this.tail = []
  }

  /**
   * LOOKAHEAD 앞까지의 음을 예약한다.
   *
   * setInterval로 음을 "그때그때" 내면 타이머가 밀리는 만큼 음이 밀린다. 브라우저
   * 타이머는 탭이 가려지면 느려지기까지 한다. 그래서 타이머는 예약만 하고, 시각은
   * 오디오 시계로 정한다.
   */
  private schedule(): void {
    const ctx = this.ctx
    if (!ctx || !this.filter) return

    const horizon = ctx.currentTime + LOOKAHEAD
    const spec = this.spec

    while (this.chordAt < horizon) {
      const chord = spec.chords[this.chordIndex % spec.chords.length]
      // 다음 코드와 겹치게 길게 끈다. 사이가 벌어지면 한 덩이씩 끊겨 들린다.
      const hold = this.chordSec + PAD_TAIL
      for (const midi of chord) this.pad(midiToFreq(midi), this.chordAt, hold, spec.padGain)
      this.chordIndex += 1
      this.chordAt += this.chordSec
    }

    while (this.bellAt < horizon) {
      const note = spec.bells[spec.bellPattern[this.bellIndex % spec.bellPattern.length]]
      this.bell(midiToFreq(note), this.bellAt, spec.bellGain)
      this.bellIndex += 1
      this.bellAt += this.bellStep
    }
  }

  /** 패드 한 음 — 사인에 트라이앵글을 살짝 얹어 느리게 열고 닫는다 */
  private pad(freq: number, start: number, hold: number, peak: number): void {
    const ctx = this.ctx
    const dest = this.filter
    if (!ctx || !dest) return

    const attack = Math.min(2.2, hold * 0.35)
    const release = Math.min(2.8, hold * 0.45)

    const gain = ctx.createGain()
    gain.gain.setValueAtTime(0.0001, start)
    gain.gain.linearRampToValueAtTime(peak, start + attack)
    gain.gain.setValueAtTime(peak, start + hold - release)
    gain.gain.linearRampToValueAtTime(0.0001, start + hold)
    gain.connect(dest)

    const body = ctx.createOscillator()
    body.type = 'sine'
    body.frequency.value = freq
    body.connect(gain)

    // 조금 어긋나게 겹친 트라이앵글. 사인 하나만으로는 소리에 표면이 없다.
    const air = ctx.createOscillator()
    air.type = 'triangle'
    air.frequency.value = freq
    air.detune.value = 7
    const airGain = ctx.createGain()
    airGain.gain.value = 0.3
    air.connect(airGain)
    airGain.connect(gain)

    const end = start + hold + 0.05
    body.start(start)
    air.start(start)
    body.stop(end)
    air.stop(end)
    // 끝난 노드를 끊는다. 30초 이야기에 수백 개가 쌓이게 두지 않는다.
    body.onended = () => {
      gain.disconnect()
      airGain.disconnect()
    }
  }

  /** 벨 한 음 — 짧게 때리고 길게 사라진다 */
  private bell(freq: number, start: number, peak: number): void {
    const ctx = this.ctx
    const dest = this.filter
    if (!ctx || !dest) return

    const gain = ctx.createGain()
    gain.gain.setValueAtTime(0.0001, start)
    gain.gain.linearRampToValueAtTime(peak, start + 0.04)
    gain.gain.exponentialRampToValueAtTime(0.0001, start + BELL_DECAY)
    gain.connect(dest)
    if (this.send) gain.connect(this.send)

    const osc = ctx.createOscillator()
    osc.type = 'triangle'
    osc.frequency.value = freq
    osc.connect(gain)
    osc.start(start)
    osc.stop(start + BELL_DECAY + 0.05)
    osc.onended = () => gain.disconnect()
  }
}

export interface FilmMusicPlayer {
  /** 이 브라우저에서 소리를 만들 수 있는가 */
  supported: boolean
  /** 재생 시작. 사용자 동작(클릭) 안에서 불러야 한다 */
  start: (mood: string, pace?: number) => void
  /** 서서히 사라지게 하고 멈춘다 */
  stop: () => void
  /** 가족의 목소리·낭독이 나는 동안 음량을 내린다 */
  duck: (on: boolean) => void
}

export function useFilmMusic(): FilmMusicPlayer {
  const engine = useRef<FilmMusicEngine | null>(null)
  const supported = isFilmMusicSupported()

  // 화면을 떠나면 소리도 따라 사라져야 한다. AudioContext는 컴포넌트가 사라져도
  // 살아 있어서, 닫지 않으면 다른 페이지에서 음악이 계속 난다.
  useEffect(() => {
    return () => {
      engine.current?.dispose()
      engine.current = null
    }
  }, [])

  const start = useCallback(
    (mood: string, pace = 1) => {
      if (!supported) return
      if (!engine.current) engine.current = new FilmMusicEngine()
      engine.current.start(mood, pace)
    },
    [supported],
  )

  const stop = useCallback(() => {
    engine.current?.stop()
  }, [])

  const duck = useCallback((on: boolean) => {
    engine.current?.duck(on)
  }, [])

  return { supported, start, stop, duck }
}
