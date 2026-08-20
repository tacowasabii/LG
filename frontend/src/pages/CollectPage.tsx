/**
 * 모으기 — 올리면 AI가 묶어서 초안을 쓰고, 확인하면 그 자리에서 추억이 된다
 *
 * 예전 흐름은 "올리기 → 채우기 → 첫 질문"이었다. 올린 사진은 EXIF로 사건에
 * 자동으로 묶이고(또는 "2015년 기록" 같은 빈 사건이 새로 생기고), 그 추정은
 * 확인 요청으로 넘어가 가족이 판정해야 했다.
 *
 * 지금은 이렇다.
 *
 *   올리기 → 묶음별 AI 초안(제목·날짜·장소·함께한 가족·설명) → 고치거나 그대로 저장
 *
 * 저장하면 끝이다. 다른 가족의 승인을 기다리지 않는다. 대신 AI가 무엇을 근거로
 * 그렇게 썼는지 화면에 그대로 펼친다 — 촬영 시점, 좌표, 지목된 사람, 기존 가족
 * 기록. 사용자가 어디까지가 사실이고 어디부터가 추정인지 볼 수 있어야 한다.
 *
 * **어떤 사진이 같은 사건인지 사용자에게 묻지 않는다.** 첫 사용자는 앨범에서 아무
 * 사진이나 고르고, 그게 정상이다. 여러 사건이 섞여 있으면 날짜·좌표로 갈라 묶음마다
 * 초안을 세운다. 예전에는 업로드 하나가 추억 하나여서, 부산 사진과 서울 사진을 함께
 * 올리면 두 좌표의 평균 — 아무도 가 본 적 없는 지점 — 이 장소가 됐다.
 *
 * 확정하지 않는 것 셋.
 *   1. 갈린 묶음이 틀렸으면 "전부 하나의 추억으로"로 되돌릴 수 있다.
 *   2. 인물 추정은 "이 사진들에 엄마도 있나요?"로 되묻는다 (기획안 06).
 *   3. 기존 추억과 관련 있어 보이면 알려 주고, 붙일지 새로 만들지는 사용자가
 *      고른다. 자동으로 병합하지 않는다 (기획안 08).
 */

import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Sparkles } from 'lucide-react'
import {
  MemoryDraft,
  MediaUploadResult,
  addMediaToMemory,
  createMemory,
  draftMemory,
  mediaUrl,
  setMediaPersons,
  uploadMedia,
} from '../lib/api'
import {
  DraftForm,
  Group,
  clearCollectDraft,
  loadCollectDraft,
  saveCollectDraft,
} from '../lib/collectDraft'
import { useCurrentUser } from '../lib/currentUser'
import { invalidateEvents } from '../lib/useGraphData'
import { Page, PageHeader } from '../components/Page'

const MEDIA_TYPE_LABEL: Record<string, string> = {
  photo: '사진',
  video: '영상',
  audio: '음성',
}

function buildForm(draft: MemoryDraft): DraftForm {
  return {
    title: draft.title,
    date_start: (draft.date_start || '').slice(0, 10),
    // 그래프에 맞는 장소가 없으면 좌표에서 짐작한 지명을 채워 둔다. 짐작이므로
    // place_id는 비운다 — 저장하면 이 이름으로 새 장소가 만들어지고, 틀렸으면
    // 사용자가 저장 전에 고친다.
    place_name: draft.place?.name || draft.place_guess?.name || '',
    place_id: draft.place?.id || null,
    description: draft.description,
    person_ids: draft.person_ids,
  }
}

