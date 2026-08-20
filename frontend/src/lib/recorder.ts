/**
 * 목소리 녹음 (기획안 "답변을 원본 음성으로 저장")
 *
 * MediaRecorder로 녹음하고, 끝난 뒤 Web Audio로 파형 피크를 뽑는다. 파형을
 * 브라우저에서 계산하는 이유는 서버에 오디오 디코더(ffmpeg 등)를 두지 않기
 * 위해서다. 서버는 파일과 숫자 배열만 받는다.
 *
 * 전사(음성 → 글)는 여기서 하지 않는다. lib/transcriber.ts가 녹음과 나란히
 * 돌면서 브라우저 음성 인식으로 옮긴다. 두 일을 나눠 둔 이유는 인식이 실패해도
 * 녹음은 끝까지 남아야 하기 때문이다 — 목소리 원본이 이 제품의 자산이고 글은
 * 그것을 찾기 위한 색인이다.
 */

/** 파형 막대 개수 — AudioClip이 그리는 개수와 맞춘다 */
const PEAK_COUNT = 56

export interface Recording {
  blob: Blob
  durationSec: number
  waveform: number[]
  /** 미리 듣기용 로컬 URL. 업로드 후 해제한다 */
  previewUrl: string
}

export function isRecordingSupported(): boolean {
  return (
    typeof navigator !== 'undefined' &&
    !!navigator.mediaDevices?.getUserMedia &&
    typeof MediaRecorder !== 'undefined'
  )
}

/** 브라우저가 받아 주는 첫 번째 형식을 고른다 (사파리는 webm을 못 쓴다) */
function pickMimeType(): string | undefined {
  const candidates = ['audio/webm', 'audio/mp4', 'audio/ogg']
  for (const type of candidates) {
    if (MediaRecorder.isTypeSupported?.(type)) return type
  }
  return undefined
}

export class VoiceRecorder {
  private recorder: MediaRecorder | null = null
  private chunks: Blob[] = []
  private stream: MediaStream | null = null
  private startedAt = 0

  async start(): Promise<void> {
    if (!isRecordingSupported()) {
      throw new Error('이 브라우저에서는 녹음을 쓸 수 없습니다.')
    }

    this.stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    const mimeType = pickMimeType()
    this.recorder = new MediaRecorder(this.stream, mimeType ? { mimeType } : undefined)
    this.chunks = []

    this.recorder.ondataavailable = (e) => {
      if (e.data.size > 0) this.chunks.push(e.data)
    }

    this.startedAt = performance.now()
    this.recorder.start(200)
  }

  /** 녹음을 멈추고 파일·길이·파형을 돌려준다 */
  async stop(): Promise<Recording> {
    const recorder = this.recorder
    if (!recorder) throw new Error('녹음이 시작되지 않았습니다.')

    const stopped = new Promise<void>((resolve) => {
      recorder.onstop = () => resolve()
    })
    recorder.stop()
    await stopped

    this.stream?.getTracks().forEach((track) => track.stop())
    this.stream = null
    this.recorder = null

    const blob = new Blob(this.chunks, { type: recorder.mimeType || 'audio/webm' })
    const elapsedSec = (performance.now() - this.startedAt) / 1000

    // 디코딩이 실패해도 녹음 자체는 살린다 (파형이 없을 뿐이다)
    let waveform: number[] = []
    let durationSec = elapsedSec
    try {
      const decoded = await decodePeaks(blob)
      waveform = decoded.waveform
      if (decoded.durationSec > 0) durationSec = decoded.durationSec
    } catch (e) {
      console.warn('[recorder] 파형을 뽑지 못했습니다', e)
    }

    return {
      blob,
      durationSec: Math.round(durationSec * 10) / 10,
      waveform,
      previewUrl: URL.createObjectURL(blob),
    }
  }

  /** 녹음을 버린다 (화면에서 취소했을 때) */
  cancel(): void {
    try {
      this.recorder?.stop()
    } catch {
      // 이미 멈춘 상태면 무시한다
    }
    this.stream?.getTracks().forEach((track) => track.stop())
    this.stream = null
    this.recorder = null
    this.chunks = []
  }
}

/** 녹음 파일에서 0~1 정규화된 피크 배열과 길이를 뽑는다 */
export async function decodePeaks(
  blob: Blob,
  peakCount = PEAK_COUNT,
): Promise<{ waveform: number[]; durationSec: number }> {
  const AudioCtx = window.AudioContext || (window as any).webkitAudioContext
  const ctx = new AudioCtx()

  try {
    const buffer = await ctx.decodeAudioData(await blob.arrayBuffer())
    const channel = buffer.getChannelData(0)
    const bucketSize = Math.floor(channel.length / peakCount) || 1

    const peaks: number[] = []
    let loudest = 0

    for (let i = 0; i < peakCount; i++) {
      let peak = 0
      const start = i * bucketSize
      for (let j = start; j < start + bucketSize && j < channel.length; j++) {
        const value = Math.abs(channel[j])
        if (value > peak) peak = value
      }
      peaks.push(peak)
      if (peak > loudest) loudest = peak
    }

    // 가장 큰 소리를 1로 맞춘다. 조용히 녹음해도 파형이 보이게.
    const waveform = peaks.map((p) =>
      loudest > 0 ? Math.max(0.06, Math.min(1, p / loudest)) : 0.06,
    )

    return { waveform, durationSec: buffer.duration }
  } finally {
    // 컨텍스트를 열어 두면 탭마다 오디오 자원을 붙잡는다
    void ctx.close()
  }
}
