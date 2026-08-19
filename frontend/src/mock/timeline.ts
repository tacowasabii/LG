/**
 * 목데이터 — Timeline & Map (기획안 02장 EXPANSION · TIMELINE)
 *
 * 실기능 개발 시 교체 지점:
 *   MOCK_TIMELINE  -> GET /api/graph/events (참여자·미디어·음성 수 포함으로 확장)
 *   MOCK_PLACES    -> GET /api/graph/places
 *   coverageGaps() -> 서버에서 "기록 공백 구간"을 계산해 내려주기
 *
 * 좌표와 제목은 실제 그래프(data/graph.json)에서 그대로 옮겼다. 지도 화면을
 * 백엔드 없이도 볼 수 있게 프론트에 복사해 둔 것이다.
 */

import type { VerificationState } from '../lib/api'

export interface TimelinePlace {
  id: string
  name: string
  lat: number
  lng: number
}

export interface TimelineEvent {
  id: string
  title: string
  date: string
  place: TimelinePlace
  participant_ids: string[]
  media_thumbs: string[]
  media_count: number
  memory_count: number
  voice_count: number
  state: VerificationState
}

export const MOCK_TIMELINE: TimelineEvent[] = [
  {
    id: 'E01',
    title: '1998 부산 가족여행',
    date: '1998-08-13',
    place: { id: 'place_E01', name: '부산 광안리 해수욕장', lat: 35.1532, lng: 129.1187 },
    participant_ids: ['P01', 'P02', 'P03'],
    media_thumbs: [
      '/media-files/E01_001.jpg',
      '/media-files/E01_002.jpg',
      '/media-files/E01_003.jpg',
    ],
    media_count: 4,
    memory_count: 2,
    voice_count: 2,
    state: 'conflicted',
  },
  {
    id: 'E02',
    title: '2003 하늘 초등학교 입학식',
    date: '2003-03-05',
    place: { id: 'place_E02', name: '서울 은솔초등학교', lat: 37.5663, lng: 126.978 },
    participant_ids: ['P01', 'P02', 'P03'],
    media_thumbs: [
      '/media-files/E02_001.jpg',
      '/media-files/E02_002.jpg',
      '/media-files/E02_003.jpg',
    ],
    media_count: 3,
    memory_count: 1,
    voice_count: 0,
    state: 'confirmed',
  },
  {
    id: 'E03',
    title: '2006 제주도 여름여행',
    date: '2006-07-23',
    place: { id: 'place_E03', name: '제주 협재해수욕장', lat: 33.3946, lng: 126.2397 },
    participant_ids: ['P01', 'P02', 'P03', 'P04'],
    media_thumbs: [
      '/media-files/E03_001.jpg',
      '/media-files/E03_002.jpg',
      '/media-files/E03_003.jpg',
    ],
    media_count: 3,
    memory_count: 1,
    voice_count: 0,
    state: 'supported',
  },
  {
    id: 'E04',
    title: '2010 할머니 칠순잔치',
    date: '2010-11-21',
    place: { id: 'place_E04', name: '대전 가족식당', lat: 36.3504, lng: 127.3845 },
    participant_ids: ['P01', 'P02', 'P03', 'P04', 'P05'],
    media_thumbs: [
      '/media-files/E04_001.jpg',
      '/media-files/E04_002.jpg',
      '/media-files/E04_003.jpg',
    ],
    media_count: 3,
    memory_count: 1,
    voice_count: 1,
    state: 'confirmed',
  },
  {
    id: 'E05',
    title: '2015 하늘 고등학교 졸업식',
    date: '2015-02-13',
    place: { id: 'place_E05', name: '서울 미래고등학교', lat: 37.5576, lng: 126.992 },
    participant_ids: ['P01', 'P02', 'P03', 'P04', 'P06'],
    media_thumbs: [
      '/media-files/E05_001.jpg',
      '/media-files/E05_002.jpg',
      '/media-files/E05_003.jpg',
    ],
    media_count: 3,
    memory_count: 1,
    voice_count: 0,
    state: 'inferred',
  },
  {
    id: 'E06',
    title: '2017 첫 가족 캠핑',
    date: '2017-10-08',
    place: { id: 'place_E06', name: '가평 은평캠핑장', lat: 37.8315, lng: 127.5096 },
    participant_ids: ['P01', 'P02', 'P03', 'P04'],
    media_thumbs: [
      '/media-files/E06_001.jpg',
      '/media-files/E06_002.jpg',
      '/media-files/E06_003.jpg',
    ],
    media_count: 4,
    memory_count: 1,
    voice_count: 1,
    state: 'supported',
  },
  {
    id: 'E07',
    title: '2021 하늘 결혼식',
    date: '2021-05-29',
    place: { id: 'place_E07', name: '서울 라움웨딩홀', lat: 37.5167, lng: 127.041 },
    participant_ids: ['P01', 'P02', 'P03', 'P04', 'P05', 'P07'],
    media_thumbs: [
      '/media-files/E07_001.jpg',
      '/media-files/E07_002.jpg',
      '/media-files/E07_003.jpg',
    ],
    media_count: 5,
    memory_count: 1,
    voice_count: 0,
    state: 'confirmed',
  },
  {
    id: 'E08',
    title: '2024 부모님 환갑 가족모임',
    date: '2024-09-14',
    place: { id: 'place_E08', name: '부산 오션뷰 레스토랑', lat: 35.158, lng: 129.1604 },
    participant_ids: ['P01', 'P02', 'P03', 'P04', 'P05'],
    media_thumbs: [
      '/media-files/E08_001.jpg',
      '/media-files/E08_002.jpg',
      '/media-files/E08_003.jpg',
    ],
    media_count: 3,
    memory_count: 1,
    voice_count: 0,
    state: 'inferred',
  },
]

