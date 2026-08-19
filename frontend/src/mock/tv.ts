/**
 * 목데이터 — TV 대기화면(Today's Memory) & 프리셋 (기획안 06장 LG TV / webOS)
 *
 * 기획안의 문장: "TV가 꺼진 시간이 아니라 가족 이야기가 자연스럽게 노출되는 시간".
 * 그래서 대기화면은 사용자가 찾아오기를 기다리지 않고 먼저 말을 거는 화면이다.
 * TV에는 키보드가 없으므로 검색창이 아니라 고른 몇 개의 프리셋으로만 들어간다.
 *
 * 실기능 개발 시 교체 지점:
 *   ambientSlides()    -> GET  /api/tv/ambient?date=YYYY-MM-DD ("N년 전 오늘"을 서버가 계산)
 *   tvPresets()        -> GET  /api/tv/presets (최근 본 것·확인 대기 사건을 섞어 서버가 큐레이션)
 *   buildLocalJourney()-> POST /api/tv/journey 만 쓰고 이 함수는 삭제
 *
 * 사건·사진·상태는 mock/timeline.ts 를 그대로 쓴다. 대기화면이 실제 그래프와
 * 다른 사건을 보여주면 리모컨으로 넘어간 재생 화면과 어긋난다.
 */

import type { TVJourney } from '../lib/api'
import { MOCK_TIMELINE, TimelineEvent } from './timeline'
import { clipsForEvent } from './voice'

export interface AmbientSlide {
  event: TimelineEvent
  /** 이 슬라이드에 띄울 사진 */
  media_path: string
  /** "28년 전 이맘때" 처럼 왜 지금 이 사진인지 밝히는 한 줄 */
  reason: string
  voice_count: number
}

/** 오늘과 같은 월·일에서 며칠 떨어졌는지 (연말연시를 넘어가도 가깝게 센다) */
function daysFromAnniversary(eventDate: string, today: Date): number {
  const [, month, day] = eventDate.split('-').map(Number)
  const thisYear = new Date(today.getFullYear(), month - 1, day)
  const diff = Math.abs(thisYear.getTime() - today.getTime()) / 86400000
  return Math.round(Math.min(diff, 365 - diff))
}

function reasonFor(event: TimelineEvent, today: Date): string {
  const years = today.getFullYear() - Number(event.date.slice(0, 4))
  const distance = daysFromAnniversary(event.date, today)
  const month = Number(event.date.slice(5, 7))

  if (distance === 0) return years + '년 전 오늘'
  if (distance <= 10) return years + '년 전 이맘때'
  return years + '년 전 ' + month + '월'
}

/**
 * 대기화면에 돌려 쓸 슬라이드. 오늘 날짜에 가까운 기념일을 앞에 세우고,
 * 같은 거리면 오래된 기억을 먼저 보여준다 (오래된 사진이 더 말을 건다).
 */
export function ambientSlides(today: Date = new Date(), limit = 4): AmbientSlide[] {
  const ranked = [...MOCK_TIMELINE].sort((a, b) => {
    const byDistance = daysFromAnniversary(a.date, today) - daysFromAnniversary(b.date, today)
    if (byDistance !== 0) return byDistance
    return a.date.localeCompare(b.date)
  })

  return ranked.slice(0, limit).map((event) => ({
    event,
    media_path: event.media_thumbs[0],
    reason: reasonFor(event, today),
    voice_count: clipsForEvent(event.id).length,
  }))
}

export interface TVPreset {
  id: string
  label: string
  sublabel: string
  /** POST /api/tv/journey 에 넘길 질의 */
  query: string
  thumb: string
  /** 서버 없이 재생할 때 쓸 사건 목록 */
  event_ids: string[]
}

/**
 * 프리셋 6개. TV에서 고를 수 있는 갈래는 사건 / 사람 / 시기 / 확인 대기,
 * 이 네 가지면 충분하다. 더 늘리면 리모컨으로 훑는 시간이 재생 시간을 넘는다.
 */
