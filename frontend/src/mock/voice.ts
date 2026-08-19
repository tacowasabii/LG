/**
 * 목데이터 — 실제 가족 음성 (기획안 대표 경험 "어머니 음성 12초")
 *
 * 실기능 개발 시 교체 지점:
 *   MOCK_VOICE_CLIPS -> GET /api/media?media_type=audio
 *   waveform         -> 업로드 시 서버에서 피크 배열을 뽑아 내려준다
 *   재생             -> components/AudioClip.tsx 의 시뮬레이션을 <audio src> 로 교체
 *
 * 지금은 오디오 파일이 없으므로 재생은 타이머로 흉내만 낸다. 화면 설계를
 * 확정하는 단계라 파형·길이·전사문의 레이아웃만 실제와 같게 맞춰 두었다.
 */

export type VoiceSource = 'interview' | 'home_video' | 'voice_memo'

export interface VoiceClip {
  id: string
  event_id: string
  event_title: string
  speaker_id: string
  speaker_name: string
  duration_sec: number
  /** 음성 그대로의 전사문. 요약이 아니라 원문을 보존한다 */
  transcript: string
  recorded_at: string
  source: VoiceSource
  /** 0~1 정규화된 파형 피크 */
  waveform: number[]
}

export const VOICE_SOURCE_LABEL: Record<VoiceSource, string> = {
  interview: 'AI 인터뷰 녹음',
  home_video: '홈비디오 음성',
  voice_memo: '음성 메모',
}

/** 시드 기반 결정적 파형 — 렌더마다 모양이 바뀌지 않게 한다 */
function makeWaveform(seed: number, count = 56): number[] {
  const bars: number[] = []
  let x = seed
  for (let i = 0; i < count; i++) {
    x = (x * 1103515245 + 12345) % 2147483648
    const noise = (x / 2147483648) * 0.55
    // 말소리처럼 중앙이 차오르고 끝이 잦아드는 봉투를 씌운다
    const envelope = Math.sin((Math.PI * (i + 1)) / (count + 1)) ** 0.7
    bars.push(Math.max(0.12, Math.min(1, (0.45 + noise) * envelope)))
  }
  return bars
}

export const MOCK_VOICE_CLIPS: VoiceClip[] = [
  {
    id: 'V01',
    event_id: 'E01',
    event_title: '1998 부산 가족여행',
    speaker_id: 'P02',
    speaker_name: '박서연',
    duration_sec: 12,
    transcript:
      '그때 하늘이가 바다를 처음 봤어요. 파도가 밀려오니까 무서워서 내 다리를 꽉 붙잡고 안 놓더라고. 한참 있다가 발만 담그고 웃었지.',
    recorded_at: '2026-07-12',
    source: 'interview',
    waveform: makeWaveform(11),
  },
  {
    id: 'V04',
    event_id: 'E01',
    event_title: '1998 부산 가족여행',
    speaker_id: 'P01',
    speaker_name: '김민수',
    duration_sec: 15,
    transcript:
      '여행 전에 캠코더를 하나 새로 샀어요. 그거 들고 하늘이 노는 것만 계속 찍었지. 지금 보면 화면이 흔들려서 웃긴데, 그때는 그게 그렇게 좋았어요.',
    recorded_at: '2026-07-12',
    source: 'interview',
    waveform: makeWaveform(29),
  },
  {
    id: 'V02',
    event_id: 'E04',
    event_title: '2010 할머니 칠순잔치',
    speaker_id: 'P05',
    speaker_name: '이정자',
    duration_sec: 18,
    transcript:
      '내 칠순에 자식들 손주들 다 모였어. 촛불을 같이 부는데, 나는 그날 사진보다 그 소리가 더 기억에 남아. 다들 웃는 소리.',
    recorded_at: '2026-07-19',
    source: 'interview',
    waveform: makeWaveform(47),
  },
  {
    id: 'V03',
    event_id: 'E06',
    event_title: '2017 첫 가족 캠핑',
    speaker_id: 'P04',
    speaker_name: '김지우',
    duration_sec: 9,
    transcript:
      '모닥불 앞에서 형이랑 아빠랑 늦게까지 얘기했어요. 그날 처음으로 아빠 어릴 때 이야기를 들었어요.',
    recorded_at: '2026-07-20',
    source: 'home_video',
    waveform: makeWaveform(73),
  },
]

export function clipsForEvent(eventId: string): VoiceClip[] {
  return MOCK_VOICE_CLIPS.filter((c) => c.event_id === eventId)
}

export function clipById(id: string): VoiceClip | undefined {
  return MOCK_VOICE_CLIPS.find((c) => c.id === id)
}

/** 인터뷰 녹음 시뮬레이션이 끝나면 이 전사문이 입력창에 채워진다 */
export const MOCK_TRANSCRIBED =
  '그날은 아침에 비가 조금 왔어요. 점심 지나서 개서 그때 바다에 나갔지.'

/** 새로 녹음한 클립의 자리표시자 파형 */
export const MOCK_RECORDING_WAVEFORM = makeWaveform(97)
