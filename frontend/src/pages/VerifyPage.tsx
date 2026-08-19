import { useEffect, useState } from 'react'
import { CheckCircle2, HelpCircle, GitBranch, ShieldCheck, Users } from 'lucide-react'
import {
  getVerificationInbox,
  verifyEvent,
  InboxItem,
  VerificationState,
} from '../lib/api'

/**
 * Verification Inbox — 기획안 STEP 04 "확인하기"
 *
 * AI가 연결한 사실을 가족이 맞음 / 모름 / 이견으로 판정한다.
 * 이견은 기존 기록을 덮어쓰지 않고 그 사람의 기억으로 함께 보존된다.
 */

const STATE_CONFIG: Record<
  VerificationState,
  { label: string; hint: string; color: string }
> = {
  conflicted: {
    label: '기억 충돌',
    hint: '기억이 서로 다릅니다. 양쪽 모두 보존됩니다.',
    color: 'text-amber-700 bg-amber-50 border-amber-200',
  },
  inferred: {
    label: '확인 필요',
    hint: '아직 아무도 확인하지 않았습니다.',
    color: 'text-gray-600 bg-gray-50 border-gray-200',
  },
  supported: {
    label: '다중 근거',
    hint: '두 사람 이상의 기억이 있습니다.',
    color: 'text-blue-700 bg-blue-50 border-blue-200',
  },
  confirmed: {
    label: '확인 완료',
    hint: '가족이 확인했습니다.',
    color: 'text-green-700 bg-green-50 border-green-200',
  },
}

