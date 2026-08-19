import { useState, useEffect, useCallback } from 'react'
import { Play, ChevronLeft, ChevronRight, X } from 'lucide-react'
import { createTVJourney, TVJourney, TVSlide, mediaUrl } from '../lib/api'
import RichText from '../components/RichText'

export default function TVViewPage() {
  const [journey, setJourney] = useState<TVJourney | null>(null)
  const [currentSlide, setCurrentSlide] = useState(0)
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [autoPlay, setAutoPlay] = useState(false)

  // Auto-play timer
  useEffect(() => {
    if (!autoPlay || !journey) return
    const timer = setInterval(() => {
      setCurrentSlide((prev) => {
        if (prev >= journey.slides.length - 1) {
          setAutoPlay(false)
          return prev
        }
        return prev + 1
      })
    }, 5000)
    return () => clearInterval(timer)
  }, [autoPlay, journey])

  // Keyboard navigation
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'ArrowRight') next()
      else if (e.key === 'ArrowLeft') prev()
      else if (e.key === 'Escape') setJourney(null)
      else if (e.key === ' ') { e.preventDefault(); setAutoPlay((p) => !p) }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [journey])

  const next = useCallback(() => {
    if (journey) setCurrentSlide((p) => Math.min(p + 1, journey.slides.length - 1))
  }, [journey])

  const prev = useCallback(() => {
    setCurrentSlide((p) => Math.max(p - 1, 0))
  }, [])

  const handleStart = async () => {
    if (!query.trim()) return
    setLoading(true)
    try {
      const result = await createTVJourney(query.trim())
      setJourney(result)
      setCurrentSlide(0)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  // Start screen
  if (!journey) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-white p-8">
        <div className="text-center mb-12">
          <h1 className="text-4xl font-bold mb-3">TV Memory Journey</h1>
          <p className="text-lg text-gray-400">우리의 기억을 큰 화면으로 감상하세요</p>
        </div>

        <div className="w-full max-w-lg">
          <div className="flex gap-3">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleStart()}
              placeholder="예: 우리 가족의 2015년, 부산 여행..."
              className="flex-1 px-5 py-4 bg-gray-800 border border-gray-700 rounded-xl text-white placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-primary-500 text-lg"
              disabled={loading}
            />
            <button
              onClick={handleStart}
              disabled={!query.trim() || loading}
              className="px-6 py-4 bg-primary-600 rounded-xl hover:bg-primary-700 transition-colors disabled:opacity-50"
            >
              <Play size={24} />
            </button>
          </div>

          {/* Suggestions */}
          <div className="flex flex-wrap justify-center gap-2 mt-6">
            {['우리 가족의 2015년', '부산 여행', '서연이의 생일'].map((s) => (
              <button
                key={s}
                onClick={() => setQuery(s)}
                className="text-sm text-gray-400 bg-gray-800/50 px-3 py-1.5 rounded-full hover:bg-gray-700 transition-colors"
              >
                {s}
              </button>
            ))}
          </div>
        </div>

        {loading && <p className="text-gray-400 mt-8 animate-pulse">기억을 모아오고 있어요...</p>}
      </div>
    )
  }

  // Slideshow
  const slide = journey.slides[currentSlide]

  return (
    <div className="h-full relative flex flex-col">
      {/* Close button */}
      <button
        onClick={() => setJourney(null)}
        className="absolute top-4 right-4 z-20 text-white/60 hover:text-white p-2"
      >
        <X size={24} />
      </button>

      {/* Main content */}
      <div className="flex-1 flex items-center justify-center relative">
        {slide.type === 'title' ? (
          <div className="text-center text-white">
            <h2 className="text-5xl font-bold mb-4">{journey.title}</h2>
            {journey.narration && (
              <p className="text-xl text-gray-300 max-w-2xl mx-auto whitespace-pre-wrap">
                <RichText text={journey.narration} />
              </p>
            )}
          </div>
        ) : (
          <div className="text-center">
            {slide.file_path && (
              <img
                src={mediaUrl(slide.file_path)}
                alt={slide.caption}
                className="max-h-[70vh] max-w-[90vw] object-contain rounded-lg mx-auto"
              />
            )}
            {slide.caption && (
              <p className="text-white text-lg mt-4">{slide.caption}</p>
            )}
            {slide.event_title && (
              <p className="text-gray-400 text-sm mt-1">{slide.event_title}</p>
            )}
          </div>
        )}

        {/* Navigation arrows */}
        <button
          onClick={prev}
          disabled={currentSlide === 0}
          className="absolute left-4 top-1/2 -translate-y-1/2 text-white/40 hover:text-white disabled:opacity-0 transition-all p-2"
        >
          <ChevronLeft size={40} />
        </button>
        <button
          onClick={next}
          disabled={currentSlide === journey.slides.length - 1}
          className="absolute right-4 top-1/2 -translate-y-1/2 text-white/40 hover:text-white disabled:opacity-0 transition-all p-2"
        >
          <ChevronRight size={40} />
        </button>
      </div>

      {/* Bottom bar */}
      <div className="p-4 flex items-center gap-4">
        {/* Progress */}
        <div className="flex-1 h-1 bg-gray-800 rounded-full overflow-hidden">
          <div
            className="h-full bg-primary-500 rounded-full transition-all duration-300"
            style={{ width: `${((currentSlide + 1) / journey.slides.length) * 100}%` }}
          />
        </div>

        {/* Controls */}
        <button
          onClick={() => setAutoPlay(!autoPlay)}
          className={`text-sm px-3 py-1 rounded ${autoPlay ? 'bg-primary-600 text-white' : 'bg-gray-800 text-gray-400'}`}
        >
          {autoPlay ? '일시정지' : '자동재생'}
        </button>

        <span className="text-sm text-gray-500">
          {currentSlide + 1} / {journey.slides.length}
        </span>
      </div>
    </div>
  )
}
