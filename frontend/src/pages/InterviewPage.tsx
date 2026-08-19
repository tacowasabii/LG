import { useState } from 'react'
import { Mic, Send, CheckCircle2, MessageSquare } from 'lucide-react'
import { startInterview, submitInterviewAnswer, InterviewStartResult, InterviewAnswerResult } from '../lib/api'
import RichText from '../components/RichText'

interface QA {
  question: string
  answer?: string
}

export default function InterviewPage() {
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [context, setContext] = useState<InterviewStartResult['context']>(null)
  const [qaHistory, setQaHistory] = useState<QA[]>([])
  const [currentQuestion, setCurrentQuestion] = useState<string | null>(null)
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [isComplete, setIsComplete] = useState(false)
  const [updatedCount, setUpdatedCount] = useState(0)

  const handleStart = async () => {
    setLoading(true)
    try {
      const result = await startInterview('auto')
      setSessionId(result.session_id)
      setContext(result.context)
      setCurrentQuestion(result.question)
      setQaHistory([{ question: result.question }])
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  const handleAnswer = async () => {
    if (!input.trim() || !sessionId || loading) return

    const answer = input.trim()
    setInput('')
    setLoading(true)

    // 현재 질문에 답변 추가
    setQaHistory((prev) => {
      const updated = [...prev]
      updated[updated.length - 1] = { ...updated[updated.length - 1], answer }
      return updated
    })

    try {
      const result: InterviewAnswerResult = await submitInterviewAnswer(sessionId, answer)
      setUpdatedCount((prev) => prev + result.updated_nodes.length)

      if (result.is_complete) {
        setIsComplete(true)
        setCurrentQuestion(null)
      } else if (result.next_question) {
        setCurrentQuestion(result.next_question)
        setQaHistory((prev) => [...prev, { question: result.next_question! }])
      }
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  // Not started yet
  if (!sessionId) {
    return (
      <div className="max-w-2xl mx-auto">
        <div className="text-center py-16">
          <div className="w-20 h-20 bg-primary-100 rounded-full flex items-center justify-center mx-auto mb-6">
            <Mic size={32} className="text-primary-600" />
          </div>
          <h1 className="text-2xl font-bold text-gray-900 mb-2">AI 기억 인터뷰</h1>
          <p className="text-gray-500 mb-8 max-w-md mx-auto">
            AI가 가족 기억의 빈 곳을 찾아 자연스럽게 질문합니다.
            답변은 Memory Graph에 새로운 기억으로 저장됩니다.
          </p>
          <button onClick={handleStart} disabled={loading} className="btn-primary text-lg px-8 py-3">
            {loading ? '준비 중...' : '인터뷰 시작하기'}
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">AI 기억 인터뷰</h1>
        {context?.target_title && (
          <p className="text-gray-500 mt-1">
            주제: <span className="font-medium text-gray-700">{context.target_title}</span>
          </p>
        )}
      </div>

      {/* Progress */}
      <div className="flex items-center gap-2 text-sm text-gray-500">
        <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
          <div
            className="h-full bg-primary-500 rounded-full transition-all"
            style={{ width: `${(qaHistory.length / 5) * 100}%` }}
          />
        </div>
        <span>{qaHistory.length}/5 질문</span>
      </div>

      {/* Q&A History */}
      <div className="space-y-4">
        {qaHistory.map((qa, i) => (
          <div key={i} className="space-y-2">
            {/* Question */}
            <div className="flex gap-3">
              <div className="w-8 h-8 rounded-full bg-primary-100 flex items-center justify-center flex-shrink-0">
                <MessageSquare size={14} className="text-primary-600" />
              </div>
              <div className="card flex-1">
                {/* 질문은 EXAONE이 생성하므로 마크다운·줄바꿈이 섞여 온다 */}
                <p className="text-sm text-gray-800 whitespace-pre-wrap">
                  <RichText text={qa.question} />
                </p>
              </div>
            </div>

            {/* Answer */}
            {qa.answer && (
              <div className="flex gap-3 justify-end">
                <div className="card flex-1 bg-primary-50 border-primary-100 ml-11">
                  {/* 답변은 사용자가 입력한 평문이므로 마크다운 해석 없이 줄바꿈만 보존한다 */}
                  <p className="text-sm text-gray-800 whitespace-pre-wrap">{qa.answer}</p>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Input or Complete */}
      {isComplete ? (
        <div className="card text-center py-8 bg-green-50 border-green-100">
          <CheckCircle2 size={40} className="mx-auto text-green-500 mb-3" />
          <h3 className="font-semibold text-gray-900 mb-1">인터뷰 완료!</h3>
          <p className="text-sm text-gray-600">
            {updatedCount}개의 새로운 기억이 Memory Graph에 추가되었습니다.
          </p>
          <button onClick={() => { setSessionId(null); setQaHistory([]); setIsComplete(false); setUpdatedCount(0) }} className="btn-secondary mt-4">
            새 인터뷰 시작
          </button>
        </div>
      ) : (
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && handleAnswer()}
            placeholder="답변을 입력하세요..."
            className="flex-1 px-4 py-3 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-primary-500 text-sm"
            disabled={loading}
          />
          <button onClick={handleAnswer} disabled={!input.trim() || loading} className="btn-primary px-4 disabled:opacity-50">
            <Send size={18} />
          </button>
        </div>
      )}
    </div>
  )
}
