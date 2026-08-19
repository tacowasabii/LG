import { useState, useCallback, useEffect } from 'react'
import {
  uploadMedia,
  supplementMedia,
  getEvents,
  MediaUploadResult,
  EventListItem,
  mediaUrl,
} from '../lib/api'
import { Page, PageHeader } from '../components/Page'

/**
 * 기록 올리기
 *
 * 읽어낸 정보를 알약 한 줄로 나열한다 — 촬영 시점, GPS, 연결된 사건. 무엇을
 * 읽었는지가 파일 이름보다 중요하고, 읽을 정보가 없으면 추측해서 채우지 않고
 * 그 자리에서 물어본다. "추가 정보 필요"는 오류가 아니라 정직함의 표시이므로
 * 붉은 경고가 아니라 상태 알약으로 조용히 둔다.
 */

const MEDIA_TYPE_LABEL: Record<string, string> = {
  image: '사진',
  video: '영상',
  audio: '음성',
}

export default function UploadPage() {
  const [dragOver, setDragOver] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [results, setResults] = useState<MediaUploadResult[]>([])
  const [error, setError] = useState<string | null>(null)
  const [events, setEvents] = useState<EventListItem[]>([])
  const [supplementForms, setSupplementForms] = useState<
    Record<string, { date: string; event_id: string; description: string }>
  >({})

  useEffect(() => {
    getEvents().then(setEvents).catch(console.error)
  }, [])

  const handleFiles = useCallback(async (files: FileList | null) => {
    if (!files || files.length === 0) return
    setUploading(true)
    setError(null)

    const newResults: MediaUploadResult[] = []
    for (const file of Array.from(files)) {
      try {
        const result = await uploadMedia(file)
        newResults.push(result)
      } catch (e) {
        setError(`${file.name} 업로드 실패`)
      }
    }

    setResults((prev) => [...newResults, ...prev])
    setUploading(false)
  }, [])

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setDragOver(false)
      handleFiles(e.dataTransfer.files)
    },
    [handleFiles],
  )

  const patchForm = (
    id: string,
    patch: Partial<{ date: string; event_id: string; description: string }>,
  ) =>
    setSupplementForms((prev) => {
      const base = prev[id] ?? { date: '', event_id: '', description: '' }
      return { ...prev, [id]: { ...base, ...patch } }
    })

  const saveSupplement = async (result: MediaUploadResult) => {
    const form = supplementForms[result.id]
    if (!form?.date && !form?.event_id) return
    try {
      const res = await supplementMedia({
        media_id: result.id,
        date: form.date || undefined,
        event_id: form.event_id || undefined,
        description: form.description || undefined,
      })
      // 업데이트된 결과 반영
      setResults((prev) =>
        prev.map((r) =>
          r.id === result.id
            ? {
                ...r,
                needs_info: false,
                linked_event_id: res.linked_event_id || r.linked_event_id,
                exif_date: form.date || r.exif_date,
              }
            : r,
        ),
      )
    } catch (e) {
      console.error(e)
    }
  }

  const eventTitle = (id: string) => events.find((e) => e.id === id)?.title || id

  return (
    <Page width={820}>
      <PageHeader
        eyebrow="Upload"
        title="기록 올리기"
        lead="사진·영상·음성을 올리면 촬영 시점과 장소를 읽어 사건에 연결합니다. 읽을 정보가 없으면 추측하지 않고 물어봅니다."
      />

      <div
        onDragOver={(e) => {
          e.preventDefault()
          setDragOver(true)
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => document.getElementById('file-input')?.click()}
        className="mt-9 cursor-pointer rounded-lg px-8 py-16 text-center
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
          사진 JPG · PNG / 영상 MP4 · MOV / 음성 MP3 · M4A
        </p>
        <input
          id="file-input"
          type="file"
          multiple
          accept="image/*,video/*,audio/*"
          className="hidden"
          onChange={(e) => handleFiles(e.target.files)}
        />
      </div>

      {error && (
        <p className="t-body-sm mt-4" style={{ color: 'var(--critical-ink)' }}>
          {error}
        </p>
      )}

      {results.length > 0 && (
        <div className="mt-9">
          <div
            className="flex items-baseline justify-between pb-3"
            style={{ borderBottom: '2px solid var(--ink-700)' }}
          >
            <p className="t-eyebrow m-0">읽은 결과</p>
            <button onClick={() => setResults([])} className="btn-link">
              다시 올리기
            </button>
          </div>

          {results.map((result) => {
            const form = supplementForms[result.id]
            const needsForm = result.needs_info && !result.linked_event_id

            return (
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
                      {result.linked_event_id && (
                        <span
                          className="pill font-normal"
                          style={{
                            background: 'var(--accent-soft)',
                            color: 'var(--accent-ink)',
                          }}
                        >
                          사건 연결 · {eventTitle(result.linked_event_id)}
                        </span>
                      )}
                    </div>
                  </div>

                  <span
                    className="pill px-2.5 py-1"
                    style={
                      result.needs_info
                        ? {
                            background: 'var(--critical-soft)',
                            color: 'var(--critical-ink)',
                          }
                        : {
                            background: 'var(--positive-soft)',
                            color: 'var(--positive-ink)',
                          }
                    }
                  >
                    {result.needs_info ? '추가 정보 필요' : '자동 연결 완료'}
                  </span>
                </div>

                {/* EXIF가 없는 기록 — 추측해서 채우지 않고 아는 것만 받는다 */}
                {needsForm && (
                  <div className="ml-[92px] mt-4 rounded-lg bg-ink-50 p-5">
                    <p className="t-body-sm m-0 mb-3">
                      EXIF 정보가 없습니다. 추측해서 채우지 않습니다. 아는 것만 알려주세요.
                    </p>
                    <div className="flex flex-col gap-2">
                      <input
                        type="date"
                        value={form?.date || ''}
                        onChange={(e) => patchForm(result.id, { date: e.target.value })}
                        className="field field-sm"
                      />
                      <select
                        value={form?.event_id || ''}
                        onChange={(e) => patchForm(result.id, { event_id: e.target.value })}
                        className="field field-sm"
                      >
                        <option value="">기존 사건에 연결 (선택)</option>
                        {events.map((ev) => (
                          <option key={ev.id} value={ev.id}>
                            {ev.title}
                            {ev.date_start ? ` (${ev.date_start})` : ''}
                          </option>
                        ))}
                      </select>
                      <input
                        type="text"
                        placeholder="사진 설명 (선택)"
                        value={form?.description || ''}
                        onChange={(e) => patchForm(result.id, { description: e.target.value })}
                        className="field field-sm"
                      />
                      <button
                        onClick={() => saveSupplement(result)}
                        disabled={!form?.date && !form?.event_id}
                        className="btn-primary mt-1 self-start px-[18px] py-2.5 text-[13px]"
                      >
                        정보 저장
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </Page>
  )
}
