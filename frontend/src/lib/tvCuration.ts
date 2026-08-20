/**
 * TV 대기화면(Today's Memory)과 프리셋 큐레이션 (기획안 06장 LG TV / webOS)
 *
 * 기획안의 문장: "TV가 꺼진 시간이 아니라 가족 이야기가 자연스럽게 노출되는 시간".
 * 그래서 대기화면은 사용자가 찾아오기를 기다리지 않고 먼저 말을 건다.
 * TV에는 키보드가 없으므로 검색창이 아니라 고른 몇 개의 프리셋으로만 들어간다.
 *
 * 사건 목록(GET /api/graph/events)만 받아서 계산한다. 사건 id를 코드에 박지
 * 않으므로 그래프가 바뀌어도 프리셋이 따라 움직인다.
 *
 * 서버로 옮길 자리: ambientSlides()는 "N년 전 오늘"을 계산하는 일이므로 서버가
 * 하는 편이 맞다 (GET /api/tv/ambient). 지금은 사건 8개 규모라 화면에서 센다.
 */

import type { EventListItem, TVJourney, VoiceClip } from './api'

export interface AmbientSlide {
  event: EventListItem
  /** 이 슬라이드에 띄울 사진 */
  media_path: string
  /** "28년 전 이맘때" 처럼 왜 지금 이 사진인지 밝히는 한 줄 */
  reason: string
  voice_count: number
}

const year = (event: EventListItem) => Number((event.date_start || '').slice(0, 4))

/** 오늘과 같은 월·일에서 며칠 떨어졌는지 (연말연시를 넘어가도 가깝게 센다) */
function daysFromAnniversary(eventDate: string, today: Date): number {
  const [, month, day] = eventDate.split('-').map(Number)
  if (!month || !day) return 999
  const thisYear = new Date(today.getFullYear(), month - 1, day)
  const diff = Math.abs(thisYear.getTime() - today.getTime()) / 86400000
  return Math.round(Math.min(diff, 365 - diff))
}

function reasonFor(event: EventListItem, today: Date): string {
  const date = event.date_start || ''
  const years = today.getFullYear() - year(event)
  const distance = daysFromAnniversary(date, today)
  const month = Number(date.slice(5, 7))

  if (distance === 0) return years + '년 전 오늘'
  if (distance <= 10) return years + '년 전 이맘때'
  if (month) return years + '년 전 ' + month + '월'
  return years + '년 전'
}

/**
 * 대기화면에 돌려 쓸 슬라이드. 오늘 날짜에 가까운 기념일을 앞에 세우고,
 * 같은 거리면 오래된 기억을 먼저 보여준다 (오래된 사진이 더 말을 건다).
 */
