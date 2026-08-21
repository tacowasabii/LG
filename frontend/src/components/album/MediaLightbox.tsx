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

import { ReactNode, useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  Link2,
  Lock,
  Trash2,
  Users,
  X,
} from 'lucide-react'
import {
  AlbumMediaItem,
  CascadePreview,
  EventListItem,
  FaceBox,
  MediaDetail,
  addMediaToMemory,
  deleteMedia,
  getDeleteCascade,
  assignMediaFace,
  detectMediaFaces,
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

/**
 * 사진 위에 얼굴 한 자리를 표시한다.
 *
 * 이름이 붙은 얼굴은 강조색 테두리에 이름표를, 못 붙인 얼굴은 옅은 점선에
 * "누구인가요?"를 얹는다. 모르는 얼굴을 아예 안 그리면 사용자는 AI가 그 얼굴을
 * 못 봤다고 생각한다 — 찾았지만 가리지 못했다는 것과 다른 이야기다.
 */
function FaceMarker({
  face,
  members,
  onAssign,
  busy,
}: {
  face: FaceBox
  members: LightboxMember[]
  /** 이 얼굴을 이 사람으로 정한다. null이면 이름을 뗀다 */
  onAssign: (personId: string | null) => void
  busy: boolean
}) {
  const [open, setOpen] = useState(false)
  const known = Boolean(face.person_id)
  const label = known ? [face.relation, face.name].filter(Boolean).join(' ') : '누구인가요?'

  return (
    <div
      className="absolute"
      style={{
        left: face.left * 100 + '%',
        top: face.top * 100 + '%',
        width: face.width * 100 + '%',
        height: face.height * 100 + '%',
        border: known ? '2px solid var(--accent)' : '2px dashed rgba(250,250,247,0.6)',
        borderRadius: 4,
        boxShadow: '0 0 0 1px rgba(14,13,11,0.35)',
        background: open ? 'rgba(250,250,247,0.12)' : 'transparent',
      }}
      title={known ? `닮은 정도 ${face.similarity.toFixed(0)}%` : face.reason}
    >
      {/* 이름표를 누르면 그 얼굴이 누구인지 고른다. 얼굴 하나씩 정할 수 있어야
          "이 사진에 누가 있나요?" 알약보다 정확하다 — 알약은 사진 전체에
          붙이는 것이라 어느 얼굴이 누구인지 남지 않는다. */}
      <button
        onClick={() => setOpen((v) => !v)}
        disabled={busy}
        className="absolute cursor-pointer whitespace-nowrap rounded border-0 px-1.5 py-0.5
                   text-[11px] font-medium disabled:opacity-50"
        style={{
          left: -2,
          top: '100%',
          marginTop: 4,
          background: known ? 'var(--accent)' : 'rgba(14,13,11,0.72)',
          color: known ? 'var(--accent-fg)' : 'var(--paper)',
        }}
      >
        {label}
      </button>

      {open && (
        <div
          className="absolute z-20 flex max-w-[220px] flex-wrap gap-1 rounded p-2"
          style={{
            left: -2,
            top: '100%',
            marginTop: 28,
            background: 'rgba(14,13,11,0.92)',
            border: '1px solid rgba(255,255,255,0.18)',
          }}
        >
          {members.map((m) => (
            <button
              key={m.id}
              onClick={() => {
                onAssign(m.id)
                setOpen(false)
              }}
              disabled={busy}
              className="cursor-pointer rounded border-0 px-2 py-1 text-[11px] disabled:opacity-50"
              style={
                m.id === face.person_id
                  ? { background: 'var(--accent)', color: 'var(--accent-fg)' }
                  : { background: 'rgba(255,255,255,0.12)', color: 'var(--paper)' }
              }
            >
              {m.name}
            </button>
          ))}
          {known && (
            <button
              onClick={() => {
                onAssign(null)
                setOpen(false)
              }}
              disabled={busy}
              className="cursor-pointer rounded border-0 px-2 py-1 text-[11px] disabled:opacity-50"
              style={{ background: 'rgba(255,255,255,0.06)', color: 'rgba(250,250,247,0.7)' }}
            >
              이름 떼기
            </button>
          )}
        </div>
      )}
    </div>
  )
}


/** 이 화면이 쓰는 구성원 정보. 사진첩이 넘겨 주는 최소 모양이다 */
export interface LightboxMember {
  id: string
  name: string
  relation?: string | null
  thumbnail_url?: string | null
}

interface MediaLightboxProps {
  items: AlbumMediaItem[]
  index: number
  /** 조건에 맞는 전체 개수. "12 / 38"의 뒤 숫자 */
  total: number
  members: LightboxMember[]
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
  /** 얼굴 자리를 사진 위에 표시할까 (기본은 켠다 — 누가 누구인지가 이 화면의 질문이다) */
  const [showFaces, setShowFaces] = useState(true)
  const [detecting, setDetecting] = useState(false)
  const imgRef = useRef<HTMLImageElement | null>(null)
  /** 사진이 화면에 그려진 사각형 (부모 기준). 얼굴 상자를 여기에 맞춰 얹는다 */
  const [imgRect, setImgRect] = useState<{
    left: number
    top: number
    width: number
    height: number
  } | null>(null)
  const [faceError, setFaceError] = useState<string | null>(null)
  const faceBoxes = detail?.face_boxes ?? []

  /**
   * 그려진 사진의 자리를 잰다.
   *
   * max-w/max-h로 줄어든 실제 크기는 로드가 끝나야 정해지고, 창 크기가 바뀌면
   * 또 달라진다. offsetParent가 부모(relative)라서 offset 값을 그대로 쓴다.
   */
  const measureImage = useCallback(() => {
    const img = imgRef.current
    if (!img) return
    setImgRect({
      left: img.offsetLeft,
      top: img.offsetTop,
      width: img.offsetWidth,
      height: img.offsetHeight,
    })
  }, [])

  // 창 크기가 바뀌면 사진도 줄어든다. 상자가 따라가지 않으면 어긋난 자리에 남는다.
  useEffect(() => {
    window.addEventListener('resize', measureImage)
    return () => window.removeEventListener('resize', measureImage)
  }, [measureImage])

  // 사진을 넘기면 크기가 달라진다 (onLoad가 오기 전까지는 이전 사진 기준이다)
  useEffect(() => {
    setImgRect(null)
    setFaceError(null)
  }, [item.id])

  /** 얼굴 하나가 누구인지 정한다 (상자의 이름표를 눌러 고른 결과) */
  const assignFace = async (faceIndex: number, personId: string | null) => {
    setFaceError(null)
    setDetecting(true)
    try {
      const res = await assignMediaFace(item.id, faceIndex, personId)
      setDetail((prev) =>
        prev ? { ...prev, face_boxes: res.face_boxes, faces_source: 'user_input' } : prev,
      )
      // 사진첩 목록의 인물도 함께 맞춘다 (서버가 detected_faces를 정리해 준다)
      onItemUpdate(item.id, {
        people: res.detected_faces.map((id) => {
          const found = members.find((m) => m.id === id)
          return {
            id,
            name: found?.name || '',
            relation: found?.relation ?? null,
            thumbnail_url: found?.thumbnail_url ?? null,
          }
        }),
      })
    } catch (e) {
      console.error(e)
      setFaceError(readDetail(e, '얼굴에 이름을 붙이지 못했습니다.'))
    } finally {
      setDetecting(false)
    }
  }

  /** 얼굴을 다시 찾는다. 등록이 늘어난 뒤에 누르는 버튼이다 (유료 호출) */
  const redetect = async () => {
    if (detecting) return
    setDetecting(true)
    setFaceError(null)
    try {
      const res = await detectMediaFaces(item.id)
      setDetail((prev) => (prev ? { ...prev, face_boxes: res.face_boxes } : prev))
      if (res.face_boxes.length === 0) {
        setFaceError('이 사진에서 얼굴을 찾지 못했습니다.')
      }
      // 이름이 붙은 얼굴을 인물 목록에도 반영한다 (서버가 이미 맞춰 두었다)
      const named = res.face_boxes.filter((f) => f.person_id)
      if (named.length > 0) {
        onItemUpdate(item.id, {
          people: named.map((f) => ({
            id: f.person_id as string,
            name: f.name || '',
            relation: f.relation ?? null,
            thumbnail_url: null,
          })),
        })
      }
    } catch (e) {
      // 조용히 삼키면 버튼이 반짝하고 아무 일도 안 하는 것처럼 보인다.
      // 서버는 "얼굴 인식이 꺼져 있습니다 (AWS 자격증명이 없습니다)" 처럼
      // 화면이 지어낼 수 없는 이유를 준다.
      console.error(e)
      setFaceError(readDetail(e, '얼굴을 찾지 못했습니다. 잠시 뒤 다시 시도해 주세요.'))
    } finally {
      setDetecting(false)
    }
  }
  const [pane, setPane] = useState<'none' | 'people' | 'event' | 'delete'>('none')
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
      // 날짜까지 함께 넘긴다 — 사건별로 묶어 보는 중이면 새 묶음 머리에 바로 적힌다
      onItemUpdate(item.id, {
        event: { id: event.id, title: event.title, date: event.date_start ?? null },
      })
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
            /* 얼굴 상자는 그림이 실제로 그려진 자리 위에 얹는다.
               <img>를 div로 감싸면 안 된다 — 높이가 auto인 부모에 대한 퍼센트
               최대높이는 무시되어서 max-h-full이 죽고, 사진이 원본 크기로 커져
               상자가 화면 밖으로 밀린다. 그래서 감싸지 않고 그려진 사각형을
               재서(imgRect) 그 위에 겹치는 층을 따로 둔다. */
            <>
              <img
                key={item.id}
                ref={imgRef}
                src={mediaUrl(item.file_path)}
                alt={item.original_filename}
                onLoad={measureImage}
                className="max-h-full max-w-full object-contain"
              />
              {showFaces && imgRect && faceBoxes.length > 0 && (
                <div
                  className="absolute"
                  style={{
                    left: imgRect.left,
                    top: imgRect.top,
                    width: imgRect.width,
                    height: imgRect.height,
                  }}
                >
                  {faceBoxes.map((face, i) => (
                    <FaceMarker
                      key={i}
                      face={face}
                      members={members}
                      busy={detecting}
                      onAssign={(personId) => assignFace(i, personId)}
                    />
                  ))}
                </div>
              )}
            </>
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
              {detail?.faces_source === 'ai_vision' && (
                <span className="ml-1.5 text-white/40">· AI가 얼굴로 알아봄</span>
              )}
            </Row>
            {faceBoxes.length > 0 && (
              <Row label="찾은 얼굴">
                {faceBoxes.filter((f) => f.person_id).length}명 확인 ·{' '}
                {faceBoxes.filter((f) => !f.person_id).length}명 미상
                <span className="ml-1.5 text-white/40">(사진 위에 표시됩니다)</span>
              </Row>
            )}
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

            {item.media_type === 'photo' && faceBoxes.length > 0 && (
              <button
                onClick={() => setShowFaces((v) => !v)}
                className="flex cursor-pointer items-center gap-1 rounded border border-white/20
                           bg-transparent px-3.5 py-[7px] text-[12px] text-white/75
                           transition-colors duration-150 ease-out hover:bg-white/10"
              >
                {showFaces ? '얼굴 표시 끄기' : '얼굴 표시 켜기'}
              </button>
            )}

            {/* 유료 호출이라 여는 것만으로는 돌지 않는다. 얼굴 등록이 늘어난
                뒤에 다시 눌러 보라는 뜻의 버튼이다. */}
            {item.media_type === 'photo' && (
              <button
                onClick={redetect}
                disabled={detecting}
                className="flex cursor-pointer items-center gap-1 rounded border border-white/20
                           bg-transparent px-3.5 py-[7px] text-[12px] text-white/75
                           transition-colors duration-150 ease-out hover:bg-white/10
                           disabled:opacity-50"
              >
                {detecting
                  ? '얼굴을 찾고 있습니다…'
                  : faceBoxes.length > 0
                    ? '얼굴 다시 찾기'
                    : '얼굴 찾기'}
              </button>
            )}

            {/* 실패하면 이유를 그대로 밝힌다. 조용히 삼키면 버튼이 반짝하고
                아무 일도 안 하는 것처럼 보인다 (실제로 그랬다). */}
            {faceError && (
              <span className="self-center text-[12px]" style={{ color: 'var(--critical-ink)' }}>
                {faceError}
              </span>
            )}
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
              삭제를 더보기 안에 숨기지 않는다 — 찾느라 두 번 누르게 만드는 것이
              실수를 막아 주지도 않았다. 한 번의 실수를 막는 것은 아래 확인
              화면이다: 무엇이 함께 사라지는지 보여 준 뒤에야 지운다.
            */}
            <button
              onClick={openDelete}
              className="flex cursor-pointer items-center gap-1 rounded border
                         bg-transparent px-3.5 py-[7px] text-[12px]
                         transition-colors duration-150 ease-out"
              style={{ borderColor: 'rgba(224,122,95,0.5)', color: 'var(--critical-ink)' }}
              aria-expanded={pane === 'delete'}
            >
              <Trash2 size={13} strokeWidth={2} />
              이 사진 삭제
            </button>
          </div>

          {notice && <p className="m-0 mt-3 text-[12px] text-white/70">{notice}</p>}

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
                이 사진에 있는 사람을 고릅니다. AI가 알아본 것이 있으면 미리 켜져
                있고, 여기서 고친 결과가 사실로 남습니다.
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
