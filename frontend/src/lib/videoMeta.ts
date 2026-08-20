/**
 * 영상에서 길이와 첫 장면을 뽑는다
 *
 * 파형을 브라우저에서 계산하는 것과 같은 분업이다 (lib/recorder.ts). 서버에
 * ffmpeg를 두지 않기 위해 브라우저가 재고, 서버는 숫자와 그림 파일만 받는다.
 *
 * 왜 필요한가: 영상은 목록·추억 카드에서 썸네일이 없어 원본을 통째로 물린다.
 * 사진 옆에 영상이 몇 개 섞이면 목록을 한 번 여는 데 수십 MB가 나간다. 첫 장면
 * 한 장을 뽑아 두면 그 자리를 그림으로 채울 수 있다.
 *
 * 실패는 정상 경로로 취급한다. 코덱을 브라우저가 못 열거나 길이를 못 재는 영상이
 * 있고, 그때 업로드가 막히면 안 된다 — 원본은 이미 사용자가 고른 파일이고
 * 썸네일은 편의다. 뽑지 못하면 null을 돌려주고 업로드는 그대로 간다.
 */

/** 썸네일 최대 변 길이. 서버의 사진 썸네일과 같은 크기로 맞춘다 */
const POSTER_MAX = 300

/** 못 여는 파일에서 무한정 기다리지 않는다 */
const PROBE_TIMEOUT_MS = 8000

export interface VideoMeta {
  /** 초. 못 재면 null */
  durationSec: number | null
  /** 첫 장면 JPEG. 못 뽑으면 null */
  poster: Blob | null
}

/** 첫 프레임이 검은 화면인 영상이 많아서 조금 뒤로 간다 */
function posterTime(duration: number): number {
  if (!Number.isFinite(duration) || duration <= 0) return 0
  return Math.min(1, duration * 0.1)
}

function drawPoster(video: HTMLVideoElement): Promise<Blob | null> {
  const width = video.videoWidth
  const height = video.videoHeight
  if (!width || !height) return Promise.resolve(null)

  const scale = Math.min(1, POSTER_MAX / Math.max(width, height))
  const canvas = document.createElement('canvas')
  canvas.width = Math.max(1, Math.round(width * scale))
  canvas.height = Math.max(1, Math.round(height * scale))

  const ctx = canvas.getContext('2d')
  if (!ctx) return Promise.resolve(null)

  try {
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height)
  } catch (e) {
    // 다른 출처의 영상이면 캔버스가 오염돼 그릴 수 없다 (지금은 로컬 파일뿐이다)
    console.warn('[videoMeta] 프레임을 그리지 못했습니다', e)
    return Promise.resolve(null)
  }

  return new Promise((resolve) => {
    canvas.toBlob((blob) => resolve(blob), 'image/jpeg', 0.82)
  })
}

/**
 * 영상 파일에서 길이와 첫 장면을 읽는다.
 * 어느 단계에서 실패해도 거기까지 얻은 것만 돌려준다.
 */
export async function probeVideo(file: File): Promise<VideoMeta> {
  const url = URL.createObjectURL(file)
  const video = document.createElement('video')
  video.preload = 'metadata'
  // 소리를 내지 않고 자동 재생 정책에 걸리지 않게 한다
  video.muted = true
  video.playsInline = true
  video.src = url

  const result: VideoMeta = { durationSec: null, poster: null }

  try {
    await new Promise<void>((resolve, reject) => {
      const timer = window.setTimeout(() => reject(new Error('영상 정보 읽기 시간 초과')), PROBE_TIMEOUT_MS)
      const done = (fn: () => void) => {
        window.clearTimeout(timer)
        fn()
      }
      video.onloadedmetadata = () => done(resolve)
      video.onerror = () => done(() => reject(new Error('영상을 열지 못했습니다')))
    })

    // webm 일부는 duration이 Infinity로 온다. 그럴 때는 길이를 적지 않는다.
    if (Number.isFinite(video.duration) && video.duration > 0) {
      result.durationSec = Math.round(video.duration * 10) / 10
    }

    await new Promise<void>((resolve, reject) => {
      const timer = window.setTimeout(() => reject(new Error('프레임 이동 시간 초과')), PROBE_TIMEOUT_MS)
      const done = (fn: () => void) => {
        window.clearTimeout(timer)
        fn()
      }
      video.onseeked = () => done(resolve)
      video.onerror = () => done(() => reject(new Error('프레임으로 이동하지 못했습니다')))
      video.currentTime = posterTime(video.duration)
    })

    result.poster = await drawPoster(video)
  } catch (e) {
    // 길이만 얻고 그림을 못 뽑은 경우도 여기로 온다. 얻은 것은 그대로 쓴다.
    console.warn('[videoMeta] 영상 정보를 다 읽지 못했습니다', e)
  } finally {
    video.onloadedmetadata = null
    video.onseeked = null
    video.onerror = null
    video.removeAttribute('src')
    video.load()
    URL.revokeObjectURL(url)
  }

  return result
}
