/**
 * 모으기 — 올리면 AI가 초안을 쓰고, 확인하면 그 자리에서 추억이 된다
 *
 * 예전 흐름은 "올리기 → 채우기 → 첫 질문"이었다. 올린 사진은 EXIF로 사건에
 * 자동으로 묶이고(또는 "2015년 기록" 같은 빈 사건이 새로 생기고), 그 추정은
 * 확인 요청으로 넘어가 가족이 판정해야 했다.
 *
 * 지금은 이렇다.
 *
 *   올리기 → AI 초안(제목·날짜·장소·함께한 가족·설명) → 고치거나 그대로 저장
 *
 * 저장하면 끝이다. 다른 가족의 승인을 기다리지 않는다. 대신 AI가 무엇을 근거로
 * 그렇게 썼는지 화면에 그대로 펼친다 — 촬영 시점, 좌표, 지목된 사람, 기존 가족
 * 기록. 사용자가 어디까지가 사실이고 어디부터가 추정인지 볼 수 있어야 한다.
 *
 * 확정하지 않는 것 둘.
 *   1. 인물 추정은 "이 사진들에 엄마도 있나요?"로 되묻는다 (기획안 06).
 *   2. 기존 추억과 관련 있어 보이면 알려 주고, 붙일지 새로 만들지는 사용자가
 *      고른다. 자동으로 병합하지 않는다 (기획안 08).
 */

import { useCallback, useState } from 'react'
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
import { useCurrentUser } from '../lib/currentUser'
import { invalidateEvents } from '../lib/useGraphData'
import { Page, PageHeader } from '../components/Page'

const MEDIA_TYPE_LABEL: Record<string, string> = {
  photo: '사진',
  video: '영상',
  audio: '음성',
}

/** 콜드스타트 크기 — "사진 3장으로 시작" */
const FIRST_PICK = 3

interface DraftForm {
  title: string
  date_start: string
  place_name: string
  /** 그래프에 있는 장소를 그대로 쓰는 경우. 이름을 고치면 비워진다 */
  place_id: string | null
  description: string
  person_ids: string[]
}

