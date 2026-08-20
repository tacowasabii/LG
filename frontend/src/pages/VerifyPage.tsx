import { useEffect, useState } from 'react'
import {
  EventCorrections,
  InboxItem,
  PlaceOption,
  getVerificationInbox,
  verifyEvent,
} from '../lib/api'
import { STATE_CONFIG } from '../components/StatusPill'
import { invalidateEvents } from '../lib/useGraphData'
import { Page, PageHeader } from '../components/Page'
import { useCurrentUser } from '../lib/currentUser'
import { mediaUrl } from '../lib/api'

/**
 * Verification Inbox — 기획안 STEP 04 "확인하기"
 *
 * AI가 연결한 사실을 가족이 맞음 / 수정 / 모름 / 이견으로 판정한다.
 *
 * 수정과 이견을 나눠 둔 것이 이 화면의 핵심이다. 수정은 AI가 잘못 넣은 값을
 * 바로잡는 것(날짜가 틀렸다)이고, 이견은 사람마다 다른 기억(나는 다르게 기억한다)
 * 이다. 앞은 덮어쓰고 뒤는 지우지 않고 함께 보존된다. 수정에는 누가 무엇을 무엇으로
 * 바꿨는지가 함께 남아 나중에 되짚을 수 있다.
 *
 * 확인 이력을 따로 모아 뱃지 줄로 보여주던 것을 없앴다. 같은 정보가 사람 목록과
 * 뱃지 줄에 두 번 나오면 "지금 누가 답을 안 했는지"를 두 곳을 대조해서 세게 된다.
 * 이제 판정은 그 사람의 줄에서 버튼이 결과 문장으로 바뀌는 것으로만 나타난다.
 */

type Verdict = 'confirm' | 'correct' | 'unknown' | 'dispute'

const VERDICT_TEXT: Record<Verdict, { label: string; color: string }> = {
  confirm: { label: '맞음으로 확인', color: 'var(--positive-ink)' },
  correct: { label: '값을 고쳤습니다', color: 'var(--accent-ink)' },
  unknown: { label: '모름', color: 'var(--ink-400)' },
  dispute: { label: '다른 기억을 남겼습니다', color: 'var(--critical-ink)' },
}

/** 고친 항목을 사람이 읽는 말로 */
const FIELD_LABEL: Record<string, string> = {
  title: '제목',
  date_start: '날짜',
  description: '설명',
  location_id: '장소',
}

interface CorrectForm {
  personId: string
  title: string
  date_start: string
  description: string
  location_id: string
}