export function ambientSlides(
  events: EventListItem[],
  clips: VoiceClip[] = [],
  today: Date = new Date(),
  limit = 4,
): AmbientSlide[] {
  // 사진이 없는 사건은 대기화면에 띄울 그림이 없다
  const withPhoto = events.filter((e) => e.media_thumbs.length > 0 && e.date_start)

  const ranked = [...withPhoto].sort((a, b) => {
    const byDistance =
      daysFromAnniversary(a.date_start!, today) - daysFromAnniversary(b.date_start!, today)
    if (byDistance !== 0) return byDistance
    return (a.date_start || '').localeCompare(b.date_start || '')
  })

  return ranked.slice(0, limit).map((event) => ({
    event,
    media_path: event.media_thumbs[0],
    reason: reasonFor(event, today),
    voice_count: clips.filter((c) => c.event_id === event.id).length,
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

/** 장소 이름에서 괄호 주석과 세부 지명을 떼어 "부산" 같은 큰 단위로 */
function placeKey(event: EventListItem): string {
  const name = (event.place?.name || event.location_name || '').replace(/\(.*\)/, '').trim()
  return name.split(' ')[0] || ''
}

/**
 * 프리셋. TV에서 고를 수 있는 갈래는 시기 / 장소 / 사람 / 목소리 / 한 사람의 기억이면
 * 충분하다. 더 늘리면 리모컨으로 훑는 시간이 재생 시간을 넘는다.
 *
 * 사건 id를 박지 않고 데이터에서 뽑는다 — 사진을 더 올리면 프리셋도 바뀐다.
 */
export function tvPresets(events: EventListItem[], clips: VoiceClip[] = []): TVPreset[] {
  if (events.length === 0) return []

  const byDate = [...events]
    .filter((e) => e.date_start)
    .sort((a, b) => (a.date_start || '').localeCompare(b.date_start || ''))
  const thumbOf = (list: EventListItem[]) => list.find((e) => e.media_thumbs[0])?.media_thumbs[0] || ''
  const presets: TVPreset[] = []

  // 1. 가장 오래된 기억
  const oldest = byDate[0]
  if (oldest) {
    presets.push({
      id: 'oldest',
      label: '가장 오래된 기억',
      sublabel: year(oldest) + ' · ' + oldest.title,
      query: oldest.title,
      thumb: thumbOf([oldest]),
      event_ids: [oldest.id],
    })
  }

  // 2. 같은 장소에 남은 기억이 여럿이면 그 장소로 묶는다
  const placeCount = new Map<string, EventListItem[]>()
  events.forEach((e) => {
    const key = placeKey(e)
    if (!key) return
    placeCount.set(key, [...(placeCount.get(key) || []), e])
  })
  const [topPlace, placeEvents] =
    [...placeCount.entries()].sort((a, b) => b[1].length - a[1].length)[0] || ['', []]
  if (placeEvents.length > 1) {
    presets.push({
      id: 'place-' + topPlace,
      label: topPlace + '에서 보낸 날들',
      sublabel:
        placeEvents.length +
        '개 사건 · 사진 ' +
        placeEvents.reduce((sum, e) => sum + e.media_count, 0) +
        '장',
      query: topPlace,
      thumb: thumbOf(placeEvents),
      event_ids: placeEvents.map((e) => e.id),
    })
  }

  // 3. 가장 많이 등장한 사람의 시간
  const personCount = new Map<string, { name: string; events: EventListItem[] }>()
  events.forEach((e) => {
    e.participants.forEach((p) => {
      const entry = personCount.get(p.id) || { name: p.name, events: [] }
      entry.events.push(e)
      personCount.set(p.id, entry)
    })
  })
  const topPerson = [...personCount.values()].sort((a, b) => b.events.length - a.events.length)[0]
  if (topPerson && topPerson.events.length > 1) {
    presets.push({
      id: 'person-' + topPerson.name,
      label: topPerson.name + '의 시간',
      sublabel: topPerson.events.length + '개 사건',
      query: topPerson.name,
      thumb: thumbOf(topPerson.events),
      event_ids: topPerson.events.map((e) => e.id),
    })
  }

  // 4. 목소리가 남은 기억 — 이 제품에서 가장 들려주고 싶은 것
  const voiceEventIds = new Set(clips.map((c) => c.event_id).filter(Boolean) as string[])
  const withVoice = events.filter((e) => voiceEventIds.has(e.id))
  if (withVoice.length > 0) {
    presets.push({
      id: 'voices',
      label: '목소리가 남은 기억',
      sublabel: '실제 가족 음성 ' + clips.length + '개',
      query: withVoice[0].title,
      thumb: thumbOf(withVoice),
      event_ids: withVoice.map((e) => e.id),
    })
  }

  // 5. 가장 최근의 모임
  const latest = byDate[byDate.length - 1]
  if (latest && latest.id !== oldest?.id) {
    presets.push({
      id: 'recent',
      label: '가장 최근의 모임',
      sublabel: year(latest) + ' · ' + latest.title,
      query: latest.title,
      thumb: thumbOf([latest]),
      event_ids: [latest.id],
    })
  }

  // 6. 아직 한 사람만 기억하는 추억 — 함께 보다가 기억을 더할 수 있게.
  //    예전에는 "확인이 필요한 기억"이었다. TV 앞에 모인 가족에게 확인 과제를
  //    내밀지 않는다 — 보다가 떠오르면 말하면 된다.
  const alone = events.filter((e) => e.state === 'alone')
  if (alone.length > 0) {
    presets.push({
      id: 'alone',
      label: '한 사람만 기억하는 추억',
      sublabel: alone.length + '개 · 함께 보면 기억이 떠오를지도',
      query: alone[0].title,
      thumb: thumbOf(alone),
      event_ids: alone.map((e) => e.id),
    })
  }

  return presets
}

/**
 * 백엔드 없이 재생하기 위한 로컬 Journey 조립.
 *
 * POST /api/tv/journey 는 정적 배포(VITE_STATIC_MODE)에서는 호출할 서버가 없고,
 * 발표 중 백엔드가 죽으면 TV 화면이 통째로 비어 버린다. 대기화면에서 OK만
 * 눌렀는데 아무 일도 일어나지 않는 것이 이 화면에서 가장 나쁜 실패다.
 * 서버 응답과 같은 모양(TVJourney)으로 맞춰 두었으므로 화면 코드는 구분하지 않는다.
 */
export function buildLocalJourney(
  title: string,
  eventIds: string[],
  events: EventListItem[],
): TVJourney {
  const picked = eventIds
    .map((id) => events.find((e) => e.id === id))
    .filter((e): e is EventListItem => Boolean(e))
    .sort((a, b) => (a.date_start || '').localeCompare(b.date_start || ''))

  const slides: TVJourney['slides'] = [
    {
      type: 'title',
      caption: title,
      media_id: null,
      file_path: null,
      event_id: null,
      event_title: null,
      date: null,
    },
  ]

  picked.forEach((event) => {
    event.media_thumbs.forEach((path) => {
      slides.push({
        type: 'photo',
        media_id: path.split('/').pop()?.replace(/\.[a-z]+$/i, '') ?? null,
        file_path: path,
        caption: event.title,
        event_id: event.id,
        event_title: event.title,
        date: event.date_start,
      })
    })
  })

  const years = picked.map((e) => (e.date_start || '').slice(0, 4)).filter(Boolean)
  const span =
    years.length > 1
      ? years[0] + '년부터 ' + years[years.length - 1] + '년까지'
      : years[0] + '년'

  return {
    id: 'local-' + eventIds.join('-'),
    title,
    slides,
    // 내레이션은 EXAONE이 쓰는 자리다. 서버가 없을 때는 지어내지 않고 사실만 적는다
    narration:
      span + ', 사건 ' + picked.length + '개와 사진 ' + (slides.length - 1) + '장이 연결되어 있습니다.',
    total_duration_sec: (slides.length - 1) * 9,
  }
}