export default function CollectPage() {
  const { current, members } = useCurrentUser()

  const [dragOver, setDragOver] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [results, setResults] = useState<MediaUploadResult[]>([])
  const [error, setError] = useState<string | null>(null)

  /** 기록별로 지목된 사람. 얼굴 인식이 없으므로 여기가 detected_faces의 출처다 */
  const [personTags, setPersonTags] = useState<Record<string, string[]>>({})
  const [tagging, setTagging] = useState<string | null>(null)

  // AI 초안
  const [draft, setDraft] = useState<MemoryDraft | null>(null)
  const [form, setForm] = useState<DraftForm | null>(null)
  const [drafting, setDrafting] = useState(false)
  const [saving, setSaving] = useState(false)
  /** 만들어진 추억 (여기까지 오면 이미 가족 공간에 게시된 상태다) */
  const [created, setCreated] = useState<{ id: string; title: string } | null>(null)
  const [attachedTo, setAttachedTo] = useState<{ id: string; title: string } | null>(null)
  /** 인물 후보 중 "아니요"로 넘긴 사람 (다시 묻지 않는다) */
  const [dismissed, setDismissed] = useState<string[]>([])

  const visualIds = results.filter((r) => r.media_type !== 'audio').map((r) => r.id)

  const buildForm = (next: MemoryDraft): DraftForm => ({
    title: next.title,
    date_start: (next.date_start || '').slice(0, 10),
    place_name: next.place?.name || '',
    place_id: next.place?.id || null,
    description: next.description,
    person_ids: next.person_ids,
  })

  const makeDraft = useCallback(async (mediaIds: string[]) => {
    if (mediaIds.length === 0) return
    setDrafting(true)
    setError(null)
    try {
      const next = await draftMemory(mediaIds)
      setDraft(next)
      setForm(buildForm(next))
    } catch (e) {
      console.error(e)
      setError('초안을 만들지 못했습니다. 아래에서 직접 적어도 됩니다.')
    } finally {
      setDrafting(false)
    }
  }, [])

  const handleFiles = useCallback(
    async (files: FileList | null) => {
      if (!files || files.length === 0) return
      setUploading(true)
      setError(null)
      setCreated(null)
      setAttachedTo(null)

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

      // 올린 것 전체로 초안을 만든다 (한 묶음이 하나의 추억이 되는 것이 기본이다)
      const all = [...uploaded, ...results].map((r) => r.id)
      await makeDraft(all)
    },
    [makeDraft, results],
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
      // 초안의 "함께한 가족"도 따라간다 (같은 사실을 두 곳에서 따로 관리하지 않는다)
      setForm((prev) =>
        prev
          ? {
              ...prev,
              person_ids: Array.from(
                new Set([
                  ...prev.person_ids.filter((id) => id !== personId),
                  ...(res.detected_faces.includes(personId) ? [personId] : []),
                ]),
              ),
            }
          : prev,
      )
    } catch (e) {
      console.error(e)
      setPersonTags((prev) => ({ ...prev, [mediaId]: before }))
      setError('사람을 저장하지 못했습니다.')
    } finally {
      setTagging(null)
    }
  }

  /** AI가 되물은 인물을 "네"로 받는다 — 추억의 함께한 가족에 넣고 사진에도 지목한다 */
  const acceptCandidate = async (personId: string) => {
    setForm((prev) =>
      prev ? { ...prev, person_ids: Array.from(new Set([...prev.person_ids, personId])) } : prev,
    )
    setDismissed((prev) => [...prev, personId])

    for (const mediaId of visualIds) {
      const current = personTags[mediaId] ?? []
      if (current.includes(personId)) continue
      try {
        const res = await setMediaPersons(mediaId, [...current, personId])
        setPersonTags((prev) => ({ ...prev, [mediaId]: res.detected_faces }))
      } catch (e) {
        console.error(e)
      }
    }
  }

  const save = async () => {
    if (!form || saving) return
    setSaving(true)
    setError(null)
    try {
      const res = await createMemory({
        title: form.title,
        description: form.description,
        date_start: form.date_start || null,
        place_id: form.place_id,
        place_name: form.place_id ? null : form.place_name || null,
        lat: draft?.lat ?? null,
        lng: draft?.lng ?? null,
        person_ids: form.person_ids,
        media_ids: results.map((r) => r.id),
      })
      invalidateEvents()
      setCreated({ id: res.event_id, title: form.title })
      setDraft(null)
      setForm(null)
    } catch (e) {
      console.error(e)
      setError('추억을 만들지 못했습니다. 다시 시도해 주세요.')
    } finally {
      setSaving(false)
    }
  }

  /** 기존 추억에 사진만 더한다 (새 추억을 만들지 않는다) */
  const attachToExisting = async (eventId: string, title: string) => {
    setSaving(true)
    setError(null)
    try {
      await addMediaToMemory(eventId, results.map((r) => r.id))
      invalidateEvents()
      setAttachedTo({ id: eventId, title })
      setDraft(null)
      setForm(null)
    } catch (e) {
      console.error(e)
      setError('기존 추억에 더하지 못했습니다.')
    } finally {
      setSaving(false)
    }
  }

  const reset = () => {
    setResults([])
    setPersonTags({})
    setDraft(null)
    setForm(null)
    setCreated(null)
    setAttachedTo(null)
    setDismissed([])
  }

  const firstTime = results.length === 0 && !created && !attachedTo
  const candidates = (draft?.person_candidates || []).filter(
    (c) => !dismissed.includes(c.id) && !(form?.person_ids || []).includes(c.id),
  )

  return (
    <Page width={820}>
      <PageHeader
        eyebrow="Collect"
        title="사진을 올리면 AI가 추억을 씁니다"
        lead="촬영 시점·장소·함께한 가족과 기존 가족 기록을 읽어 초안을 만듭니다. 확인하고 저장하면 바로 가족 공간에 남습니다 — 다른 가족의 확인을 기다리지 않습니다."
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
            ? `사진 ${FIRST_PICK}장으로 시작해도 충분합니다 · JPG · PNG · MP4 · M4A`
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
        <p className="t-caption mt-4 max-w-[62ch]">
          한 번에 올린 사진은 하나의 추억 초안으로 묶입니다. 촬영 시점이 없는 옛 사진이면
          날짜 칸을 비워 두고 아는 것만 적으면 됩니다 — 추측해서 채우지 않습니다.
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
                    {result.exif_date && (
                      <span className="pill bg-ink-50 font-normal text-ink-500">
                        촬영 {result.exif_date.slice(0, 10)}
                      </span>
                    )}
                    {result.exif_lat != null && (
                      <span className="pill bg-ink-50 font-normal text-ink-500">
                        GPS 좌표 있음
                      </span>
                    )}
                    {!result.exif_date && (
                      <span className="pill bg-ink-50 font-normal text-ink-500">
                        촬영 시점 없음
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
                    이 {MEDIA_TYPE_LABEL[result.media_type] || '기록'}에 누가 있나요? 지목한
                    사람만 그래프에 이어집니다.
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

          {!draft && !created && !attachedTo && (
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

      {/* AI 초안 — 고치거나 그대로 저장한다 */}
      {form && draft && (
        <div className="surface mt-9 p-7">
          <div className="flex flex-wrap items-baseline justify-between gap-3">
            <p className="t-eyebrow m-0">AI 초안</p>
            <button
              onClick={() => makeDraft(results.map((r) => r.id))}
              disabled={drafting}
              className="btn-link disabled:opacity-40"
            >
              {drafting ? '다시 쓰는 중…' : '다시 만들기'}
            </button>
          </div>
          <p className="t-caption m-0 mt-2 max-w-[62ch]">
            {draft.ai_used
              ? 'AI가 읽어낸 사실만으로 썼습니다. 마음에 들지 않으면 고치세요 — 저장하는 것은 고친 결과입니다.'
              : '모델을 부르지 못해 읽어낸 사실로만 만들었습니다. 문장은 직접 다듬어 주세요.'}
          </p>

          {/* 무엇을 근거로 썼는가 */}
          {draft.evidence.length > 0 && (
            <div className="mt-5 rounded bg-ink-50 px-4 py-3.5">
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
                onChange={(e) => setForm({ ...form, title: e.target.value })}
                className="field field-sm min-w-0 flex-1"
              />
            </label>

            <label className="flex flex-wrap items-center gap-2.5">
              <span className="t-caption w-[68px] shrink-0">날짜</span>
              <input
                type="date"
                value={form.date_start}
                onChange={(e) => setForm({ ...form, date_start: e.target.value })}
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
                  setForm({ ...form, place_name: e.target.value, place_id: null })
                }
                className="field field-sm min-w-0 flex-1"
              />
            </label>

            <label className="flex flex-wrap items-start gap-2.5">
              <span className="t-caption mt-2 w-[68px] shrink-0">설명</span>
              <textarea
                value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
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
                        setForm({
                          ...form,
                          person_ids: on
                            ? form.person_ids.filter((id) => id !== m.id)
                            : [...form.person_ids, m.id],
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
                <div
                  key={candidate.id}
                  className="mb-2.5 flex flex-wrap items-center gap-3"
                >
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
                      이 사진에 {candidate.relation || candidate.name}(
                      {candidate.name})도 있나요?
                      {candidate.confidence === 'maybe' && ' (확실하지 않습니다)'}
                    </span>
                    <span className="t-caption block">{candidate.reason}</span>
                  </span>
                  <span className="flex gap-1.5">
                    <button
                      onClick={() => acceptCandidate(candidate.id)}
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
                      onClick={() => setDismissed((prev) => [...prev, candidate.id])}
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
                    onClick={() => attachToExisting(item.event_id, item.title)}
                    disabled={saving}
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
              onClick={save}
              disabled={!form.title.trim() || saving}
              className="btn-primary disabled:opacity-40"
            >
              {saving ? '만드는 중…' : '이 추억 만들기'}
            </button>
            <p className="t-caption m-0">
              {current?.name ?? '지금 쓰는 사람'}님이 만든 추억으로 바로 게시됩니다
            </p>
          </div>
        </div>
      )}

      {/* 만든 뒤 */}
      {created && (
        <div className="mt-9">
          <p className="m-0 text-2xl font-bold tracking-[-0.02em] text-ink-900">
            가족 공간에 올라갔습니다
          </p>
          <p className="t-body-sm mt-2 max-w-[62ch]">
            ‘{created.title}’이 가족 기록으로 남았습니다. 다른 가족은 확인할 의무가 없고,
            기억나는 것이 있을 때만 자기 기억을 더합니다.
          </p>

          <div className="mt-7 grid grid-cols-3 gap-3">
            {[
              { to: `/memory/${created.id}`, label: '만든 추억 보기' },
              { to: '/continue', label: '가족의 추억에 기억 더하기' },
              { to: '/interview', label: '이야기를 목소리로 남기기' },
            ].map((next) => (
              <Link
                key={next.to}
                to={next.to}
                className="surface hover-border-accent p-5 text-sm text-ink-700
                           no-underline hover:no-underline"
              >
                {next.label}
                <span className="mt-1.5 block text-accent-ink">→</span>
              </Link>
            ))}
          </div>

          <button onClick={reset} className="btn-link mt-6">
            기록을 더 올리기
          </button>
        </div>
      )}

      {attachedTo && (
        <div className="mt-9">
          <p className="m-0 text-2xl font-bold tracking-[-0.02em] text-ink-900">
            기존 추억에 더했습니다
          </p>
          <p className="t-body-sm mt-2 max-w-[62ch]">
            ‘{attachedTo.title}’에 올린 기록이 들어갔습니다. 원래 있던 기억은 그대로입니다.
          </p>
          <div className="mt-5 flex gap-3">
            <Link
              to={`/memory/${attachedTo.id}`}
              className="btn-primary no-underline hover:no-underline"
            >
              그 추억 보기
            </Link>
            <button onClick={reset} className="btn-quiet">
              기록을 더 올리기
            </button>
          </div>
        </div>
      )}
    </Page>
  )
}
