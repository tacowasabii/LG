/**
 * 여러 화면이 함께 쓰는 그래프 데이터 훅
 *
 * 사건 요약과 음성은 홈·지도·채팅·인물·TV가 모두 필요로 한다. 화면마다 fetch를
 * 새로 쓰면 필드 이름과 실패 처리가 조금씩 달라지므로 여기로 모았다.
 *
 * 캐시는 모듈 스코프에 둔다. 사건 8개 규모라 정교한 캐시가 필요하지 않고,
 * 화면을 옮길 때마다 목록이 다시 깜빡이지 않는 것이 더 중요하다.
 * 무언가를 새로 남긴 뒤에는 invalidate*()를 불러 다음 조회에서 다시 받는다.
 */

import { useCallback, useEffect, useState } from 'react'
import { EventListItem, VoiceClip, getEvents, getVoiceClips } from './api'

let eventCache: EventListItem[] | null = null
let voiceCache: Record<string, VoiceClip[]> = {}

export function invalidateEvents(): void {
  eventCache = null
}

export function invalidateVoiceClips(): void {
  voiceCache = {}
}

export interface EventsState {
  events: EventListItem[]
  loading: boolean
  /** id로 사건 찾기 — 근거 뱃지·슬라이드가 장소와 확인 상태를 붙일 때 쓴다 */
  eventById: (id: string | null | undefined) => EventListItem | undefined
  reload: () => void
}

export function useEvents(): EventsState {
  const [events, setEvents] = useState<EventListItem[]>(eventCache || [])
  const [loading, setLoading] = useState(!eventCache)

  const load = useCallback((force = false) => {
    if (eventCache && !force) {
      setEvents(eventCache)
      setLoading(false)
      return
    }
    setLoading(true)
    getEvents()
      .then((list) => {
        eventCache = list
        setEvents(list)
      })
      .catch((e) => console.error('[events] 불러오지 못했습니다', e))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const eventById = useCallback(
    (id: string | null | undefined) => (id ? events.find((e) => e.id === id) : undefined),
    [events],
  )

  return {
    events,
    loading,
    eventById,
    reload: () => load(true),
  }
}

export interface VoiceState {
  clips: VoiceClip[]
  loading: boolean
  /** 그 사건에서 남긴 목소리 */
  clipsForEvent: (eventId: string | null | undefined) => VoiceClip[]
  reload: () => void
}

/** personId를 주면 그 사람이 말한 음성만 */
export function useVoiceClips(personId?: string): VoiceState {
  const key = personId || '__all__'
  const [clips, setClips] = useState<VoiceClip[]>(voiceCache[key] || [])
  const [loading, setLoading] = useState(!voiceCache[key])

  const load = useCallback(
    (force = false) => {
      if (voiceCache[key] && !force) {
        setClips(voiceCache[key])
        setLoading(false)
        return
      }
      setLoading(true)
      getVoiceClips(personId)
        .then((list) => {
          voiceCache[key] = list
          setClips(list)
        })
        .catch((e) => console.error('[voice] 불러오지 못했습니다', e))
        .finally(() => setLoading(false))
    },
    [key, personId],
  )

  useEffect(() => {
    load()
  }, [load])

  const clipsForEvent = useCallback(
    (eventId: string | null | undefined) =>
      eventId ? clips.filter((c) => c.event_id === eventId) : [],
    [clips],
  )

  return {
    clips,
    loading,
    clipsForEvent,
    reload: () => load(true),
  }
}
