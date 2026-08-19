/**
 * 목데이터 — Memory Film (기획안 02장 CORE · STORY)
 *
 * 실기능 개발 시 교체 지점:
 *   MOCK_STORYBOARDS   -> POST /api/film  (사건 id + 길이 + 대상 세대)
 *   MOCK_ANNIVERSARIES -> GET  /api/film/anniversaries
 *
 * 기획안의 "진정성 원칙"에 맞춰 장면마다 원본 출처와 적용된 AI 효과를 함께
 * 들고 있다. 화면에서 효과 목록을 반드시 노출해 생성 요소를 숨기지 않는다.
 */

export type Audience = 'child' | 'adult' | 'elder'
export type FilmLength = 30 | 45 | 60

export const AUDIENCE_LABEL: Record<Audience, string> = {
  child: '아이용',
  adult: '성인용',
  elder: '어르신용',
}

export const AUDIENCE_DESC: Record<Audience, string> = {
  child: '쉬운 낱말, 짧은 문장, 인물 이름을 자주 부릅니다.',
  adult: '사건의 배경과 관계를 설명합니다.',
  elder: '느린 전환, 큰 자막, 당시 호칭을 그대로 씁니다.',
}

export interface FilmScene {
  media_id: string
  thumb: string
  /** 화면에 얹히는 자막 */
  subtitle: string
  /** 장면 설명 (편집자 시점) */
  note: string
  duration_sec: number
  /** 이 장면의 근거 */
  source_label: string
  /** 이 장면에 적용된 AI 효과. 비어 있으면 원본 그대로 */
  ai_effects: string[]
  /** 연결된 실제 음성 클립 */
  voice_id?: string
}

export interface Storyboard {
  event_id: string
  title: string
  subtitle: string
  narration: string
  scenes: FilmScene[]
}

export const MOCK_STORYBOARDS: Storyboard[] = [
  {
    event_id: 'E01',
    title: '엄마가 처음 바다를 본 날',
    subtitle: '1998년 8월 · 부산 광안리',
    narration:
      '1998년 여름, 세 사람은 처음으로 함께 부산에 갔습니다. 그날 하늘이는 파도를 무서워했고, 아버지는 새로 산 캠코더를 계속 들고 있었습니다.',
    scenes: [
      {
        media_id: 'E01_001',
        thumb: '/media-files/E01_001.jpg',
        subtitle: '1998년 8월 · 광안리 해수욕장',
        note: '해변에서 세 사람이 함께 찍은 여행 기념사진',
        duration_sec: 8,
        source_label: '원본 사진 · EXIF 1998-08-13',
        ai_effects: ['느린 패닝', '깊이 기반 시차'],
      },
      {
        media_id: 'E01_002',
        thumb: '/media-files/E01_002.jpg',
        subtitle: '아버지의 새 캠코더',
        note: '아버지가 캠코더로 어린 하늘을 촬영하는 장면',
        duration_sec: 7,
        source_label: '원본 사진 + 아빠 인터뷰 음성 15초',
        ai_effects: ['느린 줌 인'],
        voice_id: 'V04',
      },
      {
        media_id: 'E01_003',
        thumb: '/media-files/E01_003.jpg',
        subtitle: '"파도가 무서워서 다리를 붙잡고"',
        note: '물가에서 파도를 만나는 장면. 엄마 음성이 이 위에 깔린다',
        duration_sec: 12,
        source_label: '원본 사진 + 엄마 인터뷰 음성 12초',
        ai_effects: ['미세 배경 움직임'],
        voice_id: 'V01',
      },
      {
        media_id: 'video_E001',
        thumb: '/media-files/E01_001.jpg',
        subtitle: '1998년 홈비디오',
        note: '캠코더 원본 영상 구간 (편집 없이 그대로)',
        duration_sec: 8,
        source_label: '원본 영상 E001.mp4',
        ai_effects: [],
      },
    ],
  },
  {
    event_id: 'E04',
    title: '촛불을 함께 불던 밤',
    subtitle: '2010년 11월 · 대전',
    narration:
      '2010년 11월, 할머니의 칠순에 온 가족이 한자리에 모였습니다. 할머니는 그날 사진보다 다들 웃던 소리를 더 오래 기억합니다.',
    scenes: [
      {
        media_id: 'E04_001',
        thumb: '/media-files/E04_001.jpg',
        subtitle: '2010년 11월 · 할머니 칠순',
        note: '케이크 앞에 온 가족이 모인 기념사진',
        duration_sec: 9,
        source_label: '원본 사진 · 가족 확인 완료',
        ai_effects: ['느린 패닝'],
      },
      {
        media_id: 'E04_003',
        thumb: '/media-files/E04_003.jpg',
        subtitle: '"나는 그 소리가 더 기억에 남아"',
        note: '촛불을 부는 순간. 할머니 음성이 이 위에 깔린다',
        duration_sec: 18,
        source_label: '원본 사진 + 할머니 인터뷰 음성 18초',
        ai_effects: ['미세 배경 움직임'],
        voice_id: 'V02',
      },
      {
        media_id: 'E04_002',
        thumb: '/media-files/E04_002.jpg',
        subtitle: '할머니와 손주들',
        note: '할머니와 하늘, 지우가 함께 찍은 사진',
        duration_sec: 8,
        source_label: '원본 사진 · 가족 확인 완료',
        ai_effects: ['느린 줌 아웃'],
      },
    ],
  },
  {
    event_id: 'E07',
    title: '손을 잡은 두 사람',
    subtitle: '2021년 5월 · 서울',
    narration:
      '2021년 5월, 하늘이가 결혼했습니다. 할머니는 웨딩드레스를 입은 손녀를 보며 기쁘면서도 뭉클했다고 말합니다.',
    scenes: [
      {
        media_id: 'E07_003',
        thumb: '/media-files/E07_003.jpg',
        subtitle: '2021년 5월 · 라움웨딩홀',
        note: '신부와 할머니가 손을 잡고 마주 보는 장면',
        duration_sec: 10,
        source_label: '원본 사진 · 가족 확인 완료',
        ai_effects: ['느린 줌 인', '깊이 기반 시차'],
      },
      {
        media_id: 'E07_001',
        thumb: '/media-files/E07_001.jpg',
        subtitle: '가족사진',
        note: '공식 가족사진',
        duration_sec: 8,
        source_label: '원본 사진',
        ai_effects: ['느린 패닝'],
      },
      {
        media_id: 'video_E007_01',
        thumb: '/media-files/E07_002.jpg',
        subtitle: '식장 입장',
        note: '원본 영상 구간',
        duration_sec: 12,
        source_label: '원본 영상 E007_01.mp4',
        ai_effects: [],
      },
    ],
  },
]

