import { useState, useRef, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { sendChat, ChatResponse, ChatSource, mediaUrl } from '../lib/api'
import RichText from '../components/RichText'
import EvidenceCard from '../components/EvidenceCard'
import AudioClip from '../components/AudioClip'
import { useEvents, useVoiceClips } from '../lib/useGraphData'
import { useCurrentUser } from '../lib/currentUser'

/**
 * Ask HomeStory — 질문하면 그래프와 원본을 근거로 답한다
 *
 * 기획안이 요구한 두 가지를 더했다.
 *  1. "답변과 함께 실제 사진·음성 재생" — 근거를 썸네일 알약으로 보여주고,
 *     누르면 원본 패널이 열린다. 사건에 음성이 있으면 함께 재생한다.
 *  2. "정보가 부족하면 가족에게 추가 질문" — 근거가 없거나 추정이 섞인 답변
 *     아래에 기억을 남기거나 확인하러 가는 길을 붙였다. 기획안 6단계의
 *     마지막 고리(이어가기)가 화면에서 끊겨 있었다.
 *
 * 신뢰도를 아이콘 하나(✅/⚠️)로 줄이지 않는다. "확인된 기록 기반"과 "근거 없음 ·
 * 추측하지 않았습니다"는 사용자에게 전혀 다른 뜻이고, 그 차이를 문장으로 밝히는
 * 것이 이 제품이 신뢰를 얻는 방식이다.
 *
 * 근거·음성·확인 상태는 모두 API에서 온다. 남은 교체 지점은 원본 패널을
 * GET /api/media/{id} 상세로 채우는 것과, "기억 남기기"가 그 사건을 바로 인터뷰
 * 대상으로 넘기는 것(POST /api/interview/start {target_id})이다.
 */

interface Message {
  role: 'user' | 'assistant'
  content: string
  sources?: ChatSource[]
  confidence?: string
  /** 질문 자체를 들고 있어야 후속 액션(기억 남기기)에 문맥을 넘길 수 있다 */
  query?: string
}

/** 백엔드가 내려주는 신뢰도 값을 사용자가 읽을 문장으로 바꾼다 */
const CONFIDENCE_LABEL: Record<string, string> = {
  confirmed: '확인된 기록 기반',
  supported: '두 사람 이상의 기억으로 뒷받침됨',
  conflicted: '기억이 갈리는 사건 · 양쪽 보존',
  inferred: 'AI 추정 포함 · 아직 확인되지 않았습니다',
  none: '근거 없음 · 추측하지 않았습니다',
}

function confidenceColor(confidence: string): string {
  if (confidence === 'confirmed') return 'var(--positive-ink)'
  if (confidence === 'conflicted') return 'var(--critical-ink)'
  return 'var(--ink-400)'
}

const SUGGESTIONS = [
  '우리 가족이 부산 처음 간 게 언제야?',
  '제주도 여행에서 뭐 했어?',
  '아빠가 기억하는 부산 여행 이야기 알려줘',
  '서연이 생일파티 사진 보여줘',
]

export default function ChatPage() {
  const { current } = useCurrentUser()
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [conversationId, setConversationId] = useState<string | undefined>()
  const [openSource, setOpenSource] = useState<ChatSource | null>(null)
  // 근거에 걸린 사건의 확인 상태와 그 사건에 남은 목소리를 함께 보여준다
  const { eventById } = useEvents()
  const { clipsForEvent } = useVoiceClips()
  const messagesEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const send = async (text?: string) => {
    const query = (text ?? input).trim()
    if (!query || loading) return

    setInput('')
    setMessages((prev) => [...prev, { role: 'user', content: query }])
    setLoading(true)

    try {
      const result: ChatResponse = await sendChat(query, conversationId)
      setConversationId(result.conversation_id ?? undefined)
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: result.answer,
          sources: result.sources,
          confidence: result.confidence,
          query,
        },
      ])
    } catch (e) {
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: '답변을 생성하지 못했습니다. 다시 시도해 주세요.' },
      ])
    } finally {
      setLoading(false)
    }
  }

  /** 답변 근거에 걸린 사건들 (음성·확인 상태를 붙이는 기준) */
  const eventIdsOf = (sources?: ChatSource[]) =>
    (sources || [])
      .filter((s) => s.type === 'event')
      .map((s) => s.id)
      .filter((id) => !!eventById(id))

  // 사건 근거는 서버가 그 사건의 사진 한 장을 썸네일로 함께 내려준다
  const sourceThumb = openSource?.thumbnail || null

  return (
    <div className="mx-auto flex h-screen max-w-[820px] flex-col px-12">
      <div className="pb-6 pt-12">
        <p className="t-eyebrow m-0 mb-3">Ask HomeStory</p>
        <h2 className="t-title m-0">기억에 물어보기</h2>
        <p className="t-body-sm m-0 mt-2.5">
          모든 문장은 원본 기록으로 되짚을 수 있습니다. 근거가 없으면 없다고 답합니다.
        </p>
      </div>

      <div className="flex min-w-0 flex-1 flex-col gap-5 overflow-y-auto overflow-x-hidden pb-6">
        {messages.length === 0 && (
          <div className="py-12">
            <p className="t-body m-0 mb-5 text-ink-300">기억에 대해 무엇이든 물어보세요.</p>
            <div className="flex flex-col gap-px">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => send(s)}
                  className="flex cursor-pointer items-center justify-between gap-4 border-0
                             bg-transparent px-1 py-3.5 text-left text-[15px] text-ink-500
                             hover:text-accent-ink"
                  style={{ borderBottom: '1px solid var(--border)' }}
                >
                  <span>{s}</span>
                  <span className="text-accent-ink">→</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, i) => {
          const isUser = msg.role === 'user'
          const eventIds = eventIdsOf(msg.sources)
          const clips = eventIds.flatMap((id) => clipsForEvent(id))
          const conflicted = eventIds.some((id) => eventById(id)?.state === 'conflicted')
          const grounded = msg.confidence === 'confirmed' || msg.confidence === 'supported'
          const needsMore = !isUser && !!msg.confidence && (!msg.sources?.length || !grounded)

          return (
            <div key={i} className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
              <div className="max-w-[88%]">
                <div
                  className="px-5 py-4"
                  style={
                    isUser
                      ? {
                          background: 'var(--accent)',
                          color: 'var(--accent-fg)',
                          borderRadius: '12px 12px 4px 12px',
                        }
                      : {
                          background: 'var(--paper-pure)',
                          color: 'var(--ink-700)',
                          border: '1px solid var(--border)',
                          borderRadius: '12px 12px 12px 4px',
                        }
                  }
                >
                  <p
                    className="m-0 whitespace-pre-wrap text-[15px] leading-relaxed"
                    style={{ textWrap: 'pretty' }}
                  >
                    {isUser ? msg.content : <RichText text={msg.content} />}
                  </p>
                </div>

                {/* 근거 — 사진으로 보여준다 */}
                {msg.sources && msg.sources.length > 0 && (
                  <div className="mt-2.5 flex flex-wrap gap-2">
                    {msg.sources.map((source, j) => (
                      <EvidenceCard
                        key={j}
                        source={source}
                        active={openSource?.id === source.id}
                        onSelect={setOpenSource}
                      />
                    ))}
                  </div>
                )}

                {/* 실제 가족 음성 */}
                {clips.length > 0 && (
                  <div className="mt-2.5 flex flex-col gap-2">
                    {clips.map((clip) => (
                      <AudioClip key={clip.id} clip={clip} compact />
                    ))}
                  </div>
                )}

                {msg.confidence && !isUser && (
                  <p
                    className="t-caption m-0 ml-0.5 mt-2.5"
                    style={{ color: confidenceColor(msg.confidence) }}
                  >
                    {CONFIDENCE_LABEL[msg.confidence] || msg.confidence}
                  </p>
                )}

                {/* 기억이 갈리는 사건이면 숨기지 않고 알린다 */}
                {conflicted && (
                  <div
                    className="mt-2.5 rounded-lg px-4 py-3.5"
                    style={{ background: 'var(--critical-soft)' }}
                  >
                    <p className="t-body-sm m-0" style={{ color: 'var(--critical-ink)' }}>
                      이 사건은 가족의 기억이 서로 다릅니다. 한쪽으로 정리하지 않고 둘 다 남겨
                      두었습니다.
                    </p>
                    <Link
                      to="/verify"
                      className="mt-2 inline-block text-xs"
                      style={{ color: 'var(--critical-ink)', textDecoration: 'underline' }}
                    >
                      양쪽 기억 보기 →
                    </Link>
                  </div>
                )}

                {/* 폐쇄 루프 — 모르면 여기서 채운다 */}
                {needsMore && (
                  <div className="mt-2.5 rounded-lg bg-ink-50 px-4 py-3.5">
                    <p className="t-body-sm m-0">
                      {current?.name ?? '지금 보는 사람'}님이 지금 기억을 남기면 다음부터는 근거를 갖고 답할 수
                      있습니다.
                    </p>
                    <div className="mt-2.5 flex flex-wrap gap-2">
                      <Link to="/interview" className="btn-outline no-underline hover:no-underline">
                        지금 기억 남기기
                      </Link>
                      <Link to="/verify" className="btn-quiet no-underline hover:no-underline">
                        확인이 필요한 사건 보기
                      </Link>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )
        })}

        {loading && <p className="t-caption m-0">그래프를 찾고 있습니다…</p>}

        <div ref={messagesEndRef} />
      </div>

      <div
        className="flex gap-2 pb-8 pt-5"
        style={{ borderTop: '1px solid var(--border)' }}
      >
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && send()}
          placeholder="기억에 대해 물어보세요"
          className="field flex-1"
          disabled={loading}
        />
        <button
          onClick={() => send()}
          disabled={!input.trim() || loading}
          className="btn-primary shrink-0"
        >
          묻기 →
        </button>
      </div>

      {openSource && (
        <div
          className="fixed inset-0 z-[60] flex items-center justify-center p-8"
          style={{ background: 'rgba(14,13,11,0.5)' }}
          onClick={() => setOpenSource(null)}
        >
          <div
            className="w-[380px] rounded-lg bg-paper-pure p-7"
            style={{ boxShadow: 'var(--shadow-lg)' }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-4">
              <p className="t-eyebrow m-0">근거 원본</p>
              <button
                onClick={() => setOpenSource(null)}
                className="cursor-pointer border-0 bg-transparent text-ink-300"
                aria-label="닫기"
              >
                ✕
              </button>
            </div>

            {sourceThumb && (
              <img
                src={mediaUrl(sourceThumb)}
                alt=""
                className="mt-4 h-[200px] w-full rounded bg-ink-50 object-cover"
              />
            )}

            {openSource.title && (
              <p className="m-0 mt-4 text-[17px] font-semibold text-ink-900">
                {openSource.title}
              </p>
            )}

            <dl className="mt-3.5 flex flex-col gap-2">
              <div
                className="flex justify-between gap-4 pb-2"
                style={{ borderBottom: '1px solid var(--ink-50)' }}
              >
                <dt className="t-caption">종류</dt>
                <dd className="t-body-sm m-0">{openSource.type}</dd>
              </div>
              <div
                className="flex justify-between gap-4 pb-2"
                style={{ borderBottom: '1px solid var(--ink-50)' }}
              >
                <dt className="t-caption">식별자</dt>
                <dd className="t-mono m-0 text-xs">{openSource.id}</dd>
              </div>
              {openSource.confidence != null && (
                <div className="flex justify-between gap-4">
                  <dt className="t-caption">근거 강도</dt>
                  <dd className="t-mono m-0 text-xs">
                    {Math.round(openSource.confidence * 100)}%
                  </dd>
                </div>
              )}
            </dl>

            <p className="t-caption mt-4">
              모든 답변 문장은 이런 원본으로 되짚을 수 있어야 합니다.
            </p>
          </div>
        </div>
      )}
    </div>
  )
}
