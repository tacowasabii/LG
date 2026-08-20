/**
 * 목소리를 글로 (기획안 "답변을 원본 음성으로 저장" + 검색 가능한 기억)
 *
 * 브라우저의 Web Speech API를 쓴다. 이 저장소에 붙어 있는 AI는 EXAONE 텍스트
 * 모델 하나뿐이고 STT API 키가 없다. 서버에 음성 인식을 두려면 키·비용·오디오
 * 디코더가 함께 따라오는데, 브라우저는 이미 그것을 들고 있다.
 *
 * 파형을 브라우저에서 계산하는 것과 같은 분업이다 (lib/recorder.ts). 서버는
 * 파일과 글자만 받는다.
 *
 * 녹음(MediaRecorder)과 동시에 돈다. 둘이 마이크를 각각 잡지만 크롬에서는 같은
 * 입력을 함께 들을 수 있다. 인식이 실패해도 녹음은 그대로 남는다 — 목소리 원본이
 * 이 제품의 자산이고, 글은 그것을 찾기 위한 색인이다. 순서를 뒤집지 않는다.
 *
 * 여기서 나온 글은 사람이 말한 그대로가 아니라 **기계가 옮긴 것**이다. 그래서
 * 화면은 고칠 수 있게 두고, 고치지 않은 글은 그래프에 ai_stt로 남는다
 * (backend/models/graph_models.py SourceType). 기획안의 사실 vs 추정 분리다.
 *
 * 한계를 적어 둔다:
 *   - 크롬·엣지에서 동작한다. 사파리·파이어폭스는 지원이 없거나 불완전하다.
 *   - 크롬은 음성을 구글 서버로 보낸다. 오프라인에서는 동작하지 않는다.
 *   - 조용하면 스스로 멈춘다. continuous를 켜도 그래서 다시 시작해 준다.
 *
 * 실기능 확장 지점:
 *   서버 STT(Whisper 등)를 붙이면 stop()이 blob을 그 API로 보내는 형태가 된다.
 *   화면 쪽 계약(final/interim 업데이트)은 그대로 쓸 수 있다.
 */

/** 인식 결과. interim은 다음 순간에 바뀔 수 있는 조각이다 */
export interface TranscriptUpdate {
  /** 모델이 확정한 문장들 */
  final: string
  /** 지금 듣고 있는 조각 — 확정 전이라 바뀐다 */
  interim: string
}

export type TranscriberErrorKind = 'denied' | 'network' | 'unsupported' | 'unknown'

export interface TranscriberError {
  kind: TranscriberErrorKind
  message: string
}

/** 브라우저가 주는 최소한의 모양만 적는다 (lib.dom 타입 유무에 기대지 않는다) */
interface SpeechRecognitionLike {
  lang: string
  continuous: boolean
  interimResults: boolean
  maxAlternatives: number
  start(): void
  stop(): void
  abort(): void
  onresult: ((event: any) => void) | null
  onerror: ((event: any) => void) | null
  onend: (() => void) | null
}

type SpeechRecognitionCtor = new () => SpeechRecognitionLike

function recognitionCtor(): SpeechRecognitionCtor | null {
  if (typeof window === 'undefined') return null
  const w = window as any
  return w.SpeechRecognition || w.webkitSpeechRecognition || null
}

export function isTranscriptionSupported(): boolean {
  return recognitionCtor() !== null
}

const ERROR_MESSAGE: Record<TranscriberErrorKind, string> = {
  denied: '마이크 사용이 막혀 있어 글로 옮기지 못했습니다. 녹음은 그대로 저장됩니다.',
  network: '네트워크가 닿지 않아 글로 옮기지 못했습니다. 녹음은 그대로 저장됩니다.',
  unsupported: '이 브라우저는 자동 전사를 지원하지 않습니다. 크롬에서 쓸 수 있습니다.',
  unknown: '글로 옮기지 못했습니다. 녹음은 그대로 저장됩니다.',
}

function errorKind(code: string): TranscriberErrorKind {
  if (code === 'not-allowed' || code === 'service-not-allowed') return 'denied'
  if (code === 'network') return 'network'
  return 'unknown'
}