export interface Anniversary {
  date: string
  label: string
  event_id: string
  reason: string
  days_left: number
}

/** 오늘(2026-08-19) 기준 다가오는 기념일 */
export const MOCK_ANNIVERSARIES: Anniversary[] = [
  {
    date: '2026-09-14',
    label: '부모님 환갑 2주년',
    event_id: 'E08',
    reason: '2024년 9월 14일 가족모임 기록이 있습니다',
    days_left: 26,
  },
  {
    date: '2026-11-21',
    label: '할머니 생신',
    event_id: 'E04',
    reason: '2010년 칠순잔치와 같은 날짜입니다',
    days_left: 94,
  },
  {
    date: '2027-05-29',
    label: '하늘 결혼 6주년',
    event_id: 'E07',
    reason: '2021년 5월 29일 결혼식 기록이 있습니다',
    days_left: 283,
  },
  {
    date: '2027-08-13',
    label: '첫 부산 여행 29주년',
    event_id: 'E01',
    reason: '가장 오래된 기록입니다. 이 사건에는 음성이 2개 있습니다',
    days_left: 359,
  },
]

export function storyboardFor(eventId: string): Storyboard | undefined {
  return MOCK_STORYBOARDS.find((s) => s.event_id === eventId)
}

/**
 * 길이 옵션에 맞춰 장면을 자른다. 실제로는 서버가 재편집하지만,
 * 화면에서 길이 선택의 결과가 보여야 하므로 여기서 흉내만 낸다.
 */
export function fitToLength(scenes: FilmScene[], target: FilmLength): FilmScene[] {
  const picked: FilmScene[] = []
  let total = 0
  for (const scene of scenes) {
    if (total + scene.duration_sec > target && picked.length > 0) break
    picked.push(scene)
    total += scene.duration_sec
  }
  return picked
}
