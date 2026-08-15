import { useState, useCallback, useEffect } from 'react'
import { Upload, CheckCircle, X, Image, Film, Mic, AlertCircle } from 'lucide-react'
import { uploadMedia, supplementMedia, getEvents, MediaUploadResult, EventListItem } from '../lib/api'

export default function UploadPage() {
  const [dragOver, setDragOver] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [results, setResults] = useState<MediaUploadResult[]>([])
  const [error, setError] = useState<string | null>(null)
  const [events, setEvents] = useState<EventListItem[]>([])
  const [supplementForms, setSupplementForms] = useState<Record<string, { date: string; event_id: string; description: string }>>({})

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

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    handleFiles(e.dataTransfer.files)
  }, [handleFiles])

  const mediaIcon = (type: string) => {
    if (type === 'video') return <Film size={16} className="text-purple-500" />
    if (type === 'audio') return <Mic size={16} className="text-green-500" />
    return <Image size={16} className="text-blue-500" />
  }

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">미디어 업로드</h1>
        <p className="text-gray-500 mt-1">사진, 영상, 음성을 업로드하면 자동으로 분석되어 Memory Graph에 연결됩니다.</p>
      </div>

      {/* Drop Zone */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        className={`border-2 border-dashed rounded-xl p-12 text-center transition-colors cursor-pointer ${
          dragOver ? 'border-primary-400 bg-primary-50' : 'border-gray-300 hover:border-gray-400'
        }`}
        onClick={() => document.getElementById('file-input')?.click()}
      >
        <Upload size={40} className={`mx-auto mb-4 ${dragOver ? 'text-primary-500' : 'text-gray-400'}`} />
        <p className="text-gray-600 font-medium">
          {uploading ? '업로드 중...' : '파일을 끌어오거나 클릭하세요'}
        </p>
        <p className="text-sm text-gray-400 mt-2">사진(JPG, PNG), 영상(MP4, MOV), 음성(MP3, M4A) 지원</p>
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
        <div className="bg-red-50 text-red-700 px-4 py-3 rounded-lg text-sm flex items-center gap-2">
          <X size={16} /> {error}
        </div>
      )}

      {/* Results */}
      {results.length > 0 && (
        <div className="space-y-3">
          <h2 className="text-lg font-semibold text-gray-800">업로드 결과</h2>
          {results.map((result) => (
            <div key={result.id} className="card">
              <div className="flex items-start gap-4">
                {/* Thumbnail */}
                <div className="w-16 h-16 rounded-lg overflow-hidden bg-gray-100 flex-shrink-0">
                  {result.thumbnail_path ? (
                    <img src={result.thumbnail_path} alt="" className="w-full h-full object-cover" />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center">
                      {mediaIcon(result.media_type)}
                    </div>
                  )}
                </div>

                {/* Info */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    {result.needs_info ? (
                      <AlertCircle size={16} className="text-orange-500 flex-shrink-0" />
                    ) : (
                      <CheckCircle size={16} className="text-green-500 flex-shrink-0" />
                    )}
                    <p className="font-medium text-gray-800 truncate">{result.original_filename}</p>
                  </div>
                  <div className="flex flex-wrap gap-2 mt-2">
                    {result.media_type && (
                      <span className="inline-flex items-center gap-1 text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded">
                        {mediaIcon(result.media_type)} {result.media_type}
                      </span>
                    )}
                    {result.exif_date && (
                      <span className="text-xs bg-blue-50 text-blue-600 px-2 py-0.5 rounded">
                        📅 {result.exif_date.slice(0, 10)}
                      </span>
                    )}
                    {result.exif_lat && (
                      <span className="text-xs bg-green-50 text-green-600 px-2 py-0.5 rounded">
                        📍 GPS
                      </span>
                    )}
                    {result.linked_event_id && (
                      <span className="text-xs bg-purple-50 text-purple-600 px-2 py-0.5 rounded">
                        🔗 이벤트 연결됨
                      </span>
                    )}
                    {result.needs_info && (
                      <span className="text-xs bg-orange-50 text-orange-600 px-2 py-0.5 rounded">
                        ⚠️ 추가 정보 필요
                      </span>
                    )}
                  </div>
                </div>
              </div>

              {/* Supplement Form for EXIF-less media */}
              {result.needs_info && !result.linked_event_id && (
                <div className="mt-3 pt-3 border-t border-gray-100">
                  <p className="text-sm text-gray-500 mb-2">EXIF 정보가 없습니다. 아래 정보를 입력해주세요:</p>
                  <div className="grid grid-cols-1 gap-2">
                    <input
                      type="date"
                      placeholder="촬영 날짜"
                      value={supplementForms[result.id]?.date || ''}
                      onChange={(e) => setSupplementForms((prev) => ({
                        ...prev,
                        [result.id]: { ...prev[result.id], date: e.target.value, event_id: prev[result.id]?.event_id || '', description: prev[result.id]?.description || '' },
                      }))}
                      className="px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
                    />
                    <select
                      value={supplementForms[result.id]?.event_id || ''}
                      onChange={(e) => setSupplementForms((prev) => ({
                        ...prev,
                        [result.id]: { ...prev[result.id], event_id: e.target.value, date: prev[result.id]?.date || '', description: prev[result.id]?.description || '' },
                      }))}
                      className="px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
                    >
                      <option value="">기존 이벤트에 연결 (선택)</option>
                      {events.map((ev) => (
                        <option key={ev.id} value={ev.id}>
                          {ev.title} {ev.date_start ? `(${ev.date_start})` : ''}
                        </option>
                      ))}
                    </select>
                    <input
                      type="text"
                      placeholder="사진 설명 (선택)"
                      value={supplementForms[result.id]?.description || ''}
                      onChange={(e) => setSupplementForms((prev) => ({
                        ...prev,
                        [result.id]: { ...prev[result.id], description: e.target.value, date: prev[result.id]?.date || '', event_id: prev[result.id]?.event_id || '' },
                      }))}
                      className="px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
                    />
                    <button
                      onClick={async () => {
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
                                ? { ...r, needs_info: false, linked_event_id: res.linked_event_id || r.linked_event_id, exif_date: form.date || r.exif_date }
                                : r
                            )
                          )
                        } catch (e) {
                          console.error(e)
                        }
                      }}
                      className="btn-primary text-sm"
                    >
                      정보 저장
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
