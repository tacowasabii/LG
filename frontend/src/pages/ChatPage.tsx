import { useState, useRef, useEffect } from 'react'
import { Send, Image, Calendar, Brain } from 'lucide-react'
import { sendChat, ChatResponse, ChatSource } from '../lib/api'

interface Message {
  role: 'user' | 'assistant'
  content: string
  sources?: ChatSource[]
  confidence?: string
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [conversationId, setConversationId] = useState<string | undefined>()
  const messagesEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = async () => {
    const query = input.trim()
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
        },
      ])
    } catch (e) {
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: '답변을 생성하지 못했습니다. 다시 시도해주세요.' },
      ])
    } finally {
      setLoading(false)
    }
  }

  const suggestions = [
    '우리 가족이 부산 처음 간 게 언제야?',
    '제주도 여행에서 뭐 했어?',
    '서연이 생일파티 사진 보여줘',
    '아빠가 기억하는 부산 여행 이야기 알려줘',
  ]

  return (
    <div className="max-w-3xl mx-auto flex flex-col h-[calc(100vh-6rem)]">
      {/* Header */}
      <div className="mb-4">
        <h1 className="text-2xl font-bold text-gray-900">Memory Chat</h1>
        <p className="text-gray-500 mt-1">가족의 기억을 질문해보세요. 실제 기록을 근거로 답변합니다.</p>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto space-y-4 pb-4">
        {messages.length === 0 && (
          <div className="text-center py-12">
            <Brain size={48} className="mx-auto text-gray-300 mb-4" />
            <p className="text-gray-400 mb-6">가족의 기억에 대해 무엇이든 물어보세요</p>
            <div className="flex flex-wrap justify-center gap-2">
              {suggestions.map((s) => (
                <button
                  key={s}
                  onClick={() => setInput(s)}
                  className="text-sm bg-gray-100 text-gray-600 px-3 py-1.5 rounded-full hover:bg-gray-200 transition-colors"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[80%] ${msg.role === 'user' ? 'order-1' : ''}`}>
              {/* Bubble */}
              <div
                className={`px-4 py-3 rounded-2xl ${
                  msg.role === 'user'
                    ? 'bg-primary-600 text-white rounded-br-md'
                    : 'bg-white border border-gray-200 text-gray-800 rounded-bl-md'
                }`}
              >
                <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
              </div>

              {/* Sources */}
              {msg.sources && msg.sources.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-2">
                  {msg.sources.map((source, j) => (
                    <SourceBadge key={j} source={source} />
                  ))}
                </div>
              )}

              {/* Confidence */}
              {msg.confidence && msg.role === 'assistant' && (
                <p className="text-xs text-gray-400 mt-1 ml-1">
                  {msg.confidence === 'confirmed' ? '✅ 확인된 기록 기반' : '⚠️ AI 추론 포함'}
                </p>
              )}
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex justify-start">
            <div className="bg-white border border-gray-200 px-4 py-3 rounded-2xl rounded-bl-md">
              <div className="flex gap-1">
                <div className="w-2 h-2 rounded-full bg-gray-300 animate-bounce" style={{ animationDelay: '0ms' }} />
                <div className="w-2 h-2 rounded-full bg-gray-300 animate-bounce" style={{ animationDelay: '150ms' }} />
                <div className="w-2 h-2 rounded-full bg-gray-300 animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="border-t border-gray-200 pt-4">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && handleSend()}
            placeholder="가족의 기억에 대해 물어보세요..."
            className="flex-1 px-4 py-3 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent text-sm"
            disabled={loading}
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || loading}
            className="btn-primary px-4 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Send size={18} />
          </button>
        </div>
      </div>
    </div>
  )
}

function SourceBadge({ source }: { source: ChatSource }) {
  const icons: Record<string, typeof Image> = {
    media: Image,
    event: Calendar,
    memory: Brain,
  }
  const Icon = icons[source.type] || Brain

  return (
    <div className="inline-flex items-center gap-1.5 text-xs bg-gray-50 border border-gray-200 px-2 py-1 rounded-lg">
      <Icon size={12} className="text-gray-500" />
      <span className="text-gray-600 max-w-[120px] truncate">{source.title || source.id}</span>
      {source.confidence && (
        <span className="text-gray-400">{Math.round(source.confidence * 100)}%</span>
      )}
    </div>
  )
}
