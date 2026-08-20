/**
 * 모으기 — 올리고, 못 읽은 것을 채우고, 첫 질문에 답하는 한 화면
 *
 * 예전에는 "시작하기"와 "업로드"가 따로 있었고 둘 다 같은 일(uploadMedia)을 했다.
 * 나뉘어 있는 동안 기능이 한쪽에만 붙었다 — 시작하기에서는 EXIF 없는 사진을 그
 * 자리에서 채울 수 없고(업로드 화면으로 보냈다), 답변에서 무엇이 그래프에 붙었는지
 * 보여주지도 않았다. 첫 사용자가 보는 화면에서 그 둘이 빠져 있던 셈이다.
 *
 * 그래서 하나로 합쳤다. 화면은 하나고, 그래프가 비어 있을 때만 말투가 달라진다
 * (단계 알약 + "사진 3장으로 시작"). 온보딩은 화면이 아니라 상태다.
 *
 * AI 인터뷰는 합치지 않았다. 사진이 없어도 성립하는 활동이고(부모님 이야기만
 * 녹음하는 경우가 기획안이 말한 핵심 독자 데이터다), 녹음·파형·5문 진행을 여기
 * 얹으면 한 화면이 두 일을 하게 된다. 여기서는 첫 질문 하나만 받고 나머지는
 * 인터뷰 화면으로 넘긴다.
 */

import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  EventListItem,
  ExtractedFromAnswer,
  InterviewStartResult,
  MediaUploadResult,
  getEvents,
  mediaUrl,
  setMediaPersons,
  startInterview,
  submitInterviewAnswer,
  supplementMedia,
  uploadMedia,
} from '../lib/api'
import { useCurrentUser } from '../lib/currentUser'
import { invalidateEvents } from '../lib/useGraphData'
import LearnedFromAnswer from '../components/LearnedFromAnswer'
import RichText from '../components/RichText'
import { Page, PageHeader, StatRow } from '../components/Page'

const MEDIA_TYPE_LABEL: Record<string, string> = {
  // 서버가 내려주는 값은 photo다 (MediaType.PHOTO). image로 적어 두면 알약에
  // 영문이 그대로 노출된다.
  photo: '사진',
  video: '영상',
  audio: '음성',
}

/** 기획안이 정한 콜드스타트 크기 — "사진 3장으로 시작" */
const FIRST_PICK = 3

const STEPS = ['올리기', '채우기', '첫 질문']

interface SupplementForm {
  date: string
  event_id: string
  description: string
}