export default function VerifyPage() {
  const { members } = useCurrentUser()
  const [items, setItems] = useState<InboxItem[]>([])
  const [places, setPlaces] = useState<PlaceOption[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState<string | null>(null)
  const [messages, setMessages] = useState<Record<string, string>>({})
  // 이견 입력창을 펼친 이벤트 -> {personId, note}
  const [disputeForms, setDisputeForms] = useState<
    Record<string, { personId: string; note: string }>
  >({})
  // 수정 폼을 펼친 이벤트 -> 고칠 값. 지금 값으로 채워 둔다 — 빈 칸에서 시작하면
  // 저장할 때 멀쩡한 값이 지워진다.
  const [correctForms, setCorrectForms] = useState<Record<string, CorrectForm>>({})

  const load = () =>
    getVerificationInbox()
      .then((res) => {
        setItems(res.items)
        setPlaces(res.places || [])
      })
      .catch(console.error)

  /** 장소 id를 이름으로 (수정 이력에 id를 그대로 보여주면 읽을 수 없다) */
  const placeName = (id?: string | null) => {
    if (!id) return '없음'
    return places.find((p) => p.id === id)?.name || id
  }

  useEffect(() => {
    load().finally(() => setLoading(false))
  }, [])

  const act = async (
    eventId: string,
    personId: string,
    action: Verdict,
    note?: string,
    corrections?: EventCorrections,
  ) => {
    setBusy(eventId)
    try {
      const res = await verifyEvent(eventId, personId, action, note, corrections)
      // 확인 상태가 바뀌면 홈·지도·TV의 뱃지도 함께 바뀌어야 한다
      invalidateEvents()
      setMessages((prev) => ({ ...prev, [eventId]: res.message }))
      setDisputeForms((prev) => {
        const next = { ...prev }
        delete next[eventId]
        return next
      })
      setCorrectForms((prev) => {
        const next = { ...prev }
        delete next[eventId]
        return next
      })
      await load()
    } catch (e) {
      console.error(e)
      // 서버가 이유를 보낸다 (없는 장소·바뀐 값 없음). 삼켜 버리면 사용자는
      // 왜 저장이 안 됐는지 모른다.
      const message = e instanceof Error ? e.message : String(e)
      const detail = message.match(/"detail"\s*:\s*"([^"]+)"/)
      setMessages((prev) => ({
        ...prev,
        [eventId]: detail ? detail[1] : '기록에 실패했어요. 다시 시도해 주세요.',
      }))
    } finally {
      setBusy(null)
    }
  }

  /** 지금 값으로 채운 수정 폼을 연다 */
  const openCorrectForm = (item: InboxItem, personId: string) =>
    setCorrectForms((prev) => ({
      ...prev,
      [item.event_id]: {
        personId,
        title: item.event_title || '',
        date_start: item.date_start || '',
        description: item.description || '',
        location_id: item.place?.id || '',
      },
    }))

  const submitCorrection = (item: InboxItem, form: CorrectForm) =>
    act(item.event_id, form.personId, 'correct', undefined, {
      title: form.title,
      // 빈 칸은 "값 없음"이다. 빈 문자열로 보내면 서버가 날짜로 읽으려 한다.
      date_start: form.date_start || null,
      description: form.description,
      location_id: form.location_id || null,
    })

  /** 사람 사진은 가족 공간 구성원에서 찾는다 */
  const photoOf = (id: string) => members.find((m) => m.id === id)?.thumbnail_url || null

  if (loading) {
    return (
      <Page width={860}>
        <p className="t-caption">불러오는 중…</p>
      </Page>
    )
  }

  const pending = items.filter((i) => i.state === 'inferred' || i.state === 'conflicted').length

  return (
    <Page width={860}>
      <PageHeader
        eyebrow="Verification Inbox"
        title="확인 요청"
        lead="AI가 연결한 사실을 가족이 확인합니다. 기억이 다르면 지우지 않고 함께 보존합니다."
      />
      {pending > 0 && (
        <p className="t-mono mt-4 text-xs text-accent-ink">확인이 필요한 사건 {pending}건</p>
      )}

      {items.length === 0 ? (
        <div className="mt-8">
          <p className="t-body-sm m-0 text-ink-300">확인할 사건이 없습니다.</p>
          <p className="t-caption m-0 mt-1">
            사진을 올리면 AI가 연결한 사실이 여기에 쌓입니다.
          </p>
        </div>
      ) : (
        <div className="mt-8 flex flex-col gap-4">
          {items.map((item) => {
            const config = STATE_CONFIG[item.state]
            const form = disputeForms[item.event_id]
            const isBusy = busy === item.event_id

            // 참여자별 판정을 확인 이력에서 되짚는다
            const verdictOf = (personId: string): Verdict | null => {
              if (item.confirmed_by.some((p) => p.id === personId)) return 'confirm'
              if (item.corrected_by.some((p) => p.id === personId)) return 'correct'
              if (item.disputed_by.some((p) => p.id === personId)) return 'dispute'
              if (item.unknown_by.some((p) => p.id === personId)) return 'unknown'
              return null
            }

            const correctForm = correctForms[item.event_id]

            return (
              <div key={item.event_id} className="surface p-7">
                <div className="flex items-start justify-between gap-5">
                  <div>
                    <p className="m-0 text-[19px] font-semibold text-ink-900">
                      {item.event_title}
                    </p>
                    <p className="t-body-sm m-0 mt-1 text-ink-400">
                      {item.date_start || '날짜 미상'}
                    </p>
                  </div>
                  <span className="pill" style={{ background: config.bg, color: config.fg }}>
                    {config.label}
                  </span>
                </div>

                <p className="t-caption m-0 mt-2.5">{config.hint}</p>

                {/* 관점별 기억 — 충돌해도 한쪽으로 정리하지 않는다 */}
                {item.memories.length > 0 && (
                  <div className="mt-5 pt-5" style={{ borderTop: '1px solid var(--border)' }}>
                    <p className="t-eyebrow m-0 mb-3 text-ink-300">
                      기억 {item.memories.length}개
                      {item.memories.length > 1 && ' · 관점별로 나란히 보존됩니다'}
                    </p>
                    {item.memories.map((m) => (
                      <div key={m.id} className="mb-2 rounded bg-ink-50 px-4 py-3.5">
                        {m.contributor_name && (
                          <p className="t-caption m-0 mb-1 text-accent-ink">
                            {m.contributor_name}
                          </p>
                        )}
                        <p className="t-body-sm m-0 text-ink-700">{m.content}</p>
                      </div>
                    ))}
                  </div>
                )}

                <div className="mt-5 pt-5" style={{ borderTop: '1px solid var(--border)' }}>
                  <p className="t-eyebrow m-0 mb-3.5 text-ink-300">누구의 확인인가요</p>
                  <div className="flex flex-col gap-2.5">
                    {item.participants.map((p) => {
                      const verdict = verdictOf(p.id)
                      const photo = photoOf(p.id)

                      return (
                        <div key={p.id} className="flex flex-wrap items-center gap-3">
                          {photo ? (
                            <img
                              src={mediaUrl(photo)}
                              alt=""
                              className="h-[26px] w-[26px] rounded-full bg-ink-50 object-cover"
                            />
                          ) : (
                            <span
                              className="flex h-[26px] w-[26px] items-center justify-center
                                         rounded-full bg-ink-50 text-[10px] text-ink-300"
                            >
                              {p.name.slice(0, 1)}
                            </span>
                          )}
                          <span className="w-[88px] text-sm text-ink-700">
                            {p.name}
                            <span className="t-caption ml-1.5 text-ink-300">{p.relation}</span>
                          </span>

                          {verdict ? (
                            <span
                              className="t-body-sm"
                              style={{ color: VERDICT_TEXT[verdict].color }}
                            >
                              {VERDICT_TEXT[verdict].label}
                            </span>
                          ) : (
                            <span className="flex gap-1.5">
                              <button
                                disabled={isBusy}
                                onClick={() => act(item.event_id, p.id, 'confirm')}
                                className="cursor-pointer whitespace-nowrap rounded bg-transparent
                                           px-3 py-1.5 text-xs disabled:opacity-40"
                                style={{
                                  border: '1px solid var(--positive)',
                                  color: 'var(--positive-ink)',
                                }}
                              >
                                맞음
                              </button>
                              <button
                                disabled={isBusy}
                                onClick={() => openCorrectForm(item, p.id)}
                                className="cursor-pointer whitespace-nowrap rounded bg-transparent
                                           px-3 py-1.5 text-xs disabled:opacity-40"
                                style={{
                                  border: '1px solid var(--accent)',
                                  color: 'var(--accent-ink)',
                                }}
                              >
                                값이 틀렸어요
                              </button>
                              <button
                                disabled={isBusy}
                                onClick={() => act(item.event_id, p.id, 'unknown')}
                                className="btn-quiet px-3 py-1.5 disabled:opacity-40"
                              >
                                모름
                              </button>
                              <button
                                disabled={isBusy}
                                onClick={() =>
                                  setDisputeForms((prev) => ({
                                    ...prev,
                                    [item.event_id]: { personId: p.id, note: '' },
                                  }))
                                }
                                className="cursor-pointer whitespace-nowrap rounded bg-transparent
                                           px-3 py-1.5 text-xs disabled:opacity-40"
                                style={{
                                  border: '1px solid var(--critical)',
                                  color: 'var(--critical-ink)',
                                }}
                              >
                                내 기억은 달라요
                              </button>
                            </span>
                          )}
                        </div>
                      )
                    })}
                  </div>
                </div>

                {/* 수정 — AI가 잘못 넣은 값을 바로잡는다. 이견과 달리 덮어쓴다 */}
                {correctForm && (
                  <div className="mt-5 pt-5" style={{ borderTop: '1px solid var(--border)' }}>
                    <p className="t-body-sm m-0 mb-1">
                      {item.participants.find((p) => p.id === correctForm.personId)?.name}님이
                      고칩니다. 무엇을 무엇으로 바꿨는지 함께 기록됩니다.
                    </p>
                    <p className="t-caption m-0 mb-3.5">
                      기억이 서로 다른 경우는 여기가 아니라 “내 기억은 달라요”입니다 — 그건
                      지우지 않고 함께 보존합니다.
                    </p>

                    <div className="flex flex-col gap-2.5">
                      <label className="flex flex-wrap items-center gap-2.5">
                        <span className="t-caption w-[52px] shrink-0">제목</span>
                        <input
                          value={correctForm.title}
                          onChange={(e) =>
                            setCorrectForms((prev) => ({
                              ...prev,
                              [item.event_id]: { ...correctForm, title: e.target.value },
                            }))
                          }
                          className="field field-sm min-w-0 flex-1"
                        />
                      </label>

                      <label className="flex flex-wrap items-center gap-2.5">
                        <span className="t-caption w-[52px] shrink-0">날짜</span>
                        <input
                          type="date"
                          value={correctForm.date_start}
                          onChange={(e) =>
                            setCorrectForms((prev) => ({
                              ...prev,
                              [item.event_id]: { ...correctForm, date_start: e.target.value },
                            }))
                          }
                          className="field field-sm min-w-0 flex-1"
                        />
                      </label>

                      <label className="flex flex-wrap items-center gap-2.5">
                        <span className="t-caption w-[52px] shrink-0">장소</span>
                        <select
                          value={correctForm.location_id}
                          onChange={(e) =>
                            setCorrectForms((prev) => ({
                              ...prev,
                              [item.event_id]: { ...correctForm, location_id: e.target.value },
                            }))
                          }
                          className="field field-sm min-w-0 flex-1"
                        >
                          <option value="">장소 없음</option>
                          {places.map((place) => (
                            <option key={place.id} value={place.id}>
                              {place.name}
                            </option>
                          ))}
                        </select>
                      </label>

                      <label className="flex flex-wrap items-start gap-2.5">
                        <span className="t-caption mt-2 w-[52px] shrink-0">설명</span>
                        <textarea
                          value={correctForm.description}
                          onChange={(e) =>
                            setCorrectForms((prev) => ({
                              ...prev,
                              [item.event_id]: { ...correctForm, description: e.target.value },
                            }))
                          }
                          rows={2}
                          className="field min-w-0 flex-1 resize-y text-sm"
                        />
                      </label>
                    </div>

                    <div className="mt-3 flex gap-2">
                      <button
                        disabled={isBusy}
                        onClick={() => submitCorrection(item, correctForm)}
                        className="btn-primary px-4 py-2 text-[13px] disabled:opacity-40"
                      >
                        {isBusy ? '저장하는 중…' : '고친 값 저장'}
                      </button>
                      <button
                        onClick={() =>
                          setCorrectForms((prev) => {
                            const next = { ...prev }
                            delete next[item.event_id]
                            return next
                          })
                        }
                        className="cursor-pointer rounded border-0 bg-transparent px-4 py-2
                                   text-[13px] text-ink-400"
                      >
                        취소
                      </button>
                    </div>
                  </div>
                )}

                {/* 고친 이력 — 값만 바뀌면 무엇이 원래 근거였는지 알 수 없다 */}
                {item.corrections.length > 0 && (
                  <div className="mt-5 pt-5" style={{ borderTop: '1px solid var(--border)' }}>
                    <p className="t-eyebrow m-0 mb-2.5 text-ink-300">고친 이력</p>
                    {item.corrections.map((record, i) => (
                      <div key={record.person_id + i} className="mb-1.5">
                        <p className="t-caption m-0">
                          {record.person_name}
                          {record.at ? ' · ' + record.at.slice(0, 10) : ''}
                        </p>
                        {record.changes.map((change) => (
                          <p key={change.field} className="t-body-sm m-0 text-ink-700">
                            {FIELD_LABEL[change.field] || change.field}{' '}
                            <span className="text-ink-300 line-through">
                              {change.field === 'location_id'
                                ? placeName(change.before)
                                : change.before || '없음'}
                            </span>{' '}
                            → {change.field === 'location_id'
                              ? placeName(change.after)
                              : change.after || '없음'}
                          </p>
                        ))}
                      </div>
                    ))}
                  </div>
                )}

                {/* 이견 입력 — 기존 기록을 덮어쓰지 않는다 */}
                {form && (
                  <div className="mt-5 pt-5" style={{ borderTop: '1px solid var(--border)' }}>
                    <p className="t-body-sm m-0 mb-2.5">
                      {item.participants.find((p) => p.id === form.personId)?.name}님은 어떻게
                      기억하시나요? 기존 기록은 지우지 않고 함께 보존됩니다.
                    </p>
                    <textarea
                      value={form.note}
                      onChange={(e) =>
                        setDisputeForms((prev) => ({
                          ...prev,
                          [item.event_id]: { ...form, note: e.target.value },
                        }))
                      }
                      rows={2}
                      placeholder="예: 그날은 비가 와서 실내에 있었어요."
                      className="field resize-y text-sm"
                    />
                    <div className="mt-2.5 flex gap-2">
                      <button
                        disabled={isBusy || !form.note.trim()}
                        onClick={() => act(item.event_id, form.personId, 'dispute', form.note.trim())}
                        className="btn-primary px-4 py-2 text-[13px] disabled:opacity-40"
                      >
                        기억 남기기
                      </button>
                      <button
                        onClick={() =>
                          setDisputeForms((prev) => {
                            const next = { ...prev }
                            delete next[item.event_id]
                            return next
                          })
                        }
                        className="cursor-pointer rounded border-0 bg-transparent px-4 py-2
                                   text-[13px] text-ink-400"
                      >
                        취소
                      </button>
                    </div>
                  </div>
                )}

                {messages[item.event_id] && (
                  <p className="t-body-sm m-0 mt-4 text-accent-ink">
                    {messages[item.event_id]}
                  </p>
                )}
              </div>
            )
          })}
        </div>
      )}
    </Page>
  )
}
