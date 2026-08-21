import { useState, useRef, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { sendChat, streamChat, ChatResponse, ChatSource, EventListItem, mediaUrl } from '../lib/api'
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
  /** 실제 모델이 답했는가 (false면 대체 문장) */
  llmUsed?: boolean
  model?: string | null
  provider?: string | null
  /** 질문 자체를 들고 있어야 후속 액션(기억 남기기)에 문맥을 넘길 수 있다 */
  query?: string
  /** 아직 글자가 흘러들어오는 중. 근거 뱃지와 후속 액션은 끝난 뒤에 붙인다 */
  streaming?: boolean
}

/**
 * 답변을 쓴 곳을 사람이 읽을 이름으로.
 *
 * 모델 id만으로는 구분할 수 없다 — Friendli는 전용 엔드포인트 id(depe675tjc2rcpo)가
 * 모델 이름 자리에 오기 때문이다. 그래서 서버가 provider를 함께 내려준다.
 */
function modelLabel(provider?: string | null, model?: string | null): string {
  if (provider === 'friendli') return 'EXAONE · FriendliAI'
  if (provider === 'bedrock') return 'Claude Haiku 4.5 · Bedrock'
  if (provider === 'exaone') {
    return model?.includes('instant') ? 'EXAONE' : 'EXAONE · 추론 모드'
  }
  return model || '모델'
}

/** 백엔드가 내려주는 신뢰도 값을 사용자가 읽을 문장으로 바꾼다 */
const CONFIDENCE_LABEL: Record<string, string> = {
  confirmed: '가족 기록 기반',
  ai_inferred: 'AI 추정 포함 · 기록에 없는 부분이 있습니다',
  none: '근거 없음 · 추측하지 않았습니다',
}

function confidenceColor(confidence: string): string {
  if (confidence === 'confirmed') return 'var(--positive-ink)'
  return 'var(--ink-400)'
}

/**
 * 조사 붙이기 — 종성이 있으면 앞의 것, 없으면 뒤의 것
 *
 * "박서연이" / "김민수가" 처럼 이름마다 달라서, 추천 질문을 데이터로 만들려면
 * 필요하다. 한글이 아니면 종성 없는 쪽을 쓴다.
 */
function withParticle(word: string, withJong: string, withoutJong: string): string {
  const code = word.charCodeAt(word.length - 1) - 0xac00
  if (code < 0 || code > 11171) return word + withoutJong
  return word + (code % 28 === 0 ? withoutJong : withJong)
}

/**
 * 추천 질문은 그래프에 실제로 있는 사건에서 만든다.
 *
 * 예전에는 고정 문장 네 개였고 그중 "서연이 생일파티 사진 보여줘"는 그래프에 없는
 * 사건이었다. 화면이 권한 질문이 "그런 기록이 없습니다"로 돌아오니 모델이 고장 난
 * 것처럼 보였다. 데이터에서 만들면 그럴 수가 없다.
 */
function buildSuggestions(events: EventListItem[]): string[] {
  if (events.length === 0) return []

  // 시드 장소 이름에 붙은 "(가상)" 같은 꼬리표는 질문에서 뗀다.
  // 검색은 부분 일치라서 떼도 같은 곳을 찾는다.
  const plain = (text: string) => text.replace(/\s*\([^)]*\)\s*$/, '').trim()

  const sorted = [...events].sort((a, b) =>
    (a.date_start || '').localeCompare(b.date_start || ''),
  )
  // 네 질문이 같은 사건을 가리키면 추천이 하나뿐인 것과 같다. 쓴 사건은 빼고 고른다.
  const used = new Set<string>()
  const pick = (test: (e: EventListItem) => boolean) => {
    const found = sorted.find((e) => !used.has(e.id) && test(e))
    if (found) used.add(found.id)
    return found
  }

  const oldest = pick(() => true)
  const withMemory = pick((e) => e.memory_count > 0 && e.participants.length > 0)
  const withPhoto = pick((e) => e.media_thumbs.length > 0)
  const newest = [...sorted].reverse().find((e) => e.place?.name)

  const questions: string[] = []
  if (oldest) questions.push(`${withParticle(plain(oldest.title), '은', '는')} 언제였어?`)
  if (withMemory) {
    const who = withMemory.participants[0].name
    questions.push(
      `${withParticle(who, '이', '가')} 기억하는 ${plain(withMemory.title)} 이야기 알려줘`,
    )
  }
  if (withPhoto) questions.push(`${plain(withPhoto.title)} 사진 보여줘`)
  if (newest?.place?.name) questions.push(`${plain(newest.place.name)} 언제 갔어?`)

  return questions.slice(0, 4)
}

