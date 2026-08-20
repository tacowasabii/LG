/**
 * 사진첩 그리드 — 촬영 연월로 나눈 정사각형 격자
 *
 * Masonry를 쓰지 않는다. 가족 사진은 세로·가로·정사각형이 뒤섞여 있어서 높이가
 * 제각각인 격자에서는 훑는 눈이 자꾸 걸린다. 훑는 것이 이 화면의 유일한 목적이다.
 *
 * 기본 상태에서 사진 위에 글자를 얹지 않는다. 얹는 것은 사진이 스스로 말하지
 * 못하는 것뿐이다 — 영상인지(재생 표시·길이), 가려진 기록인지(자물쇠), 아직
 * 어느 추억에도 안 붙었는지(미분류). 촬영일·추억·인물은 마우스를 올리거나
 * 키보드로 짚었을 때 나온다. 파일명은 그리드에 내지 않는다 (상세에 있다).
 *
 * 원본은 여기서 부르지 않는다. 썸네일이 없는 기록만 원본 경로를 쓰고, 그것도
 * loading="lazy"로 화면에 들어올 때 받는다.
 */

import { useMemo, useState } from 'react'
import { ImageOff, Lock, Play, RefreshCw } from 'lucide-react'
import { AlbumMediaItem, mediaUrl } from '../../lib/api'

/** 촬영일을 모르는 사진들이 모이는 칸 */
const UNDATED_KEY = '__undated__'
export const UNDATED_LABEL = '날짜를 알 수 없는 사진'

export interface AlbumSection {
  key: string
  label: string
  items: AlbumMediaItem[]
  /** 그 사진들이 전체 목록에서 몇 번째인지 (Lightbox가 이어서 넘길 수 있게) */
  offsets: number[]
}

/**
 * 서버가 준 순서를 그대로 두고 연월로만 나눈다.
 *
 * 정렬을 "최근 업로드순"으로 바꾸면 칸의 순서도 업로드 순서를 따라간다 —
 * 화면이 다시 줄을 세우면 서버가 자른 페이지 경계와 어긋난다. 촬영일을 모르는
 * 사진 칸만 언제나 맨 뒤로 보낸다.
 */
export function groupByMonth(items: AlbumMediaItem[]): AlbumSection[] {
  const sections = new Map<string, AlbumSection>()

  items.forEach((item, index) => {
    const key = item.has_exif && item.captured_at ? item.captured_at.slice(0, 7) : UNDATED_KEY
    let section = sections.get(key)
    if (!section) {
      section = { key, label: monthLabel(key), items: [], offsets: [] }
      sections.set(key, section)
    }
    section.items.push(item)
    section.offsets.push(index)
  })

  const ordered = [...sections.values()]
  const undated = ordered.filter((s) => s.key === UNDATED_KEY)
  return [...ordered.filter((s) => s.key !== UNDATED_KEY), ...undated]
}

function monthLabel(key: string): string {
  if (key === UNDATED_KEY) return UNDATED_LABEL
  const [year, month] = key.split('-')
  return `${year}년 ${Number(month)}월`
}

