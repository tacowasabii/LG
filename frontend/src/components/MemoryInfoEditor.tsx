/**
 * 추억의 정보 고치기 — 제목 · 날짜 · 장소 · 함께한 사람
 *
 * 추억 상세의 정보 칸(기획안 09의 두 번째 줄)이 그대로 입력칸으로 바뀐다. 읽던
 * 자리에서 고치므로 어느 값이 무엇이었는지 다시 찾을 필요가 없다.
 *
 * 만들 때 AI 초안을 고쳐 저장했더라도 뒤늦게 어긋난 것이 나온다 — EXIF에 촬영
 * 날짜가 없어 올린 날이 들어갔거나, 좌표에서 짐작한 지명이 옆 동네였거나, 얼굴
 * 인식이 놓친 할머니가 "함께한 사람"에 없다. 그때 지우고 다시 만들게 하면 가족이
 * 그 추억에 남긴 기억과 "나도 기억나요"가 함께 사라진다.
 *
 * 기억 문장을 고치는 칸은 없다. 제목·날짜·장소는 가족이 함께 보는 기록이고, 기억
 * 문장은 그 말을 한 사람의 것이다 — 더한 기억이 원본을 덮지 않는 것과 같은 규칙이다
 * (MemoryComposer도 제목·날짜·장소 칸을 두지 않는다). 자기 문장을 고치려면 지우고
 * 다시 남긴다.
 *
 * 권한은 화면이 판단하지 않는다. 남이 만든 추억이면 서버가 403으로 막고 이유를
 * 함께 보내며("이 추억은 박서연님이 올렸습니다…"), 그 문장을 그대로 적는다.
 * 단추를 미리 감추면 왜 못 고치는지 말할 자리가 없어진다 (MemoryDeleteButton과
 * 같은 방식이다).
 */

import { useState } from 'react'
import {
  MemoryDetail,
  MemoryUpdateInput,
  PersonRef,
  readDetail,
  updateMemory,
} from '../lib/api'
import { useCurrentUser } from '../lib/currentUser'
import { useEvents } from '../lib/useGraphData'

type SaveResult = Awaited<ReturnType<typeof updateMemory>>

interface Props {
  detail: MemoryDetail
  /** 저장이 끝난 뒤. 서버가 밝힌 것(무엇이 바뀌었는가)을 그대로 넘긴다 */
  onSaved: (result: SaveResult) => void
  onCancel: () => void
}