export default function ChatPage() {
  const { current } = useCurrentUser()
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [conversationId, setConversationId] = useState<string | undefined>()
  const [openSource, setOpenSource] = useState<ChatSource | null>(null)
  // 근거에 걸린 사건의 확인 상태와 그 사건에 남은 목소리를 함께 보여준다
  const { events, eventById } = useEvents()
  const { clipsForEvent } = useVoiceClips()
  const messagesEndRef = useRef<HTMLDivElement>(null)
  /** 기다린 시간. 추론 모드는 20~30초 걸려서, 숫자가 없으면 멈춘 것처럼 보인다 */
  const [waited, setWaited] = useState(0)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // 기다리는 동안 초를 센다. 가짜 진행률을 그리지 않고 실제 경과만 보여준다.
  useEffect(() => {
    if (!loading) return
    setWaited(0)
    const timer = window.setInterval(() => setWaited((s) => s + 1), 1000)
    return () => window.clearInterval(timer)
  }, [loading])

  const send = async (text?: string) => {
    const query = (text ?? input).trim()
    if (!query || loading) return

    setInput('')
    setMessages((prev) => [...prev, { role: 'user', content: query }])
    setLoading(true)

    /** 답변 자리를 미리 만든다. 여기에 글자를 이어 붙인다 */
    let slot = -1
    const openSlot = () => {
      setMessages((prev) => {
        slot = prev.length
        return [...prev, { role: 'assistant', content: '', query, streaming: true }]
      })
    }
    const patch = (change: Partial<Message>) => {
      setMessages((prev) => prev.map((m, i) => (i === slot ? { ...m, ...change } : m)))
    }

    try {
      openSlot()
      const result = await streamChat(query, conversationId, {
        // 근거는 모델이 답을 쓰기 전에 이미 정해져 있다. 먼저 붙여두면
        // 글자가 흐르는 동안 사용자가 무엇을 근거로 답하는지 볼 수 있다.
        onMeta: (meta) => patch({ sources: meta.sources, confidence: meta.confidence }),
        onDelta: (piece) =>
          setMessages((prev) =>
            prev.map((m, i) => (i === slot ? { ...m, content: m.content + piece } : m)),
          ),
      })
      setConversationId(result.conversation_id ?? undefined)
      patch({
        content: result.answer,
        sources: result.sources,
        confidence: result.confidence,
        llmUsed: result.llm_used,
        model: result.model,
        provider: result.provider,
        streaming: false,
      })
    } catch (e) {
      // 스트리밍이 막힌 환경(프록시가 버퍼링하거나 응답을 끊는 경우)에서는
      // 한 번에 받는 경로로 되돌린다. 답을 못 보여주는 것보다 낫다.
      try {
        const result: ChatResponse = await sendChat(query, conversationId)
        setConversationId(result.conversation_id ?? undefined)
        patch({
          content: result.answer,
          sources: result.sources,
          confidence: result.confidence,
          llmUsed: result.llm_used,
          model: result.model,
          provider: result.provider,
          streaming: false,
        })
      } catch {
        patch({
          content: '답변을 생성하지 못했습니다. 다시 시도해 주세요.',
          streaming: false,
        })
      }
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
              {buildSuggestions(events).map((s) => (
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
          const varied = eventIds.some((id) => eventById(id)?.state === 'varied')
          const grounded = msg.confidence === 'confirmed'
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

                {/*
                  근거 — 사진으로 보여준다.

                  라벨을 붙이는 이유: 이 목록은 "질문이 사실이라는 증거"가 아니라 "이 답을
                  쓸 때 읽은 자료"다. 기록에 없는 것을 물어도 검색은 가장 가까운 노드를
                  돌려주므로 목록이 늘 찬다 — '런던 여행'을 물으면 부산·제주 기록이 붙는다.
                  라벨이 없으면 그 기록이 있다는 뜻으로 읽힌다. 있는지 없는지는 아래
                  신뢰도 문장이 말한다 (CONFIDENCE_LABEL).
                */}
                {msg.sources && msg.sources.length > 0 && (
                  <div className="mt-2.5">
                    <p className="t-caption m-0 mb-1.5 ml-0.5 text-ink-300">이 답변이 읽은 기록</p>
                    <div className="flex flex-wrap gap-2">
                      {msg.sources.map((source, j) => (
                        <EvidenceCard
                          key={j}
                          source={source}
                          active={openSource?.id === source.id}
                          onSelect={setOpenSource}
                        />
                      ))}
                    </div>
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

                {/*
                  이 답변을 누가 썼는가. 폴백이 조용히 일어나면 "LLM이 이상하다"로만
                  보이고 원인을 찾을 수 없다. 그래서 실패했을 때는 분명히 밝힌다.
                */}
                {!isUser && msg.llmUsed === false && (
                  <p className="t-caption m-0 ml-0.5 mt-1" style={{ color: 'var(--critical-ink)' }}>
                    모델을 부르지 못해 미리 준비된 문장으로 답했습니다 — 서버의 LLM
                    설정(제공자 자격증명)과 네트워크를 확인하세요.
                  </p>
                )}
                {!isUser && msg.llmUsed && msg.model && !msg.streaming && (
                  <p className="t-caption m-0 ml-0.5 mt-1 text-ink-300">
                    {modelLabel(msg.provider, msg.model)}가 썼습니다
                  </p>
                )}

                {/* 가족이 다르게 기억하는 추억이면 숨기지 않고 알린다 */}
                {varied && (
                  <div
                    className="mt-2.5 rounded-lg px-4 py-3.5"
                    style={{ background: 'var(--critical-soft)' }}
                  >
                    <p className="t-body-sm m-0" style={{ color: 'var(--critical-ink)' }}>
                      가족들이 이 추억을 조금 다르게 기억하고 있어요. 한쪽으로 정리하지 않고
                      모두 남겨 두었습니다.
                    </p>
                    <Link
                      to={eventIds[0] ? `/memory/${eventIds[0]}` : '/continue'}
                      className="mt-2 inline-block text-xs"
                      style={{ color: 'var(--critical-ink)', textDecoration: 'underline' }}
                    >
                      여러 기억 함께 보기 →
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
                      <Link to="/continue" className="btn-quiet no-underline hover:no-underline">
                        가족의 추억에 기억 더하기
                      </Link>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )
        })}

        {/*
          글자가 흐르기 시작하면 이 표시는 사라진다. 스트리밍이라 답변 자체가
          진행 상황이고, 둘을 같이 두면 화면이 두 번 말하는 셈이 된다.
        */}
        {loading && !messages[messages.length - 1]?.content && (
          <div>
            <p className="t-caption m-0">
              {waited < 3
                ? '질문을 인물·장소·시점 조건으로 바꾸는 중…'
                : '그래프에서 근거를 찾는 중…'}
              {waited > 0 && ` · ${waited}초`}
            </p>
            {waited >= 8 && (
              <p className="t-caption m-0 mt-1 text-ink-300">
                근거를 찾은 뒤 답을 쓰기 시작합니다. 첫 문장이 나오면 이어서 보입니다.
              </p>
            )}
          </div>
        )}

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