export default function CollectPage() {
  const { current, members } = useCurrentUser()

  /**
   * 저장하기 전에 쌓아 둔 것을 되살린다 (lib/collectDraft.ts).
   * 다른 탭에 갔다 오면 이 화면은 새로 마운트되므로, 초기값을 저장소에서 읽지
   * 않으면 올린 기록과 고쳐 둔 초안이 매번 사라진다. 한 번만 읽는다.
   */
  const [restored] = useState(loadCollectDraft)

  const [dragOver, setDragOver] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [results, setResults] = useState<MediaUploadResult[]>(restored.results)
  const [error, setError] = useState<string | null>(null)

  /** 기록별로 지목된 사람. 얼굴 인식이 없으므로 여기가 detected_faces의 출처다 */
  const [personTags, setPersonTags] = useState<Record<string, string[]>>(restored.personTags)
  const [tagging, setTagging] = useState<string | null>(null)

  const [groups, setGroups] = useState<Group[]>(restored.groups)
  /** AI가 갈랐는가 (합치기/다시 가르기 안내를 정한다) */
  const [grouped, setGrouped] = useState(restored.grouped)
  /** 지금 전부 하나로 합쳐 놓은 상태인가 */
  const [merged, setMerged] = useState(restored.merged)
  const [drafting, setDrafting] = useState(false)
  const [saving, setSaving] = useState<number | null>(null)

  // 바뀔 때마다 곧바로 써 둔다. 사용자가 언제 이 화면을 떠날지 알 수 없어서
  // (탭 이동·새로고침·뒤로 가기) 떠나는 순간에 맞춰 저장할 수 없다.
  useEffect(() => {
    saveCollectDraft({ results, personTags, groups, grouped, merged })
  }, [results, personTags, groups, grouped, merged])

  const patchGroup = (index: number, patch: Partial<Group>) =>
    setGroups((prev) => prev.map((g, i) => (i === index ? { ...g, ...patch } : g)))

  const makeDraft = useCallback(async (mediaIds: string[], merge = false) => {
    if (mediaIds.length === 0) return
    setDrafting(true)
    setError(null)
    try {
      const res = await draftMemory(mediaIds, merge)
      setGroups(res.groups.map((draft) => ({ draft, form: buildForm(draft), dismissed: [] })))
      setGrouped(res.grouped)
      setMerged(merge)
    } catch (e) {
      console.error(e)
      setError('초안을 만들지 못했습니다. 잠시 뒤 다시 시도해 주세요.')
    } finally {
      setDrafting(false)
    }
  }, [])

  const handleFiles = useCallback(
    async (files: FileList | null) => {
      if (!files || files.length === 0) return
      setUploading(true)
      setError(null)

      const uploaded: MediaUploadResult[] = []
      for (const file of Array.from(files)) {
        try {
          uploaded.push(await uploadMedia(file))
        } catch (e) {
          console.error(e)
          setError(`${file.name} 을 올리지 못했습니다. 파일 형식을 확인해 주세요.`)
        }
      }

      setResults((prev) => [...uploaded, ...prev])
      setPersonTags((prev) => {
        const next = { ...prev }
        uploaded.forEach((r) => {
          next[r.id] = r.detected_faces ?? []
        })
        return next
      })
      setUploading(false)

      if (uploaded.length === 0) return

      // 올린 것 전체를 다시 갈라 초안을 세운다. 아직 저장하지 않은 초안은
      // 새로 만들어지고, 이미 만든 추억은 아래 목록에 그대로 남는다.
      const pending = results
        .filter((r) => !isSaved(r.id, groups))
        .map((r) => r.id)
      await makeDraft([...uploaded.map((r) => r.id), ...pending])
    },
    [makeDraft, results, groups],
  )

  /**
   * 이 기록에 있는 사람을 켜고 끈다. 켠 결과 전체를 서버에 보낸다.
   * 낙관적으로 먼저 칠하고 실패하면 되돌린다 — 여러 번 누르는 조작이라 매번
   * 응답을 기다리면 누른 것이 반응하지 않는 것처럼 보인다.
   */
  const togglePerson = async (mediaId: string, personId: string) => {
    const before = personTags[mediaId] ?? []
    const next = before.includes(personId)
      ? before.filter((id) => id !== personId)
      : [...before, personId]

    setPersonTags((prev) => ({ ...prev, [mediaId]: next }))
    setTagging(mediaId)
    try {
      const res = await setMediaPersons(mediaId, next)
      setPersonTags((prev) => ({ ...prev, [mediaId]: res.detected_faces }))

      // 이 사진이 든 묶음의 "함께한 가족"도 따라간다 (같은 사실을 두 곳에서
      // 따로 관리하지 않는다)
      setGroups((prev) =>
        prev.map((group) => {
          if (!group.draft.media.some((m) => m.id === mediaId)) return group
          const on = res.detected_faces.includes(personId)
          const ids = group.form.person_ids.filter((id) => id !== personId)
          return {
            ...group,
            form: { ...group.form, person_ids: on ? [...ids, personId] : ids },
          }
        }),
      )
    } catch (e) {
      console.error(e)
      setPersonTags((prev) => ({ ...prev, [mediaId]: before }))
      setError('사람을 저장하지 못했습니다.')
    } finally {
      setTagging(null)
    }
  }

  /** AI가 되물은 인물을 "네"로 받는다 — 묶음의 함께한 가족에 넣고 사진에도 지목한다 */
  const acceptCandidate = async (index: number, personId: string) => {
    const group = groups[index]
    if (!group) return

    patchGroup(index, {
      form: {
        ...group.form,
        person_ids: Array.from(new Set([...group.form.person_ids, personId])),
      },
      dismissed: [...group.dismissed, personId],
    })

    for (const item of group.draft.media) {
      if (item.media_type === 'audio') continue
      const current = personTags[item.id] ?? []
      if (current.includes(personId)) continue
      try {
        const res = await setMediaPersons(item.id, [...current, personId])
        setPersonTags((prev) => ({ ...prev, [item.id]: res.detected_faces }))
      } catch (e) {
        console.error(e)
      }
    }
  }

  const save = async (index: number) => {
    const group = groups[index]
    if (!group || saving !== null) return
    setSaving(index)
    setError(null)
    try {
      const res = await createMemory({
        title: group.form.title,
        description: group.form.description,
        date_start: group.form.date_start || null,
        place_id: group.form.place_id,
        place_name: group.form.place_id ? null : group.form.place_name || null,
        lat: group.draft.lat ?? null,
        lng: group.draft.lng ?? null,
        person_ids: group.form.person_ids,
        media_ids: group.draft.media.map((m) => m.id),
      })
      invalidateEvents()
      patchGroup(index, { created: { id: res.event_id, title: group.form.title } })
    } catch (e) {
      console.error(e)
      setError('추억을 만들지 못했습니다. 다시 시도해 주세요.')
    } finally {
      setSaving(null)
    }
  }

  /** 이 묶음의 기록을 기존 추억에 더한다 (새 추억을 만들지 않는다) */
  const attachToExisting = async (index: number, eventId: string, title: string) => {
    const group = groups[index]
    if (!group || saving !== null) return
    setSaving(index)
    setError(null)
    try {
      await addMediaToMemory(
        eventId,
        group.draft.media.map((m) => m.id),
      )
      invalidateEvents()
      patchGroup(index, { attached: { id: eventId, title } })
    } catch (e) {
      console.error(e)
      setError('기존 추억에 더하지 못했습니다.')
    } finally {
      setSaving(null)
    }
  }

  const reset = () => {
    setResults([])
    setPersonTags({})
    setGroups([])
    setGrouped(false)
    setMerged(false)
    clearCollectDraft()
  }

  const firstTime = results.length === 0
  const openGroups = groups.filter((g) => !g.created && !g.attached).length

  return (
    <Page width={820}>
      <PageHeader
        eyebrow="Collect"
        title="사진을 올리면 AI가 추억을 씁니다"
        lead="여러 사건의 사진이 섞여 있어도 됩니다. 촬영 시점과 장소로 묶어 초안을 만들고, 확인하고 저장하면 바로 가족 공간에 남습니다 — 다른 가족의 확인을 기다리지 않습니다."
      />

      <div
        onDragOver={(e) => {
          e.preventDefault()
          setDragOver(true)
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDragOver(false)
          handleFiles(e.dataTransfer.files)
        }}
        onClick={() => document.getElementById('collect-file-input')?.click()}
        className="mt-8 cursor-pointer rounded-lg px-8 py-16 text-center
                   transition-colors duration-150 ease-out"
        style={{
          border: `1px dashed ${dragOver ? 'var(--accent)' : 'var(--border-strong)'}`,
          background: dragOver ? 'var(--accent-soft)' : 'transparent',
        }}
      >
        <p className="m-0 text-[17px] font-semibold text-ink-700">
          {uploading ? '올리는 중…' : '파일을 끌어오거나 눌러서 고르세요'}
        </p>
        <p className="t-caption m-0 mt-2">
          {firstTime
            ? '몇 장이든 괜찮습니다. 같은 사건인 것만 골라 올리지 않아도 됩니다 · JPG · PNG · MP4 · M4A'
            : '사진 JPG · PNG / 영상 MP4 · MOV / 음성 MP3 · M4A'}
        </p>
        <input
          id="collect-file-input"
          type="file"
          multiple
          accept="image/*,video/*,audio/*"
          className="hidden"
          onChange={(e) => handleFiles(e.target.files)}
        />
      </div>

      {firstTime && (
        <p className="t-caption mt-4 max-w-[46em]">
          앨범에서 아무 사진이나 고르면 됩니다. 촬영 시점과 좌표를 읽어 같은 사건끼리 묶고,
          묶음마다 초안을 하나씩 세웁니다. 시점이 없는 옛 사진은 따로 모아 두고 아는 것만
          물어봅니다 — 추측해서 채우지 않습니다.
        </p>
      )}

      {error && (
        <p className="t-body-sm mt-4" style={{ color: 'var(--critical-ink)' }}>
          {error}
        </p>
      )}

      {/* 올린 기록 — 무엇을 읽었는지, 누가 있는지 */}
      {results.length > 0 && (
        <div className="mt-9">
          <div
            className="flex items-baseline justify-between pb-3"
            style={{ borderBottom: '2px solid var(--ink-700)' }}
          >
            <p className="t-eyebrow m-0">올린 기록 {results.length}개</p>
            <button onClick={reset} className="btn-link">
              목록 비우기
            </button>
          </div>

          {results.map((result) => (
            <div
              key={result.id}
              className="px-1 py-5"
              style={{ borderBottom: '1px solid var(--border)' }}
            >
              <div className="flex items-start gap-5">
                {result.thumbnail_path ? (
                  <img
                    src={mediaUrl(result.thumbnail_path)}
                    alt=""
                    className="h-[72px] w-[72px] shrink-0 rounded bg-ink-50 object-cover"
                  />
                ) : (
                  <span
                    className="flex h-[72px] w-[72px] shrink-0 items-center justify-center
                               rounded bg-ink-50 text-[11px] text-ink-300"
                  >
                    {MEDIA_TYPE_LABEL[result.media_type] || result.media_type}
                  </span>
                )}

                <div className="min-w-0 flex-1">
                  <p className="t-mono m-0 text-xs text-ink-700">{result.original_filename}</p>
                  <div className="mt-2.5 flex flex-wrap gap-1.5">
                    <span className="pill bg-ink-50 font-normal text-ink-500">
                      {MEDIA_TYPE_LABEL[result.media_type] || result.media_type}
                    </span>
                    {result.exif_date ? (
                      <span className="pill bg-ink-50 font-normal text-ink-500">
                        촬영 {result.exif_date.slice(0, 10)}
                      </span>
                    ) : (
                      <span className="pill bg-ink-50 font-normal text-ink-500">
                        촬영 시점 없음
                      </span>
                    )}
                    {/* 좌표 숫자는 적지 않는다. "35.1587, 129.1604"를 보고 부산이라고
                        아는 사람은 없다. 짐작한 지명이 나오면 그것만 보여 주고,
                        표에 없는 곳(해외·바다)이면 위치가 담겨 있다는 사실만 말한다. */}
                    {result.exif_lat != null && (
                      <span className="pill bg-ink-50 font-normal text-ink-500">
                        {result.place_guess ? `${result.place_guess} 근처` : '위치 정보 있음'}
                      </span>
                    )}
                  </div>
                </div>
              </div>

              {/* 누가 있는지는 자동으로 알 수 없다 — 가족이 직접 지목한다.
                  음성은 찍힌 사람이 아니라 말한 사람이므로 여기서 다루지 않는다. */}
              {result.media_type !== 'audio' && members.length > 0 && (
                <div className="ml-[92px] mt-4">
                  <p className="t-caption m-0">
                    {result.faces_source === 'ai_vision' ? (
                      <>
                        <strong>AI가 얼굴로 알아본 사람</strong>입니다. 틀렸으면 눌러서
                        끄고, 빠진 사람은 눌러서 더하세요 — 고친 결과가 사실로 남습니다.
                      </>
                    ) : (
                      <>
                        이 {MEDIA_TYPE_LABEL[result.media_type] || '기록'}에 누가 있나요?
                        지목한 사람만 그래프에 이어집니다.
                      </>
                    )}
                  </p>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {members.map((m) => {
                      const on = (personTags[result.id] ?? []).includes(m.id)
                      return (
                        <button
                          key={m.id}
                          onClick={() => togglePerson(result.id, m.id)}
                          disabled={tagging === result.id}
                          className="pill px-2.5 py-1 disabled:opacity-50"
                          style={
                            on
                              ? { background: 'var(--accent-soft)', color: 'var(--accent-ink)' }
                              : {
                                  background: 'var(--ink-50)',
                                  color: 'var(--ink-500)',
                                  fontWeight: 400,
                                }
                          }
                        >
                          {m.name}
                        </button>
                      )
                    })}
                  </div>
                </div>
              )}
            </div>
          ))}

          {groups.length === 0 && (
            <button
              onClick={() => makeDraft(results.map((r) => r.id))}
              disabled={drafting}
              className="btn-primary mt-6 flex items-center gap-1.5 disabled:opacity-40"
            >
              <Sparkles size={15} />
              {drafting ? '초안을 쓰는 중…' : 'AI 초안 만들기'}
            </button>
          )}
        </div>
      )}

      {/* 묶음 안내 — AI가 갈랐다는 사실과 되돌릴 방법을 함께 밝힌다 */}
      {groups.length > 0 && (grouped || merged) && (
        <div className="mt-9 flex flex-wrap items-center justify-between gap-3">
          <p className="t-body-sm m-0 text-ink-500">
            {merged
              ? `올린 기록 ${results.length}개를 하나의 추억으로 봅니다.`
              : `촬영 시점과 장소로 ${groups.length}개 묶음으로 갈랐습니다. 묶음마다 따로 저장됩니다.`}
          </p>
          <button
            onClick={() =>
              makeDraft(
                results.filter((r) => !isSaved(r.id, groups)).map((r) => r.id),
                !merged,
              )
            }
            disabled={drafting || openGroups === 0}
            className="btn-quiet disabled:opacity-40"
          >
            {merged ? '다시 갈라 보기' : '전부 하나의 추억으로'}
          </button>
        </div>
      )}

      {/* 묶음별 초안 — 고치거나 그대로 저장한다 */}
      {groups.map((group, index) => {
        const { draft, form } = group
        const candidates = draft.person_candidates.filter(
          (c) => !group.dismissed.includes(c.id) && !form.person_ids.includes(c.id),
        )
        const busy = saving === index

        if (group.created) {
          return (
            <div key={index} className="surface mt-5 p-7">
              <p className="m-0 text-[17px] font-semibold text-ink-900">
                ‘{group.created.title}’이 가족 공간에 올라갔습니다
              </p>
              <p className="t-body-sm m-0 mt-2 max-w-[46em]">
                다른 가족은 확인할 의무가 없고, 기억나는 것이 있을 때만 자기 기억을 더합니다.
              </p>
              <div className="mt-4 flex flex-wrap gap-3">
                <Link
                  to={`/memory/${group.created.id}`}
                  className="btn-primary no-underline hover:no-underline"
                >
                  만든 추억 보기
                </Link>
                <Link
                  to="/continue"
                  className="btn-quiet no-underline hover:no-underline"
                >
                  가족의 추억에 기억 더하기
                </Link>
              </div>
            </div>
          )
        }

        if (group.attached) {
          return (
            <div key={index} className="surface mt-5 p-7">
              <p className="m-0 text-[17px] font-semibold text-ink-900">
                ‘{group.attached.title}’에 기록을 더했습니다
              </p>
              <p className="t-body-sm m-0 mt-2">원래 있던 기억은 그대로입니다.</p>
              <Link
                to={`/memory/${group.attached.id}`}
                className="btn-primary mt-4 inline-block no-underline hover:no-underline"
              >
                그 추억 보기
              </Link>
            </div>
          )
        }

        return (
          <div key={index} className="surface mt-5 p-7">
            <div className="flex flex-wrap items-baseline justify-between gap-3">
              <p className="t-eyebrow m-0">
                {groups.length > 1 ? `묶음 ${index + 1} / ${groups.length}` : 'AI 초안'} · 기록{' '}
                {draft.media.length}개
              </p>
              {index === 0 && (
                <button
                  onClick={() =>
                    makeDraft(
                      results.filter((r) => !isSaved(r.id, groups)).map((r) => r.id),
                      merged,
                    )
                  }
                  disabled={drafting}
                  className="btn-link disabled:opacity-40"
                >
                  {drafting ? '다시 쓰는 중…' : '초안 다시 만들기'}
                </button>
              )}
            </div>

            {/* 이 묶음에 든 기록 — 무엇이 한 추억이 되는지 눈으로 확인한다 */}
            <div className="mt-4 flex flex-wrap gap-2">
              {draft.media.map((item) =>
                item.thumbnail_path || item.media_type === 'photo' ? (
                  <img
                    key={item.id}
                    src={mediaUrl(item.thumbnail_path || item.file_path)}
                    alt=""
                    className="h-[62px] w-[84px] rounded bg-ink-50 object-cover"
                  />
                ) : (
                  <span
                    key={item.id}
                    className="flex h-[62px] w-[84px] items-center justify-center rounded
                               bg-ink-50 text-[11px] text-ink-300"
                  >
                    {MEDIA_TYPE_LABEL[item.media_type] || item.media_type}
                  </span>
                ),
              )}
            </div>

            <p className="t-caption m-0 mt-3 max-w-[46em]">
              {draft.ai_used
                ? 'AI가 읽어낸 사실만으로 썼습니다. 마음에 들지 않으면 고치세요 — 저장하는 것은 고친 결과입니다.'
                : '모델을 부르지 못해 읽어낸 사실로만 만들었습니다. 문장은 직접 다듬어 주세요.'}
            </p>

            {/* 무엇을 근거로 썼는가 */}
            {draft.evidence.length > 0 && (
              <div className="mt-4 rounded bg-ink-50 px-4 py-3.5">
                {draft.evidence.map((item) => (
                  <p key={item.label} className="t-body-sm m-0 text-ink-700">
                    <span className="t-caption mr-2 text-ink-300">{item.label}</span>
                    {item.detail}
                  </p>
                ))}
              </div>
            )}

            <div className="mt-5 flex flex-col gap-2.5">
              <label className="flex flex-wrap items-center gap-2.5">
                <span className="t-caption w-[68px] shrink-0">제목</span>
                <input
                  value={form.title}
                  onChange={(e) => patchGroup(index, { form: { ...form, title: e.target.value } })}
                  className="field field-sm min-w-0 flex-1"
                />
              </label>

              <label className="flex flex-wrap items-center gap-2.5">
                <span className="t-caption w-[68px] shrink-0">날짜</span>
                <input
                  type="date"
                  value={form.date_start}
                  onChange={(e) =>
                    patchGroup(index, { form: { ...form, date_start: e.target.value } })
                  }
                  className="field field-sm min-w-0 flex-1"
                />
              </label>

              <label className="flex flex-wrap items-center gap-2.5">
                <span className="t-caption w-[68px] shrink-0">장소</span>
                <input
                  value={form.place_name}
                  placeholder="예: 부산 해운대"
                  onChange={(e) =>
                    // 이름을 고치면 더 이상 그래프의 그 장소가 아니다
                    patchGroup(index, {
                      form: { ...form, place_name: e.target.value, place_id: null },
                    })
                  }
                  className="field field-sm min-w-0 flex-1"
                />
              </label>

              <label className="flex flex-wrap items-start gap-2.5">
                <span className="t-caption mt-2 w-[68px] shrink-0">설명</span>
                <textarea
                  value={form.description}
                  onChange={(e) =>
                    patchGroup(index, { form: { ...form, description: e.target.value } })
                  }
                  rows={3}
                  className="field min-w-0 flex-1 resize-y text-sm"
                />
              </label>

              <div className="flex flex-wrap items-start gap-2.5">
                <span className="t-caption mt-1.5 w-[68px] shrink-0">함께한 가족</span>
                <div className="flex min-w-0 flex-1 flex-wrap gap-1.5">
                  {members.map((m) => {
                    const on = form.person_ids.includes(m.id)
                    return (
                      <button
                        key={m.id}
                        onClick={() =>
                          patchGroup(index, {
                            form: {
                              ...form,
                              person_ids: on
                                ? form.person_ids.filter((id) => id !== m.id)
                                : [...form.person_ids, m.id],
                            },
                          })
                        }
                        className="pill px-2.5 py-1"
                        style={
                          on
                            ? { background: 'var(--accent-soft)', color: 'var(--accent-ink)' }
                            : {
                                background: 'var(--ink-50)',
                                color: 'var(--ink-500)',
                                fontWeight: 400,
                              }
                        }
                      >
                        {m.name}
                      </button>
                    )
                  })}
                </div>
              </div>
            </div>

            {/* 인물 추정 — 확정하지 않고 되묻는다 (기획안 06) */}
            {candidates.length > 0 && (
              <div className="mt-6 pt-5" style={{ borderTop: '1px solid var(--border)' }}>
                <p className="t-eyebrow m-0 mb-3 text-ink-300">AI가 묻습니다</p>
                {candidates.map((candidate) => (
                  <div key={candidate.id} className="mb-2.5 flex flex-wrap items-center gap-3">
                    {candidate.thumbnail_url ? (
                      <img
                        src={mediaUrl(candidate.thumbnail_url)}
                        alt=""
                        className="h-8 w-8 rounded-full bg-ink-50 object-cover"
                      />
                    ) : (
                      <span
                        className="flex h-8 w-8 items-center justify-center rounded-full bg-ink-50
                                   text-[11px] text-ink-300"
                      >
                        {candidate.name.slice(0, 1)}
                      </span>
                    )}
                    <span className="min-w-0 flex-1">
                      <span className="t-body-sm block text-ink-700">
                        이 사진에 {candidate.relation || candidate.name}({candidate.name})도
                        있나요?
                        {candidate.confidence === 'maybe' && ' (확실하지 않습니다)'}
                      </span>
                      <span className="t-caption block">{candidate.reason}</span>
                    </span>
                    <span className="flex gap-1.5">
                      <button
                        onClick={() => acceptCandidate(index, candidate.id)}
                        className="cursor-pointer whitespace-nowrap rounded bg-transparent px-3
                                   py-1.5 text-xs"
                        style={{
                          border: '1px solid var(--positive)',
                          color: 'var(--positive-ink)',
                        }}
                      >
                        네, 맞아요
                      </button>
                      <button
                        onClick={() =>
                          patchGroup(index, {
                            dismissed: [...group.dismissed, candidate.id],
                          })
                        }
                        className="btn-quiet px-3 py-1.5"
                      >
                        아니요
                      </button>
                    </span>
                  </div>
                ))}
              </div>
            )}

            {/* 기존 추억과의 관계 — 자동으로 병합하지 않는다 (기획안 08) */}
            {draft.related.length > 0 && (
              <div className="mt-6 pt-5" style={{ borderTop: '1px solid var(--border)' }}>
                <p className="t-eyebrow m-0 mb-3 text-ink-300">기존 추억과 관련 있어 보여요</p>
                {draft.related.map((item) => (
                  <div key={item.event_id} className="mb-3">
                    <p className="t-body-sm m-0 text-ink-700">
                      이 기록은 ‘{item.title}’과 관련 있어 보여요.
                    </p>
                    <p className="t-caption m-0 mt-0.5">
                      {item.reason}
                      {item.date_start ? ` · ${item.date_start}` : ''}
                    </p>
                    <button
                      onClick={() => attachToExisting(index, item.event_id, item.title)}
                      disabled={busy}
                      className="btn-outline mt-2 disabled:opacity-40"
                    >
                      기존 추억에 추가
                    </button>
                  </div>
                ))}
                <p className="t-caption m-0">
                  아니면 아래에서 새 추억으로 만들면 됩니다. 자동으로 합치지 않습니다.
                </p>
              </div>
            )}

            <div className="mt-6 flex flex-wrap items-center gap-3">
              <button
                onClick={() => save(index)}
                disabled={!form.title.trim() || busy}
                className="btn-primary disabled:opacity-40"
              >
                {busy ? '만드는 중…' : '이 추억 만들기'}
              </button>
              <p className="t-caption m-0">
                {current?.name ?? '지금 쓰는 사람'}님이 만든 추억으로 바로 게시됩니다
              </p>
            </div>
          </div>
        )
      })}

      {groups.length > 0 && openGroups === 0 && (
        <button onClick={reset} className="btn-link mt-6">
          기록을 더 올리기
        </button>
      )}
    </Page>
  )
}

/** 이미 저장(또는 기존 추억에 붙임)된 기록인가 — 다시 초안에 넣지 않는다 */
function isSaved(mediaId: string, groups: Group[]): boolean {
  return groups.some(
    (g) => (g.created || g.attached) && g.draft.media.some((m) => m.id === mediaId),
  )
}