export default function MemoryInfoEditor({ detail, onSaved, onCancel }: Props) {
  const { members } = useCurrentUser()
  const { events } = useEvents()

  const [title, setTitle] = useState(detail.title)
  const [dateStart, setDateStart] = useState((detail.date_start || '').slice(0, 10))
  const [placeName, setPlaceName] = useState(detail.place?.name || '')
  /* 이름을 손대지 않은 동안만 그래프의 그 장소다 (CollectPage와 같은 규칙) */
  const [placeId, setPlaceId] = useState<string | null>(detail.place?.id || null)
  const [personIds, setPersonIds] = useState<string[]>(detail.participants.map((p) => p.id))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  /*
    고를 수 있는 사람 — 가족 구성원과, 이미 이 추억에 있는 참여자.
    둘을 합치는 이유는 구성원 목록에 없는 참여자가 있을 수 있기 때문이다
    (초대 대기 중인 가족). 목록에 없으면 알약이 안 뜨고, 저장하는 순간 그 사람이
    조용히 빠진다 — 고치지 않은 것을 고쳐 버리는 셈이다.
  */
  const choices: PersonRef[] = [
    ...members,
    ...detail.participants.filter((p) => !members.some((m) => m.id === p.id)),
  ]

  /* 이미 쓰고 있는 장소 이름 — 같은 이름을 적으면 그 장소를 다시 쓴다 */
  const placeNames = Array.from(
    new Set(events.map((e) => e.place?.name).filter((name): name is string => !!name)),
  ).sort()

  const save = async () => {
    setSaving(true)
    setError(null)
    const input: MemoryUpdateInput = {
      title,
      date_start: dateStart || null,
      place_id: placeId,
      place_name: placeId ? null : placeName || null,
      person_ids: personIds,
    }
    try {
      onSaved(await updateMemory(detail.id, input))
    } catch (e) {
      // 남의 추억이면 403, 제목을 비웠으면 400. 서버가 밝힌 이유를 그대로 적는다
      setError(readDetail(e, '정보를 고치지 못했습니다.'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="surface p-6">
      <p className="t-eyebrow m-0 mb-4 text-ink-300">정보 고치기</p>

      <div className="flex flex-col gap-2.5">
        <label className="flex flex-wrap items-center gap-2.5">
          <span className="t-caption w-[80px] shrink-0">제목</span>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="field field-sm min-w-0 flex-1"
          />
        </label>

        <label className="flex flex-wrap items-center gap-2.5">
          <span className="t-caption w-[80px] shrink-0">날짜</span>
          <input
            type="date"
            value={dateStart}
            onChange={(e) => setDateStart(e.target.value)}
            className="field field-sm min-w-0 flex-1"
          />
        </label>

        <label className="flex flex-wrap items-center gap-2.5">
          <span className="t-caption w-[80px] shrink-0">장소</span>
          <input
            value={placeName}
            list="memory-place-names"
            placeholder="예: 부산 해운대"
            onChange={(e) => {
              // 이름을 고치면 더 이상 그래프의 그 장소가 아니다
              setPlaceName(e.target.value)
              setPlaceId(null)
            }}
            className="field field-sm min-w-0 flex-1"
          />
          <datalist id="memory-place-names">
            {placeNames.map((name) => (
              <option key={name} value={name} />
            ))}
          </datalist>
        </label>

        <div className="flex flex-wrap items-start gap-2.5">
          <span className="t-caption mt-1.5 w-[80px] shrink-0">함께한 사람</span>
          <div className="flex min-w-0 flex-1 flex-wrap gap-1.5">
            {choices.map((person) => {
              const on = personIds.includes(person.id)
              return (
                <button
                  key={person.id}
                  onClick={() =>
                    setPersonIds((prev) =>
                      on ? prev.filter((id) => id !== person.id) : [...prev, person.id],
                    )
                  }
                  className="pill px-2.5 py-1"
                  style={
                    on
                      ? { background: 'var(--accent-soft)', color: 'var(--accent-ink)' }
                      : { background: 'var(--ink-50)', color: 'var(--ink-500)', fontWeight: 400 }
                  }
                >
                  {person.name}
                </button>
              )
            })}
          </div>
        </div>
      </div>

      {/*
        빈 값의 뜻과, 새 이름을 적었을 때 무엇이 생기는지 미리 밝힌다. 저장한
        뒤에 알게 되면 되돌리는 일이 한 번 더 생긴다.
      */}
      <p className="t-caption m-0 mt-4">
        날짜를 비우면 '날짜 미상'으로 남고, 장소를 비우면 지도에서 빠집니다. 이미 있는
        장소와 같은 이름이면 그 장소를 다시 쓰고, 새 이름은 좌표가 없어 지도에 점이
        찍히지 않습니다.
      </p>
      <p className="t-caption m-0 mt-1">
        가족이 남긴 기억 문장은 여기서 바뀌지 않습니다.
      </p>

      <div className="mt-5 flex items-center gap-3">
        <button onClick={save} disabled={saving} className="btn-primary disabled:opacity-40">
          {saving ? '저장 중…' : '저장'}
        </button>
        <button onClick={onCancel} disabled={saving} className="btn-quiet">
          취소
        </button>
      </div>

      {error && (
        <p className="t-body-sm m-0 mt-3" style={{ color: 'var(--critical-ink)' }}>
          {error}
        </p>
      )}
    </div>
  )
}