/** 초를 0:07 · 1:24 꼴로 */
export function formatDuration(seconds: number | null | undefined): string {
  if (!seconds || seconds <= 0) return ''
  const total = Math.round(seconds)
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`
}

interface AlbumGridProps {
  items: AlbumMediaItem[]
  /** 전체 목록에서의 순번으로 상세를 연다 */
  onOpen: (index: number) => void
}

export default function AlbumGrid({ items, onOpen }: AlbumGridProps) {
  const sections = useMemo(() => groupByMonth(items), [items])

  return (
    <div className="mt-10 flex flex-col gap-10">
      {sections.map((section) => (
        <section key={section.key}>
          <div
            className="flex items-baseline justify-between gap-4 pb-3"
            style={{ borderBottom: '1px solid var(--border)' }}
          >
            <h3 className="t-h3 m-0">{section.label}</h3>
            <span className="t-mono text-[11px] text-ink-300">{section.items.length}개</span>
          </div>

          <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4 2xl:grid-cols-5">
            {section.items.map((item, i) => (
              <AlbumTile
                key={item.id}
                item={item}
                onOpen={() => onOpen(section.offsets[i])}
              />
            ))}
          </div>
        </section>
      ))}
    </div>
  )
}

function AlbumTile({ item, onOpen }: { item: AlbumMediaItem; onOpen: () => void }) {
  // 썸네일을 못 불러왔을 때. 깨진 이미지 아이콘만 두면 사진이 사라진 것처럼
  // 보이므로, 무엇이었는지(파일명)와 다시 시도할 길을 함께 준다.
  const [failed, setFailed] = useState(false)
  const [attempt, setAttempt] = useState(0)

  const source = item.thumbnail_path || item.file_path
  const src = mediaUrl(source) + (attempt > 0 ? `?retry=${attempt}` : '')
  const duration = formatDuration(item.duration_sec)
  const restricted = item.visibility !== 'family'

  return (
    <div className="group relative aspect-square overflow-hidden rounded bg-ink-50">
      {/*
        타일 전체가 상세를 여는 버튼이다. 다시 불러오기 버튼을 이 안에 두면
        버튼 안의 버튼이 되므로, 형제로 놓고 위에 겹친다.
      */}
      <button
        onClick={onOpen}
        className="absolute inset-0 block h-full w-full cursor-pointer border-0 bg-transparent p-0"
        aria-label={`${item.original_filename} 크게 보기`}
      >
        {failed ? (
          <span className="flex h-full w-full flex-col items-center justify-center gap-1.5 px-3">
            <ImageOff size={20} strokeWidth={1.5} className="text-ink-300" />
            <span className="t-caption line-clamp-2 break-all text-center text-[11px]">
              {item.original_filename}
            </span>
          </span>
        ) : (
          <img
            src={src}
            alt=""
            loading="lazy"
            decoding="async"
            onError={() => setFailed(true)}
            className="h-full w-full object-cover transition-transform duration-[240ms] ease-out
                       group-hover:scale-[1.03]"
          />
        )}
      </button>

      {failed && (
        <button
          onClick={() => {
            setFailed(false)
            setAttempt((n) => n + 1)
          }}
          className="btn-quiet absolute bottom-2 left-1/2 flex -translate-x-1/2 items-center gap-1
                     bg-paper-pure text-[11px]"
        >
          <RefreshCw size={11} strokeWidth={2} />
          다시 불러오기
        </button>
      )}

      {/* 사진이 스스로 말하지 못하는 것만 얹는다 */}
      <span className="pointer-events-none absolute left-2 top-2 flex items-center gap-1">
        {restricted && (
          <span
            className="flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] text-white"
            style={{ background: 'rgba(14,13,11,0.62)' }}
            title={item.visibility === 'private' ? '비공개' : '부분 공개'}
          >
            <Lock size={10} strokeWidth={2.25} />
          </span>
        )}
        {!item.event && (
          <span
            className="rounded px-1.5 py-0.5 text-[10px] font-semibold"
            style={{ background: 'var(--warning-soft)', color: 'var(--warning-ink)' }}
          >
            미분류
          </span>
        )}
      </span>

      {item.media_type === 'video' && (
        <span
          className="pointer-events-none absolute bottom-2 right-2 flex items-center gap-1
                     rounded px-1.5 py-0.5 text-[10px] text-white"
          style={{ background: 'rgba(14,13,11,0.62)' }}
        >
          <Play size={10} strokeWidth={2.25} />
          {duration || '영상'}
        </span>
      )}

      {/* 마우스를 올리거나 키보드로 짚었을 때만 */}
      <span
        className="pointer-events-none absolute inset-x-0 bottom-0 flex flex-col gap-0.5 px-2.5
                   pb-2.5 pt-8 opacity-0 transition-opacity duration-150 ease-out
                   group-hover:opacity-100 group-focus-within:opacity-100"
        style={{
          background: 'linear-gradient(to top, rgba(14,13,11,0.78), rgba(14,13,11,0))',
        }}
      >
        <span className="t-mono text-[10px] text-white/80">
          {item.has_exif && item.captured_at ? item.captured_at.slice(0, 10) : '촬영일 미상'}
        </span>
        {item.event && (
          <span className="truncate text-[12px] font-semibold text-white">
            {item.event.title}
          </span>
        )}
        {item.people.length > 0 && (
          <span className="truncate text-[11px] text-white/80">
            {item.people.map((p) => p.name).join(' · ')}
          </span>
        )}
      </span>
    </div>
  )
}
