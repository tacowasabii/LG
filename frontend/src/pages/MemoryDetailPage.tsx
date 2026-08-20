import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Heart, Plus, Sparkles } from 'lucide-react'
import {
  MemoryDetail,
  MemoryEntry,
  composeTogetherStory,
  deleteMemoryEntry,
  echoMemory,
  getMemoryDetail,
  mediaUrl,
} from '../lib/api'
import AudioClip from '../components/AudioClip'
import MemoryDeleteButton from '../components/MemoryDeleteButton'
import MemoryComposer from '../components/MemoryComposer'
import MemoryContextNote from '../components/MemoryContextNote'
import { STATE_CONFIG } from '../components/StatusPill'
import { Page, PageHeader } from '../components/Page'
import { invalidateEvents } from '../lib/useGraphData'

/**
 * 추억 상세 (기획안 09)
 *
 * 위에서 아래로 이 순서다.
 *
 *   사진 · 영상
 *   제목 · 날짜 · 장소 · 함께한 사람
 *   최초 작성자의 기억
 *   나도 기억나요 · + 내 기억 더하기
 *   가족이 더한 기억 (사진 · 영상 · 목소리 포함)
 *   가족들이 조금 다르게 기억하고 있어요
 *   AI가 만든 함께 기억한 이야기
 *
 * 순서를 이렇게 못 박은 이유는 무게 때문이다. 화면에서 가장 위에 오는 것은
 * 기록이고, 그 다음이 사람의 문장이고, AI가 쓴 것은 마지막이다. AI 요약을
 * 위에 두면 가족이 남긴 말이 요약의 각주가 된다.
 */

/** 기억 한 줄 — 원문과 다듬은 문장을 함께 보여준다 */
function MemoryBlock({
  memory,
  accent,
  onDelete,
}: {
  memory: MemoryEntry
  accent?: boolean
  /** 지우기. 서버가 막으면 그 이유를 담은 오류를 던진다 (여기서 받아 적는다) */
  onDelete: (memoryId: string) => Promise<void>
}) {
  const [showRaw, setShowRaw] = useState(false)
  const polished = memory.polished && memory.polished !== memory.content ? memory.polished : null
  const audios = memory.media.filter((m) => m.media_type === 'audio')
  const visuals = memory.media.filter((m) => m.media_type !== 'audio')

  return (
    <div className="rounded bg-ink-50 px-5 py-4">
      <p className="t-caption m-0 mb-1.5" style={accent ? { color: 'var(--accent-ink)' } : undefined}>
        {memory.contributor?.name || '가족'}
        {memory.contributor?.relation ? ` · ${memory.contributor.relation}` : ''}
        {memory.created_at ? ` · ${memory.created_at.slice(0, 10)}` : ''}
        {memory.differs && ' · 조금 다르게 기억'}
      </p>

      <p className="t-body-sm m-0 whitespace-pre-wrap text-ink-700">
        {showRaw ? memory.content : polished || memory.content}
      </p>

      {/* 다듬은 문장은 AI가 쓴 것이다. 원문을 되짚을 수 있게 둔다 */}
      {polished && (
        <button onClick={() => setShowRaw((v) => !v)} className="btn-link mt-2 text-[11px]">
          {showRaw ? 'AI가 정리한 문장 보기' : '말한 그대로 보기'}
        </button>
      )}
      {polished && !showRaw && (
        <p className="t-caption m-0 mt-1">AI가 읽기 좋게 정리했습니다. 원문은 그대로 보관됩니다.</p>
      )}

      {/*
        원문 아래에 맥락을 붙인다 (원문 → 맥락 → 연결된 사진 → 반영 여부).
        순서가 뒤집히면 사람이 남긴 말이 추출 결과의 각주가 된다.
      */}
      <MemoryContextNote context={memory.context} detailed />


      {visuals.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {visuals.map((item) =>
            item.media_type === 'video' ? (
              <video
                key={item.id}
                src={mediaUrl(item.file_path)}
                poster={mediaUrl(item.thumbnail_path)}
                preload="none"
                controls
                className="h-24 w-[132px] rounded bg-ink-100 object-cover"
              />
            ) : (
              <img
                key={item.id}
                src={mediaUrl(item.thumbnail_path || item.file_path)}
                alt=""
                className="h-24 w-[132px] rounded bg-ink-100 object-cover"
              />
            ),
          )}
        </div>
      )}

      {audios.length > 0 && (
        <div className="mt-3 flex flex-col gap-2">
          {audios.map((item) => (
            <AudioClip
              key={item.id}
              compact
              clip={{
                id: item.id,
                file_path: item.file_path,
                speaker_id: memory.contributor?.id,
                speaker_name: memory.contributor?.name,
                duration_sec: item.duration_sec || 0,
                transcript: item.transcript,
                waveform: item.waveform || [],
                recorded_at: (memory.created_at || '').slice(0, 10),
                question: item.question,
              }}
            />
          ))}
        </div>
      )}

      <MemoryDeleteButton memory={memory} onDelete={onDelete} />
    </div>
  )
}