export default function CollectPage() {
  const { current, members } = useCurrentUser()
  const [events, setEvents] = useState<EventListItem[]>([])
  /** 그래프가 비었는가 — 말투를 정한다 (첫 사용인지 아닌지) */
  const [firstTime, setFirstTime] = useState(false)

  const [dragOver, setDragOver] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [results, setResults] = useState<MediaUploadResult[]>([])
  const [error, setError] = useState<string | null>(null)
  const [supplementForms, setSupplementForms] = useState<Record<string, SupplementForm>>({})
  /** 기록별로 지목된 사람. 얼굴 인식이 없으므로 여기가 detected_faces의 출처다 */
  const [personTags, setPersonTags] = useState<Record<string, string[]>>({})
  /** 지금 저장 중인 기록 — 연달아 누를 때 응답이 엇갈리지 않게 */
  const [tagging, setTagging] = useState<string | null>(null)

  // 올린 뒤 이어지는 첫 질문 (실제 인터뷰 세션이다)
  const [session, setSession] = useState<InterviewStartResult | null>(null)
  const [answer, setAnswer] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [learned, setLearned] = useState<ExtractedFromAnswer | null>(null)
  const [answered, setAnswered] = useState(false)

  useEffect(() => {
    getEvents()
      .then((list) => {
        setEvents(list)
        setFirstTime(list.length === 0)
      })
      .catch(console.error)
  }, [])

  const handleFiles = useCallback(async (files: FileList | null) => {
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

    // 올린 것이 사건에 붙었으니 다른 화면도 다시 받아야 한다
    invalidateEvents()
    getEvents().then(setEvents).catch(console.error)

    // 올린 것을 바탕으로 AI가 물을 것을 고른다. 질문을 못 가져와도 올린 것은 남는다.
    if (!session) {
      try {
        setSession(await startInterview('auto'))
      } catch (e) {
        console.error(e)
      }
    }
  }, [session])

  /**
   * 이 기록에 있는 사람을 켜고 끈다. 켠 결과 전체를 서버에 보낸다.
   *
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
      // 서버가 걸러낸 결과로 맞춘다 (그래프에 없는 사람은 버려진다)
      const res = await setMediaPersons(mediaId, next)
      setPersonTags((prev) => ({ ...prev, [mediaId]: res.detected_faces }))
      invalidateEvents()
    } catch (e) {
      console.error(e)
      setPersonTags((prev) => ({ ...prev, [mediaId]: before }))
      setError('사람을 저장하지 못했습니다.')
    } finally {
      setTagging(null)
    }
  }

  const patchForm = (id: string, patch: Partial<SupplementForm>) =>
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
      invalidateEvents()
    } catch (e) {
      console.error(e)
      setError('정보를 저장하지 못했습니다.')
    }
  }

  const submitAnswer = async () => {
    if (!session || !answer.trim() || submitting) return
    setSubmitting(true)
    try {
      const result = await submitInterviewAnswer(session.session_id, answer.trim(), current?.id)
      setLearned(result.extracted ?? null)
      setAnswered(true)
      setAnswer('')
      invalidateEvents()
    } catch (e) {
      console.error(e)
      setError('기억을 남기지 못했습니다. 다시 시도해 주세요.')
    } finally {
      setSubmitting(false)
    }
  }

  const eventTitle = (id: string) => events.find((e) => e.id === id)?.title || id
  const linkedCount = results.filter((r) => r.linked_event_id).length
  const needsInfo = results.filter((r) => r.needs_info).length

  // 단계 표시는 실제 상태에서 파생한다 (가짜 진행률을 쓰지 않는다)
  const step = answered ? 3 : results.length === 0 ? 0 : needsInfo > 0 ? 1 : 2

  return (
    <Page width={820}>
      <PageHeader
        eyebrow="Collect"
        title={firstTime ? '사진 3장으로 시작합니다' : '기록 모으기'}
        lead={
          firstTime
            ? '한 번에 전부 정리하지 않아도 됩니다. 첫 기록만 올리고, 나머지는 질문에 답하면서 채워집니다.'
            : '사진·영상·음성을 올리면 촬영 시점과 장소를 읽어 사건에 연결합니다. 읽을 정보가 없으면 추측하지 않고 물어봅니다.'
        }
      />

      {/* 첫 사용일 때만 단계를 세워 준다. 이미 쌓인 가족에게는 군더더기다 */}
      {firstTime && (
        <div className="mt-8 flex flex-wrap items-center gap-2">
          {STEPS.map((label, i) => (
            <span
              key={label}
              className="flex items-center gap-[7px] rounded-full px-3.5 py-[7px] text-xs"
              style={
                i === step
                  ? {
                      background: 'var(--accent-soft)',
                      color: 'var(--accent-ink)',
                      fontWeight: 600,
                    }
                  : i < step
                    ? { background: 'var(--positive-soft)', color: 'var(--positive-ink)' }
                    : { background: 'var(--ink-50)', color: 'var(--ink-300)' }
              }
            >
              <span className="t-mono text-[10px] text-current">{i < step ? '✓' : i + 1}</span>
              {label}
            </span>
          ))}
        </div>
      )}

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
            ? `가장 오래된 사진 ${FIRST_PICK}장으로 시작해도 충분합니다 · JPG · PNG · MP4 · M4A`
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

      {firstTime && results.length === 0 && (
        <p className="t-caption mt-4 max-w-[62ch]">
          촬영 시점이 남아 있는 사진이면 AI가 사건을 스스로 묶습니다. 스캔한 옛 사진처럼
          시점이 없으면 이 화면에서 바로 알려주면 됩니다. 추정한 정보는 확정하지 않고 확인
          요청으로 넘어갑니다.
        </p>
      )}

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
              목록 비우기
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

                {/* 누가 있는지는 자동으로 알 수 없다 — 가족이 직접 지목한다.
                    음성은 찍힌 사람이 아니라 말한 사람이므로 여기서 다루지 않는다
                    (녹음은 speaker_id로 이어진다). */}
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
                                ? {
                                    background: 'var(--accent-soft)',
                                    color: 'var(--accent-ink)',
                                  }
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

          {firstTime && (
            <div className="mt-7">
              <StatRow
                size={36}
                cells={[
                  { value: results.length, label: '올린 기록' },
                  { value: linkedCount, label: '사건 연결' },
                  { value: needsInfo, label: '정보 필요' },
                ]}
              />
            </div>
          )}
        </div>
      )}

      {/* 올린 것을 바탕으로 AI가 묻는 첫 질문. 나머지 질문은 인터뷰 화면에서 */}
      {session && !answered && (
        <div className="surface mt-9 p-7">
          <p className="t-caption m-0">
            {current?.name ?? '지금 쓰는 사람'}님께 묻습니다 · 이 답변은 그 사람의 기억으로
            저장됩니다
          </p>
          <p className="m-0 mt-2.5 whitespace-pre-wrap text-[19px] font-semibold leading-normal text-ink-900">
            <RichText text={session.question} />
          </p>

          <textarea
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
            rows={3}
            placeholder="말하듯이 적어도 됩니다."
            className="field mt-5 w-full"
          />

          <div className="mt-4 flex flex-wrap items-center justify-between gap-4">
            <Link to="/interview" className="t-caption text-accent-ink">
              목소리로 남기려면 AI 인터뷰에서 말로 답하기 →
            </Link>
            <button
              onClick={submitAnswer}
              disabled={!answer.trim() || submitting}
              className="btn-primary disabled:opacity-40"
            >
              {submitting ? '남기는 중…' : '기억 남기기'}
            </button>
          </div>
        </div>
      )}

      {answered && (
        <div className="mt-9">
          <p className="m-0 text-2xl font-bold tracking-[-0.02em] text-ink-900">
            {firstTime ? '첫 기록이 들어왔습니다' : '기억이 기록되었습니다'}
          </p>

          {/* 답변에서 무엇이 그래프에 붙었는지 — 인터뷰 화면과 같은 것을 보여준다 */}
          {learned && <LearnedFromAnswer learned={learned} className="mt-4" />}

          {needsInfo > 0 && (
            <p className="t-body-sm mt-5 max-w-[62ch]">
              촬영 시점이 없는 기록 {needsInfo}개는 아직 사건에 붙지 못했습니다. 위 목록에서
              날짜나 사건을 알려주면 연결됩니다.
            </p>
          )}

          <p className="t-eyebrow mb-3 mt-9">이어서 하면 좋은 것</p>
          <div className="grid grid-cols-3 gap-3">
            {[
              { to: '/interview', label: '이어서 질문에 답하기' },
              { to: '/verify', label: 'AI가 추정한 것을 확인하기' },
              { to: '/chat', label: '기억에 물어보기' },
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

          <button
            onClick={() => {
              setAnswered(false)
              setLearned(null)
              setSession(null)
            }}
            className="btn-link mt-6"
          >
            기록을 더 올리기
          </button>
        </div>
      )}
    </Page>
  )
}