export const MOCK_PLACES: TimelinePlace[] = MOCK_TIMELINE.map((e) => e.place)

export interface CoverageGap {
  from_year: number
  to_year: number
  years: number
  suggestion: string
}

/** 사건 사이가 3년 이상 벌어진 구간 = 기록 공백 */
export function coverageGaps(events: TimelineEvent[]): CoverageGap[] {
  const sorted = [...events].sort((a, b) => a.date.localeCompare(b.date))
  const gaps: CoverageGap[] = []

  for (let i = 1; i < sorted.length; i++) {
    const from = Number(sorted[i - 1].date.slice(0, 4))
    const to = Number(sorted[i].date.slice(0, 4))
    const years = to - from
    if (years >= 3) {
      gaps.push({
        from_year: from,
        to_year: to,
        years,
        suggestion:
          from + '년과 ' + to + '년 사이 ' + years + '년의 기록이 없습니다. 이 시기 사진이나 이야기가 있나요?',
      })
    }
  }

  return gaps
}

/** 온보딩에서 고를 수 있는 사진 후보 (기획안 리스크 대응: 사진 3장으로 시작) */
export const MOCK_ONBOARDING_CANDIDATES = [
  { id: 'E01_001', path: '/media-files/E01_001.jpg', hint: '바다 앞 가족' },
  { id: 'E01_002', path: '/media-files/E01_002.jpg', hint: '캠코더를 든 사람' },
  { id: 'E01_003', path: '/media-files/E01_003.jpg', hint: '물놀이' },
  { id: 'E04_001', path: '/media-files/E04_001.jpg', hint: '케이크와 가족' },
  { id: 'E06_003', path: '/media-files/E06_003.jpg', hint: '모닥불 밤' },
  { id: 'E07_003', path: '/media-files/E07_003.jpg', hint: '손을 잡은 두 사람' },
]

/** 근거 카드에서 미디어 id로 썸네일을 찾을 때 쓴다 */
export const MOCK_MEDIA_THUMBS: Record<string, string> = MOCK_TIMELINE.reduce(
  (acc, event) => {
    event.media_thumbs.forEach((path) => {
      const id = path.split('/').pop()?.replace('.jpg', '') || path
      acc[id] = path
    })
    return acc
  },
  {} as Record<string, string>,
)

export function eventById(id: string): TimelineEvent | undefined {
  return MOCK_TIMELINE.find((e) => e.id === id)
}