/** stop()이 마지막 확정 결과를 기다리는 시간. 넘기면 가진 것으로 끝낸다 */
const FINALIZE_TIMEOUT_MS = 1500

export class LiveTranscriber {
  private recognition: SpeechRecognitionLike | null = null
  /** 사용자가 멈추라고 했는가 — 저절로 끊긴 것과 구분한다 */
  private stopping = false
  private finalText = ''
  private interimText = ''
  private onUpdate?: (update: TranscriptUpdate) => void
  private onError?: (error: TranscriberError) => void
  /** onend를 기다리는 stop() */
  private finalize: (() => void) | null = null

  start(handlers: {
    onUpdate: (update: TranscriptUpdate) => void
    onError?: (error: TranscriberError) => void
  }): void {
    const Ctor = recognitionCtor()
    if (!Ctor) {
      handlers.onError?.({ kind: 'unsupported', message: ERROR_MESSAGE.unsupported })
      return
    }

    this.onUpdate = handlers.onUpdate
    this.onError = handlers.onError
    this.stopping = false
    this.finalText = ''
    this.interimText = ''

    const recognition = new Ctor()
    recognition.lang = 'ko-KR'
    recognition.continuous = true
    recognition.interimResults = true
    recognition.maxAlternatives = 1

    recognition.onresult = (event: any) => {
      let interim = ''
      // resultIndex부터가 이번에 새로 온 것이다. 앞은 이미 반영했다.
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i]
        const text = result[0]?.transcript ?? ''
        if (result.isFinal) {
          this.finalText = (this.finalText + ' ' + text).trim()
        } else {
          interim += text
        }
      }
      this.interimText = interim
      this.onUpdate?.({ final: this.finalText, interim })
    }

    recognition.onerror = (event: any) => {
      const code = event?.error ?? ''
      // 조용한 구간에서 나는 소리다. 오류로 알리면 화면이 시끄러워진다.
      if (code === 'no-speech' || code === 'aborted') return
      this.onError?.({ kind: errorKind(code), message: ERROR_MESSAGE[errorKind(code)] })
    }

    recognition.onend = () => {
      if (this.stopping) {
        this.finalize?.()
        return
      }
      // 크롬은 잠깐 조용하면 스스로 끝낸다. 녹음은 계속되고 있으므로 다시 듣는다.
      try {
        recognition.start()
      } catch {
        // 이미 시작된 상태면 무시한다
      }
    }

    this.recognition = recognition
    try {
      recognition.start()
    } catch (e) {
      console.warn('[transcriber] 시작하지 못했습니다', e)
      this.recognition = null
      this.onError?.({ kind: 'unknown', message: ERROR_MESSAGE.unknown })
    }
  }

  /**
   * 인식을 멈추고 옮긴 글을 돌려준다.
   *
   * 마지막 확정 결과가 onend 직전에 오므로 그때까지 기다린다. 안 오면
   * 확정된 것에 마지막 조각을 붙여서 끝낸다 — 짧게 말하고 바로 멈추면
   * 확정이 없는 채로 조각만 남는 경우가 있다.
   */
  async stop(): Promise<string> {
    const recognition = this.recognition
    if (!recognition) return this.finalText

    this.stopping = true

    await new Promise<void>((resolve) => {
      let done = false
      let timer = 0
      const finish = () => {
        if (done) return
        done = true
        window.clearTimeout(timer)
        resolve()
      }
      // onend가 오면 여기로 들어온다. 안 오면 타이머가 끝낸다.
      this.finalize = finish
      timer = window.setTimeout(finish, FINALIZE_TIMEOUT_MS)

      try {
        recognition.stop()
      } catch {
        finish()
      }
    })

    this.finalize = null
    this.recognition = null

    const trailing = this.interimText.trim()
    if (trailing && !this.finalText) return trailing
    return this.finalText
  }

  /** 결과를 버린다 (녹음을 취소했을 때) */
  cancel(): void {
    this.stopping = true
    this.finalize = null
    try {
      this.recognition?.abort()
    } catch {
      // 이미 끝난 상태면 무시한다
    }
    this.recognition = null
    this.finalText = ''
    this.interimText = ''
  }
}