export default function MemoryDetailPage() {
  const { eventId } = useParams<{ eventId: string }>()
  const [detail, setDetail] = useState<MemoryDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [composing, setComposing] = useState(false)
  const [storyBusy, setStoryBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  /* 방금 지운 뒤 서버가 밝힌 것 — 무엇이 남았고, 이야기가 왜 사라졌는지 */
  const [removed, setRemoved] = useState<string | null>(null)

  const load = () => {
    if (!eventId) return Promise.resolve()
    return getMemoryDetail(eventId)
      .then(setDetail)
      .catch((e) => {
        console.error(e)
        setError('추억을 불러오지 못했습니다.')
      })
  }

  useEffect(() => {
    setLoading(true)
    load().finally(() => setLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [eventId])

  const toggleEcho = async () => {
    if (!eventId) return
    setBusy(true)
    try {
      const res = await echoMemory(eventId)
      setDetail((prev) =>
        prev
          ? { ...prev, i_echoed: res.echoed, echo_count: res.echo_count, echoed_by: res.echoed_by }
          : prev,
      )
      invalidateEvents()
    } catch (e) {
      console.error(e)
      setError('기억나요 표시를 남기지 못했습니다.')
    } finally {
      setBusy(false)
    }
  }

  /**
   * 기억 하나를 지운다.
   *
   * 지운 뒤 상세를 다시 받아온다. 문장 하나가 빠지면 최초 작성자의 기억 · 함께
   * 기억한 이야기 · 상태 알약이 함께 움직이므로, 화면에서 한 칸만 지워 맞추려
   * 들면 서버와 어긋난다.
   *
   * 오류는 삼키지 않고 그대로 올려보낸다 — 누른 기억 블록이 자기 자리에서 이유를
   * 보여줘야 한다.
   */
  const removeMemory = async (memoryId: string) => {
    if (!eventId) return
    setError(null)
    const result = await deleteMemoryEntry(eventId, memoryId)
    setRemoved(result.message)
    // 홈·지도·TV가 세는 기억 수와 상태에서도 즉시 빠져야 한다
    invalidateEvents()
    await load()
  }

  const makeStory = async () => {
    if (!eventId) return
    setStoryBusy(true)
    setError(null)
    try {
      const res = await composeTogetherStory(eventId)
      setDetail((prev) =>
        prev
          ? {
              ...prev,
              together_story: res.story,
              together_story_at: res.at,
              together_story_stale: false,
            }
          : prev,
      )
    } catch (e) {
      console.error(e)
      setError('이야기를 만들지 못했습니다. 가족의 기억이 쌓이면 다시 시도해 보세요.')
    } finally {
      setStoryBusy(false)
    }
  }

  if (loading) {
    return (
      <Page width={880}>
        <p className="t-caption">불러오는 중…</p>
      </Page>
    )
  }

  if (!detail) {
    return (
      <Page width={880}>
        <p className="t-body-sm text-ink-400">{error || '추억을 찾을 수 없습니다.'}</p>
        <Link to="/continue" className="btn-link mt-4 inline-block">
          기억 이어가기로 돌아가기
        </Link>
      </Page>
    )
  }

  const config = STATE_CONFIG[detail.state] ?? STATE_CONFIG.alone
  const visuals = detail.media.filter((m) => m.media_type !== 'audio')
  const audios = detail.media.filter((m) => m.media_type === 'audio')

  return (
    <Page width={880}>
      <PageHeader
        eyebrow="Memory"
        title={detail.title}
        lead={
          detail.author?.name
            ? `${detail.author.name}님이 만든 추억입니다. 기억나는 것이 있으면 더해 주세요.`
            : undefined
        }
        action={
          <span className="pill" style={{ background: config.bg, color: config.fg }}>
            {config.label}
          </span>
        }
      />

      {/*
        지운 뒤에 서버가 밝힌 것을 그대로 적는다. "지웠습니다" 한 마디로 끝내면
        함께 올린 목소리까지 사라진 줄 알고, 이야기가 왜 없어졌는지도 모른다.
      */}
      {removed && (
        <p className="t-body-sm m-0 mt-6" style={{ color: 'var(--critical-ink)' }}>
          {removed}
        </p>
      )}

      {/* 1. 사진 · 영상 */}
      {visuals.length > 0 && (
        <div className="mt-8 grid grid-cols-3 gap-2">
          {visuals.map((item) =>
            item.media_type === 'video' ? (
              <video
                key={item.id}
                src={mediaUrl(item.file_path)}
                poster={mediaUrl(item.thumbnail_path)}
                preload="none"
                controls
                className="h-[168px] w-full rounded bg-ink-50 object-cover"
              />
            ) : (
              <img
                key={item.id}
                src={mediaUrl(item.thumbnail_path || item.file_path)}
                alt=""
                className="h-[168px] w-full rounded bg-ink-50 object-cover"
              />
            ),
          )}
        </div>
      )}

      {/* 2. 제목 · 날짜 · 장소 · 함께한 사람 */}
      <div className="mt-8 flex flex-wrap gap-x-10 gap-y-4">
        <span>
          <span className="t-eyebrow block text-ink-300">날짜</span>
          <span className="t-body-sm text-ink-700">{detail.date_start || '날짜 미상'}</span>
        </span>
        <span>
          <span className="t-eyebrow block text-ink-300">장소</span>
          <span className="t-body-sm text-ink-700">{detail.place?.name || '기록 없음'}</span>
        </span>
        <span className="min-w-0">
          <span className="t-eyebrow block text-ink-300">함께한 사람</span>
          <span className="t-body-sm text-ink-700">
            {detail.participants.length > 0
              ? detail.participants.map((p) => p.name).join(' · ')
              : '아직 기록되지 않았습니다'}
          </span>
        </span>
      </div>

      {/* 가족이 남긴 목소리 (사건에 직접 붙은 녹음) */}
      {audios.length > 0 && (
        <div className="mt-6 flex flex-col gap-2">
          {audios.map((item) => (
            <AudioClip
              key={item.id}
              clip={{
                id: item.id,
                file_path: item.file_path,
                event_id: detail.id,
                event_title: detail.title,
                speaker_id: item.speaker_id,
                duration_sec: item.duration_sec || 0,
                transcript: item.transcript,
                waveform: item.waveform || [],
                question: item.question,
              }}
            />
          ))}
        </div>
      )}

      {/* 3. 최초 작성자의 기억 */}
      <section className="mt-10">
        <p className="t-eyebrow m-0 mb-3 text-ink-300">최초 작성자의 기억</p>
        {detail.author_memory ? (
          <MemoryBlock memory={detail.author_memory} accent onDelete={removeMemory} />
        ) : (
          <p className="t-body-sm m-0 text-ink-300">
            {detail.contributions.length > 0
              ? '만든 사람의 기억은 지워졌습니다. 가족이 더한 기억은 아래에 그대로 있습니다.'
              : '아직 이 추억에 남은 기억 문장이 없습니다.'}
          </p>
        )}
      </section>

      {/* 4. 나도 기억나요 · 내 기억 더하기 */}
      <section className="mt-6">
        <div className="flex flex-wrap items-center gap-2.5">
          <button
            onClick={toggleEcho}
            disabled={busy}
            className="flex cursor-pointer items-center gap-1.5 rounded bg-transparent px-3.5 py-2
                       text-[13px] disabled:opacity-40"
            style={
              detail.i_echoed
                ? { border: '1px solid var(--positive)', color: 'var(--positive-ink)' }
                : { border: '1px solid var(--border-strong)', color: 'var(--ink-500)' }
            }
          >
            <Heart size={14} fill={detail.i_echoed ? 'currentColor' : 'none'} />
            나도 기억나요
            {detail.echo_count > 0 && ` ${detail.echo_count}`}
          </button>

          <button
            onClick={() => setComposing((v) => !v)}
            className="btn-primary flex items-center gap-1.5"
          >
            <Plus size={15} />내 기억 더하기
          </button>
        </div>

        {detail.echoed_by.length > 0 && (
          <p className="t-caption m-0 mt-2.5">
            {detail.echoed_by.map((p) => p.name).join(' · ')}도 기억한다고 남겼습니다
          </p>
        )}

        {composing && (
          <div className="mt-4">
            <MemoryComposer
              eventId={detail.id}
              placeholder={`'${detail.title}'에서 기억나는 것을 적어 주세요.`}
              onCancel={() => setComposing(false)}
              onSaved={() => {
                setComposing(false)
                load()
              }}
            />
          </div>
        )}
      </section>

      {/* 5. 가족이 더한 기억 */}
      <section className="mt-10">
        <p className="t-eyebrow m-0 mb-3 text-ink-300">
          가족이 더한 기억 {detail.contributions.length > 0 && detail.contributions.length}
        </p>
        {detail.contributions.length === 0 ? (
          <p className="t-body-sm m-0 text-ink-300">
            아직 없습니다. 가족은 원할 때만 기억을 더합니다.
          </p>
        ) : (
          <div className="flex flex-col gap-2.5">
            {detail.contributions.map((memory) => (
              <MemoryBlock key={memory.id} memory={memory} onDelete={removeMemory} />
            ))}
          </div>
        )}
      </section>

      {/* 6. 서로 다르게 기억하는 경우 */}
      {detail.varied && (
        <p
          className="t-body-sm m-0 mt-6 rounded px-5 py-4"
          style={{ background: 'var(--critical-soft)', color: 'var(--critical-ink)' }}
        >
          가족들이 조금 다르게 기억하고 있어요. 어느 쪽도 정답으로 정하지 않고 그대로
          보존합니다.
        </p>
      )}

      {/* 7. AI가 만든 함께 기억한 이야기 */}
      <section className="mt-10 pt-8" style={{ borderTop: '1px solid var(--border)' }}>
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="t-eyebrow m-0 mb-1.5 text-ink-300">함께 기억한 이야기</p>
            <p className="t-caption m-0 max-w-[39em]">
              여러 사람의 기억을 AI가 하나의 이야기로 엮습니다. 누가 맞는지는 판단하지 않고,
              서로 다른 부분은 그대로 남깁니다.
            </p>
          </div>
          <button
            onClick={makeStory}
            disabled={storyBusy}
            className="btn-outline flex items-center gap-1.5 disabled:opacity-40"
          >
            <Sparkles size={14} />
            {storyBusy
              ? '엮는 중…'
              : detail.together_story
                ? '다시 만들기'
                : '이야기 만들기'}
          </button>
        </div>

        {detail.together_story ? (
          <div className="surface mt-5 p-6">
            <p className="t-body-sm m-0 whitespace-pre-wrap leading-relaxed text-ink-700">
              {detail.together_story}
            </p>
            <p className="t-caption m-0 mt-3">
              AI가 가족의 기억 {detail.contributions.length + (detail.author_memory ? 1 : 0)}개로
              썼습니다
              {detail.together_story_at ? ` · ${detail.together_story_at.slice(0, 10)}` : ''}
            </p>
            {detail.together_story_stale && (
              <p className="t-caption m-0 mt-1" style={{ color: 'var(--accent-ink)' }}>
                이야기를 만든 뒤 새 기억이 더해졌습니다. 다시 만들면 함께 반영됩니다.
              </p>
            )}
          </div>
        ) : (
          <p className="t-body-sm m-0 mt-5 text-ink-300">
            아직 만들지 않았습니다.
          </p>
        )}
      </section>

      {error && (
        <p className="t-body-sm mt-6" style={{ color: 'var(--critical-ink)' }}>
          {error}
        </p>
      )}

      <div className="mt-10">
        <Link to="/continue" className="btn-link">
          ← 기억 이어가기
        </Link>
      </div>
    </Page>
  )
}