export default function VerifyPage() {
  const [items, setItems] = useState<InboxItem[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState<string | null>(null)
  const [messages, setMessages] = useState<Record<string, string>>({})
  // 이견 입력창을 펼친 이벤트 -> {personId, note}
  const [disputeForms, setDisputeForms] = useState<
    Record<string, { personId: string; note: string }>
  >({})

  const load = () =>
    getVerificationInbox()
      .then((res) => setItems(res.items))
      .catch(console.error)

  useEffect(() => {
    load().finally(() => setLoading(false))
  }, [])

  const act = async (
    eventId: string,
    personId: string,
    action: 'confirm' | 'unknown' | 'dispute',
    note?: string,
  ) => {
    setBusy(eventId)
    try {
      const res = await verifyEvent(eventId, personId, action, note)
      setMessages((prev) => ({ ...prev, [eventId]: res.message }))
      setDisputeForms((prev) => {
        const next = { ...prev }
        delete next[eventId]
        return next
      })
      await load()
    } catch (e) {
      console.error(e)
      setMessages((prev) => ({ ...prev, [eventId]: '기록에 실패했어요. 다시 시도해주세요.' }))
    } finally {
      setBusy(null)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <p className="text-gray-400">불러오는 중...</p>
      </div>
    )
  }

  const pending = items.filter((i) => i.state === 'inferred' || i.state === 'conflicted').length

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">확인 요청</h1>
        <p className="text-gray-500 mt-1">
          AI가 연결한 사실을 가족이 확인합니다. 기억이 다르면 지우지 않고 함께 보존합니다.
        </p>
        {pending > 0 && (
          <p className="text-sm text-primary-600 mt-2">확인이 필요한 사건 {pending}건</p>
        )}
      </div>

      {items.length === 0 && (
        <div className="card text-center py-12">
          <ShieldCheck size={28} className="mx-auto text-gray-300" />
          <p className="text-gray-400 mt-3">확인할 사건이 없습니다.</p>
          <p className="text-gray-400 text-sm mt-1">
            사진을 업로드하면 AI가 연결한 사실이 여기에 쌓입니다.
          </p>
        </div>
      )}

      <div className="space-y-4">
        {items.map((item) => {
          const config = STATE_CONFIG[item.state]
          const form = disputeForms[item.event_id]
          const isBusy = busy === item.event_id

          return (
            <div key={item.event_id} className="card space-y-3">
              {/* 제목 + 상태 */}
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h3 className="font-medium text-gray-900">{item.event_title}</h3>
                  <p className="text-sm text-gray-500 mt-0.5">{item.date_start || '날짜 미상'}</p>
                </div>
                <span
                  className={`text-xs px-2 py-1 rounded-lg border whitespace-nowrap ${config.color}`}
                >
                  {config.label}
                </span>
              </div>

              <p className="text-xs text-gray-400">{config.hint}</p>

              {/* 확인 이력 */}
              {(item.confirmed_by.length > 0 ||
                item.disputed_by.length > 0 ||
                item.unknown_by.length > 0) && (
                <div className="flex flex-wrap gap-2 text-xs">
                  {item.confirmed_by.map((p) => (
                    <span
                      key={`c-${p.id}`}
                      className="inline-flex items-center gap-1 text-green-700 bg-green-50 px-2 py-1 rounded"
                    >
                      <ShieldCheck size={12} /> {p.name} 확인
                    </span>
                  ))}
                  {item.disputed_by.map((p) => (
                    <span
                      key={`d-${p.id}`}
                      className="inline-flex items-center gap-1 text-amber-700 bg-amber-50 px-2 py-1 rounded"
                    >
                      <GitBranch size={12} /> {p.name} 이견
                    </span>
                  ))}
                  {item.unknown_by.map((p) => (
                    <span
                      key={`u-${p.id}`}
                      className="inline-flex items-center gap-1 text-gray-500 bg-gray-100 px-2 py-1 rounded"
                    >
                      <HelpCircle size={12} /> {p.name} 모름
                    </span>
                  ))}
                </div>
              )}

              {/* 관점별 기억 — 충돌해도 한쪽으로 정리하지 않는다 */}
              {item.memories.length > 0 && (
                <div className="border-t border-gray-100 pt-3 space-y-2">
                  <p className="text-xs text-gray-500 flex items-center gap-1">
                    <Users size={12} /> 기억 {item.memories.length}개
                    {item.memories.length > 1 && ' · 관점별로 나란히 보존됩니다'}
                  </p>
                  {item.memories.map((m) => (
                    <div key={m.id} className="text-sm bg-gray-50 rounded-lg px-3 py-2">
                      {m.contributor_name && (
                        <span className="text-gray-500 mr-1">{m.contributor_name}:</span>
                      )}
                      <span className="text-gray-800">{m.content}</span>
                    </div>
                  ))}
                </div>
              )}

              {messages[item.event_id] && (
                <p className="text-xs text-primary-600">{messages[item.event_id]}</p>
              )}

              {/* 참여자별 판정 */}
              <div className="border-t border-gray-100 pt-3">
                <p className="text-xs text-gray-500 mb-2">누구의 확인인가요?</p>
                <div className="space-y-2">
                  {item.participants.map((p) => (
                    <div key={p.id} className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm text-gray-700 w-20 shrink-0">
                        {p.name}
                        <span className="text-gray-400 text-xs ml-1">{p.relation}</span>
                      </span>
                      <button
                        disabled={isBusy}
                        onClick={() => act(item.event_id, p.id, 'confirm')}
                        className="text-xs px-2.5 py-1 rounded-lg border border-green-200 text-green-700 hover:bg-green-50 disabled:opacity-40"
                      >
                        <CheckCircle2 size={12} className="inline mr-1" />
                        맞음
                      </button>
                      <button
                        disabled={isBusy}
                        onClick={() => act(item.event_id, p.id, 'unknown')}
                        className="text-xs px-2.5 py-1 rounded-lg border border-gray-200 text-gray-600 hover:bg-gray-50 disabled:opacity-40"
                      >
                        <HelpCircle size={12} className="inline mr-1" />
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
                        className="text-xs px-2.5 py-1 rounded-lg border border-amber-200 text-amber-700 hover:bg-amber-50 disabled:opacity-40"
                      >
                        <GitBranch size={12} className="inline mr-1" />
                        내 기억은 달라요
                      </button>
                    </div>
                  ))}
                </div>
              </div>

              {/* 이견 입력 — 기존 기록을 덮어쓰지 않는다 */}
              {form && (
                <div className="border-t border-gray-100 pt-3 space-y-2">
                  <p className="text-xs text-gray-500">
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
                    className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                  />
                  <div className="flex gap-2">
                    <button
                      disabled={isBusy || !form.note.trim()}
                      onClick={() =>
                        act(item.event_id, form.personId, 'dispute', form.note.trim())
                      }
                      className="btn-primary text-xs px-3 py-1.5 disabled:opacity-40"
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
                      className="text-xs px-3 py-1.5 text-gray-500 hover:text-gray-700"
                    >
                      취소
                    </button>
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
