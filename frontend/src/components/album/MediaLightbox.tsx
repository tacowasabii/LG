/**
 * 사진 상세 — 전체 화면 Lightbox
 *
 * 페이지를 옮기지 않는다. 사진첩에서 사진을 훑다가 하나를 크게 보고 다시
 * 훑는 것이 이 화면의 동작이고, 그 사이에 주소가 바뀌면 스크롤 위치와 필터가
 * 흔들린다.
 *
 * 원본은 여기서 처음 부른다 (그리드는 썸네일만 썼다).
 *
 * 카메라·좌표·장면 설명은 목록에 없어서 열 때 GET /api/media/{id}로 받는다.
 * 목록 60건에 그 값을 다 실으면 훑어보기만 하는 사람도 쓰지 않을 것을 받는다.
 * 못 받아도 화면은 그대로 뜬다 — 사진을 크게 보는 일이 카메라 정보에 걸려
 * 있으면 안 된다.
 *
 * 이전·다음은 목록의 순서를 그대로 따른다. 마지막에 가까워지면 다음 페이지를
 * 요청해(onNeedMore) 페이지 경계에서 멈추지 않게 한다.
 */

import { ReactNode, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  Link2,
  Lock,
  MoreHorizontal,
  Trash2,
  Users,
  X,
} from 'lucide-react'
import {
  AlbumMediaItem,
  CascadePreview,
  EventListItem,
  MediaDetail,
  addMediaToMemory,
  deleteMedia,
  getDeleteCascade,
  getMediaDetail,
  mediaUrl,
  readDetail,
  setMediaPersons,
} from '../../lib/api'
import { invalidateEvents, invalidateVoiceClips } from '../../lib/useGraphData'
import { formatDuration } from './AlbumGrid'

const VISIBILITY_LABEL: Record<string, string> = {
  family: '가족 전체',
  partial: '일부에게만',
  private: '나만 보기',
}

interface MediaLightboxProps {
  items: AlbumMediaItem[]
  index: number
  /** 조건에 맞는 전체 개수. "12 / 38"의 뒤 숫자 */
  total: number
  members: Array<{ id: string; name: string; relation?: string }>
  /** 추억에 연결할 때 고를 목록 */
  events: EventListItem[]
  onIndexChange: (index: number) => void
  onClose: () => void
  /** 목록 끝에 다다랐을 때 다음 페이지를 부른다 */
  onNeedMore: () => void
  /** 상세에서 바꾼 것을 목록에도 반영한다 (닫고 나서 어긋나 보이지 않게) */
  onItemUpdate: (id: string, patch: Partial<AlbumMediaItem>) => void
  /** 지운 사진을 목록에서 뺀다. 목록이 비면 부모가 이 화면을 닫는다 */
  onItemDelete: (id: string) => void
}