export function tvPresets(): TVPreset[] {
  const byId = (id: string) => MOCK_TIMELINE.find((e) => e.id === id)
  const thumbOf = (id: string) => byId(id)?.media_thumbs[0] ?? ''
  const needsCheck = MOCK_TIMELINE.filter(
    (e) => e.state === 'inferred' || e.state === 'conflicted',
  )

  return [
    {
      id: 'trip-busan',
      label: '부산에서 보낸 날들',
      sublabel: '1998 · 2024 · 사진 7장',
      query: '부산 여행',
      thumb: thumbOf('E01'),
      event_ids: ['E01', 'E08'],
    },
    {
      id: 'grandma',
      label: '할머니의 칠순',
      sublabel: '2010 · 음성 1개',
      query: '할머니 칠순잔치',
      thumb: thumbOf('E04'),
      event_ids: ['E04'],
    },
    {
      id: 'haneul-growth',
      label: '하늘이가 자라는 동안',
      sublabel: '입학식부터 결혼식까지',
      query: '하늘이의 성장',
      thumb: thumbOf('E02'),
      event_ids: ['E02', 'E05', 'E07'],
    },
    {
      id: 'summer',
      label: '우리 가족의 여름',
      sublabel: '바다와 캠핑',
      query: '여름 바다 여행',
      thumb: thumbOf('E03'),
      event_ids: ['E01', 'E03', 'E06'],
    },
    {
      id: 'recent',
      label: '가장 최근의 모임',
      sublabel: '2024 부모님 환갑',
      query: '2024년 가족모임',
      thumb: thumbOf('E08'),
      event_ids: ['E08'],
    },
    {
      id: 'needs-check',
      label: '확인이 필요한 기억',
      sublabel: needsCheck.length + '개 사건 · 가족에게 물어볼 것',
      query: '확인이 필요한 기억',
      thumb: thumbOf(needsCheck[0]?.id ?? 'E05'),
      event_ids: needsCheck.map((e) => e.id),
    },
  ]
}

/**
 * 백엔드 없이 재생하기 위한 로컬 Journey 조립.
 *
 * POST /api/tv/journey 는 정적 배포(VITE_STATIC_MODE)에서는 호출할 서버가 없고,
 * 발표 중 백엔드가 죽으면 TV 화면이 통째로 비어 버린다. 대기화면에서 OK만
 * 눌렀는데 아무 일도 일어나지 않는 것이 이 화면에서 가장 나쁜 실패다.
 * 서버 응답과 같은 모양(TVJourney)으로 맞춰 두었으므로 화면 코드는 구분하지 않는다.
 */
export function buildLocalJourney(title: string, eventIds: string[]): TVJourney {
  const events = eventIds
    .map((id) => MOCK_TIMELINE.find((e) => e.id === id))
    .filter((e): e is TimelineEvent => Boolean(e))
    .sort((a, b) => a.date.localeCompare(b.date))

  const slides: TVJourney['slides'] = [
    { type: 'title', caption: title, media_id: null, file_path: null, event_id: null, event_title: null, date: null },
  ]

  events.forEach((event) => {
    event.media_thumbs.forEach((path) => {
      slides.push({
        type: 'photo',
        media_id: path.split('/').pop()?.replace('.jpg', '') ?? null,
        file_path: path,
        caption: event.title,
        event_id: event.id,
        event_title: event.title,
        date: event.date,
      })
    })
  })

  const years = events.map((e) => e.date.slice(0, 4))
  const span = years.length > 1 ? years[0] + '년부터 ' + years[years.length - 1] + '년까지' : years[0] + '년'

  return {
    id: 'local-' + eventIds.join('-'),
    title,
    slides,
    // 내레이션은 EXAONE이 쓰는 자리다. 서버가 없을 때는 지어내지 않고 사실만 적는다
    narration: span + ', 사건 ' + events.length + '개와 사진 ' + (slides.length - 1) + '장이 연결되어 있습니다.',
    total_duration_sec: (slides.length - 1) * 9,
  }
}