export default function MediaLightbox({
  items,
  index,
  total,
  members,
  events,
  onIndexChange,
  onClose,
  onNeedMore,
  onItemUpdate,
  onItemDelete,
}: MediaLightboxProps) {
  const item = items[index]
  const [detail, setDetail] = useState<MediaDetail | null>(null)
  const [pane, setPane] = useState<'none' | 'people' | 'event' | 'more' | 'delete'>('none')
  const [cascade, setCascade] = useState<CascadePreview | null>(null)
  const [saving, setSaving] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const touchStartX = useRef<number | null>(null)

  const last = items.length - 1
  const hasPrev = index > 0
  const hasNext = index < last

  // 이전·다음은 부모가 가진 목록 안에서만 움직인다
  const go = (next: number) => {
    if (next < 0 || next > last) return
    onIndexChange(next)
  }

  // 끝에 가까워지면 다음 페이지를 미리 부른다 — 넘기다가 페이지 경계에서 멈추지 않게
  useEffect(() => {
    if (index >= items.length - 3) onNeedMore()
  }, [index, items.length, onNeedMore])

  // 사진이 바뀌면 곁들인 정보도 다시 받는다
  useEffect(() => {
    if (!item) return
    setDetail(null)
    setPane('none')
    setCascade(null)
    setNotice(null)

    let alive = true
    getMediaDetail(item.id)
      .then((d) => {
        if (alive) setDetail(d)
      })
      .catch((e) => {
        // 사진 자체는 이미 보이고 있다. 곁들인 정보만 없는 것이므로 조용히 넘긴다.
        console.error('[album] 상세 정보를 불러오지 못했습니다', e)
      })
    return () => {
      alive = false
    }
  }, [item?.id])

  // 키보드 — 방향키로 넘기고 Esc로 닫는다
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (pane !== 'none') {
          setPane('none')
          return
        }
        onClose()
      }
      if (e.key === 'ArrowLeft') go(index - 1)
      if (e.key === 'ArrowRight') go(index + 1)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [index, last, pane, onClose])

  // 열려 있는 동안 뒤 화면이 따라 스크롤되지 않게
  useEffect(() => {
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = previous
    }
  }, [])

  if (!item) return null

  const savePeople = async (personIds: string[]) => {
    setSaving(true)
    try {
      const result = await setMediaPersons(item.id, personIds)
      const next = result.detected_faces
        .map((id) => members.find((m) => m.id === id))
        .filter((m): m is { id: string; name: string; relation?: string } => Boolean(m))
        .map((m) => ({ id: m.id, name: m.name, relation: m.relation ?? null }))
      onItemUpdate(item.id, { people: next })
      setNotice('사진 속 인물을 저장했습니다.')
    } catch (e) {
      setNotice(e instanceof Error ? e.message : '저장하지 못했습니다.')
    } finally {
      setSaving(false)
    }
  }

  const linkToEvent = async (event: EventListItem) => {
    setSaving(true)
    try {
      await addMediaToMemory(event.id, [item.id])
      onItemUpdate(item.id, { event: { id: event.id, title: event.title } })
      setPane('none')
      setNotice(`"${event.title}"에 이었습니다.`)
    } catch (e) {
      setNotice(e instanceof Error ? e.message : '잇지 못했습니다.')
    } finally {
      setSaving(false)
    }
  }

  /**
   * 지우기 전에 무엇이 함께 사라지는지 먼저 보여준다 (기획안 08장 삭제 전파).
   *
   * 공개·동의 화면이 쓰는 것과 같은 미리보기다. 못 받아오면 지우는 단추를
   * 내주지 않는다 — 무엇을 지우는지 모르는 채로 되돌릴 수 없는 일을 하게
   * 만들지 않는다.
   */
  const openDelete = async () => {
    setPane('delete')
    setCascade(null)
    setNotice(null)
    setSaving(true)
    try {
      setCascade(await getDeleteCascade(item.id))
    } catch (e) {
      setNotice(readDetail(e, '삭제 영향을 불러오지 못했습니다.'))
    } finally {
      setSaving(false)
    }
  }

  /**
   * 원본을 지운다. 파일과 노드가 함께 사라지고, 그 원본을 가리키던 연결도
   * 끊긴다. 가족이 남긴 기억 문장은 남는다 — 지우는 것은 원본이다.
   *
   * 남의 기록이면 서버가 403으로 막는다. 화면에서 미리 단추를 감추지 않고
   * 서버가 밝힌 이유를 그대로 보여준다 — 왜 못 지우는지가 "지울 수 없음"보다
   * 쓸모 있고, 권한 규칙을 두 곳에 두면 어긋난다.
   */
  const removeMedia = async () => {
    setSaving(true)
    setNotice(null)
    try {
      await deleteMedia(item.id)
      // 홈·지도·TV의 개수와 썸네일에서도 즉시 빠져야 한다
      invalidateEvents()
      invalidateVoiceClips()
      onItemDelete(item.id)
    } catch (e) {
      setNotice(readDetail(e, '지우지 못했습니다.'))
    } finally {
      setSaving(false)
    }
  }

  const taggedIds = item.people.map((p) => p.id)

  return (
    <div
      /*
        어두운 면에서는 와인색 강조색이 보이지 않는다. 디자인 체계가 정한 방법
        그대로 data-theme으로 강조색을 갈아 끼운다 (index.css) — 여기 버튼들은
        배경과 무관하게 var(--accent)만 쓰면 된다.
      */
      data-theme="dark"
      className="fixed inset-0 z-[70] flex flex-col"
      style={{ background: 'rgba(14,13,11,0.94)' }}
      role="dialog"
      aria-modal="true"
      aria-label="사진 크게 보기"
    >
      <div
        className="flex shrink-0 items-center justify-between gap-4 px-5 py-3"
        style={{ borderBottom: '1px solid rgba(255,255,255,0.12)' }}
      >
        <span className="t-mono text-[12px] text-white/70">
          {index + 1} / {total}
        </span>
        <span className="truncate text-[13px] text-white/70">{item.original_filename}</span>
        <button
          onClick={onClose}
          className="flex cursor-pointer items-center gap-1 border-0 bg-transparent text-[13px]
                     text-white/70 hover:text-white"
          aria-label="닫기"
        >
          <X size={16} strokeWidth={2} />
          닫기
        </button>
      </div>

      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        <div
          className="relative flex min-h-0 flex-1 items-center justify-center p-4"
          onTouchStart={(e) => {
            touchStartX.current = e.touches[0]?.clientX ?? null
          }}
          onTouchEnd={(e) => {
            const startX = touchStartX.current
            touchStartX.current = null
            if (startX == null) return
            const delta = (e.changedTouches[0]?.clientX ?? startX) - startX
            // 손가락이 조금 흔들린 것과 넘긴 것을 가른다
            if (Math.abs(delta) < 48) return
            go(delta < 0 ? index + 1 : index - 1)
          }}
        >
          {item.media_type === 'video' ? (
            <video
              key={item.id}
              src={mediaUrl(item.file_path)}
              controls
              playsInline
              className="max-h-full max-w-full"
            />
          ) : (
            <img
              key={item.id}
              src={mediaUrl(item.file_path)}
              alt={item.original_filename}
              className="max-h-full max-w-full object-contain"
            />
          )}

          {hasPrev && (
            <button
              onClick={() => go(index - 1)}
              className="absolute left-3 flex h-11 w-11 cursor-pointer items-center justify-center
                         rounded-full border-0 text-white"
              style={{ background: 'rgba(14,13,11,0.55)' }}
              aria-label="이전 사진"
            >
              <ChevronLeft size={22} strokeWidth={2} />
            </button>
          )}
          {hasNext && (
            <button
              onClick={() => go(index + 1)}
              className="absolute right-3 flex h-11 w-11 cursor-pointer items-center justify-center
                         rounded-full border-0 text-white"
              style={{ background: 'rgba(14,13,11,0.55)' }}
              aria-label="다음 사진"
            >
              <ChevronRight size={22} strokeWidth={2} />
            </button>
          )}
        </div>

        <aside
          className="w-full shrink-0 overflow-y-auto px-6 py-5 lg:w-[340px]"
          style={{
            borderTop: '1px solid rgba(255,255,255,0.12)',
            background: 'rgba(255,255,255,0.03)',
          }}
        >
          <dl className="m-0 flex flex-col gap-2.5">
            <Row label="촬영일">
              {item.has_exif && item.captured_at
                ? item.captured_at.slice(0, 10)
                : '카메라가 남긴 촬영일이 없습니다'}
            </Row>
            {!item.has_exif && (
              <Row label="올린 날">{(item.uploaded_at || '').slice(0, 10)}</Row>
            )}
            <Row label="장소">{item.place?.name || '기록 없음'}</Row>
            <Row label="카메라">{detail?.exif_camera || '기록 없음'}</Row>
            {item.media_type === 'video' && (
              <Row label="길이">{formatDuration(item.duration_sec) || '기록 없음'}</Row>
            )}
            <Row label="추억">
              {item.event ? (
                <Link to={`/memory/${item.event.id}`}>
                  {item.event.title}
                </Link>
              ) : (
                '아직 어느 추억에도 붙지 않았습니다'
              )}
            </Row>
            <Row label="사진 속 인물">
              {item.people.length > 0
                ? item.people.map((p) => p.name).join(' · ')
                : '지목된 사람이 없습니다'}
            </Row>
            <Row label="공개 범위">
              {VISIBILITY_LABEL[item.visibility] ?? item.visibility}
            </Row>
            <Row label="원본 파일">{item.original_filename}</Row>
          </dl>

          {/*
            AI가 쓴 장면 설명은 그렇다고 밝힌 것만 보여 준다. 사람이 적은 것과
            모델이 쓴 것을 같은 글로 두면 어느 쪽인지 되짚을 수 없다.
          */}
          {detail?.scene_description && (
            <p className="m-0 mt-4 text-[12px] leading-relaxed text-white/60">
              {detail.scene_description}
              {detail.scene_source === 'ai_vision' && (
                <span className="ml-1.5 text-white/40">· AI가 사진을 보고 쓴 설명</span>
              )}
            </p>
          )}

          <div className="mt-5 flex flex-wrap gap-1.5">
            {item.event && (
              <Link
                to={`/memory/${item.event.id}`}
                className="btn-outline no-underline hover:no-underline"
              >
                추억 보기
              </Link>
            )}
            {!item.event && (
              <button
                onClick={() => setPane(pane === 'event' ? 'none' : 'event')}
                className="btn-outline flex items-center gap-1"
              >
                <Link2 size={12} strokeWidth={2} />
                추억에 연결
              </button>
            )}
            <button
              onClick={() => setPane(pane === 'people' ? 'none' : 'people')}
              className="flex cursor-pointer items-center gap-1 rounded border border-white/20
                         bg-transparent px-3.5 py-[7px] text-[12px] text-white/75
                         transition-colors duration-150 ease-out hover:bg-white/10"
            >
              <Users size={12} strokeWidth={2} />
              사진 속 인물 수정
            </button>
            <Link
              to="/privacy"
              className="flex items-center gap-1 rounded border border-white/20 px-3.5 py-[7px]
                         text-[12px] text-white/75 no-underline transition-colors duration-150
                         ease-out hover:bg-white/10 hover:no-underline"
            >
              <Lock size={12} strokeWidth={2} />
              공개 범위 설정
            </Link>
            <a
              href={mediaUrl(item.file_path)}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-1 rounded border border-white/20 px-3.5 py-[7px]
                         text-[12px] text-white/75 no-underline transition-colors duration-150
                         ease-out hover:bg-white/10 hover:no-underline"
            >
              <ExternalLink size={12} strokeWidth={2} />
              원본 보기
            </a>
            {/*
              삭제는 사진첩 전면에 두지 않는다. 훑어보는 화면에서 한 번의 실수로
              원본이 사라지면 안 된다 — 더보기 안에 둔다.
            */}
            <button
              onClick={() => setPane(pane === 'more' || pane === 'delete' ? 'none' : 'more')}
              className="flex cursor-pointer items-center gap-1 rounded border border-white/20
                         bg-transparent px-2.5 py-[7px] text-[12px] text-white/75
                         transition-colors duration-150 ease-out hover:bg-white/10"
              aria-label="더보기"
              aria-expanded={pane === 'more' || pane === 'delete'}
            >
              <MoreHorizontal size={14} strokeWidth={2} />
            </button>
          </div>

          {notice && <p className="m-0 mt-3 text-[12px] text-white/70">{notice}</p>}

          {pane === 'more' && (
            <div className="mt-3 flex flex-col items-start">
              <button
                onClick={openDelete}
                className="flex cursor-pointer items-center gap-1.5 border-0 bg-transparent
                           px-0 py-1 text-[12px]"
                style={{ color: 'var(--critical)' }}
              >
                <Trash2 size={13} strokeWidth={2} />
                이 사진 삭제
              </button>
            </div>
          )}

          {pane === 'delete' && (
            /*
              공개·동의 화면의 삭제 영향 카드와 같은 모양이다. 어두운 면 위에서도
              밝은 경고색 면을 그대로 쓴다 — 되돌릴 수 없는 일에서 색이 조용해지면
              안 되고, 이 색 조합은 이미 그 화면에서 쓰이고 있다.
            */
            <div
              className="mt-4 rounded-lg p-5"
              style={{ background: 'var(--critical-soft)' }}
            >
              <p className="t-body-sm m-0" style={{ color: 'var(--critical-ink)' }}>
                지울 원본 · {cascade?.target || item.original_filename}
              </p>
              {cascade?.scene_description && (
                <p
                  className="t-caption m-0 mt-1"
                  style={{ color: 'var(--critical-ink)', opacity: 0.75 }}
                >
                  {cascade.scene_description}
                </p>
              )}

              {cascade ? (
                <>
                  <p className="t-eyebrow mb-2 mt-4" style={{ color: 'var(--critical-ink)' }}>
                    함께 사라지는 것
                  </p>
                  {cascade.derived.map((d) => (
                    <div
                      key={d.label + d.detail}
                      className="flex justify-between gap-5 py-[7px]"
                      style={{ borderBottom: '1px solid rgba(194,84,42,0.18)' }}
                    >
                      <span className="t-body-sm" style={{ color: 'var(--critical-ink)' }}>
                        {d.label}
                      </span>
                      <span
                        className="t-mono text-[11px] opacity-70"
                        style={{ color: 'var(--critical-ink)' }}
                      >
                        {d.detail}
                      </span>
                    </div>
                  ))}
                  <p className="t-caption mt-3.5" style={{ color: 'var(--critical-ink)' }}>
                    가족이 남긴 기억 문장은 지워지지 않습니다. 원본과의 연결만 끊깁니다.
                  </p>

                  <div className="mt-4 flex flex-wrap items-center gap-3">
                    <button
                      onClick={removeMedia}
                      disabled={saving}
                      className="cursor-pointer rounded border-0 px-3.5 py-1.5 text-xs
                                 disabled:opacity-40"
                      style={{ background: 'var(--critical-ink)', color: 'var(--paper)' }}
                    >
                      {saving ? '지우는 중…' : '정말 지웁니다'}
                    </button>
                    <button
                      onClick={() => setPane('none')}
                      disabled={saving}
                      className="cursor-pointer rounded border bg-transparent px-3.5 py-1.5 text-xs"
                      style={{
                        borderColor: 'rgba(194,84,42,0.35)',
                        color: 'var(--critical-ink)',
                      }}
                    >
                      취소
                    </button>
                  </div>
                </>
              ) : (
                <p className="t-caption m-0 mt-3" style={{ color: 'var(--critical-ink)' }}>
                  {saving ? '삭제 영향을 확인하는 중…' : '삭제 영향을 확인하지 못해 지우지 않습니다.'}
                </p>
              )}
            </div>
          )}

          {pane === 'people' && (
            <div className="mt-4 pt-4" style={{ borderTop: '1px solid rgba(255,255,255,0.12)' }}>
              <p className="m-0 mb-2 text-[12px] text-white/60">
                이 사진에 있는 사람을 고릅니다. 얼굴 인식이 없으므로 고른 사람만 붙습니다.
              </p>
              <div className="flex flex-wrap gap-1.5">
                {members.map((m) => {
                  const on = taggedIds.includes(m.id)
                  return (
                    <button
                      key={m.id}
                      disabled={saving}
                      onClick={() =>
                        savePeople(
                          on ? taggedIds.filter((id) => id !== m.id) : [...taggedIds, m.id],
                        )
                      }
                      className={`cursor-pointer rounded-full border px-3 py-1 text-[12px]
                                  transition-colors duration-150 ease-out ${
                                    on ? '' : 'border-white/20 bg-transparent text-white/75 hover:bg-white/10'
                                  }`}
                      /*
                        고른 사람은 강조색으로 표시한다. 유틸리티(bg-accent-soft)가
                        아니라 var()를 쓰는 이유는 이 면이 어둡기 때문이다 —
                        data-theme이 갈아 끼운 밝은 베리색이 여기로 들어온다.
                      */
                      style={
                        on
                          ? {
                              borderColor: 'var(--accent)',
                              background: 'var(--accent-soft)',
                              color: 'var(--accent-ink)',
                            }
                          : undefined
                      }
                    >
                      {m.name}
                    </button>
                  )
                })}
              </div>
            </div>
          )}

          {pane === 'event' && (
            <div className="mt-4 pt-4" style={{ borderTop: '1px solid rgba(255,255,255,0.12)' }}>
              <p className="m-0 mb-2 text-[12px] text-white/60">
                어느 추억의 기록인지 고릅니다. AI가 임의로 붙이지 않습니다.
              </p>
              <div className="flex max-h-[220px] flex-col gap-1 overflow-y-auto">
                {events.length === 0 && (
                  <span className="text-[12px] text-white/50">아직 만들어진 추억이 없습니다.</span>
                )}
                {events.map((event) => (
                  <button
                    key={event.id}
                    disabled={saving}
                    onClick={() => linkToEvent(event)}
                    className="cursor-pointer rounded border-0 bg-transparent px-2 py-1.5 text-left
                               text-[12px] text-white/75 hover:bg-white/10"
                  >
                    <span className="t-mono mr-2 text-[11px] text-white/45">
                      {(event.date_start || '').slice(0, 4) || '----'}
                    </span>
                    {event.title}
                  </button>
                ))}
              </div>
            </div>
          )}
        </aside>
      </div>
    </div>
  )
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex justify-between gap-4">
      <dt className="shrink-0 text-[11px] uppercase tracking-eyebrow text-white/40">{label}</dt>
      <dd className="m-0 min-w-0 break-words text-right text-[12px] text-white/80">{children}</dd>
    </div>
  )
}
