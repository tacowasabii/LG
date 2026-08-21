/**
 * 사진첩 (기획안 사진첩 04~07장)
 *
 * 여기는 사건도 이야기도 거치지 않고 사진 자체를 훑는 자리다. 홈은 추억 단위로
 * 보여 주고, 타임라인·지도는 언제·어디였는지를 보여 주고, Film·TV는 감상하게
 * 한다. "그 사진 어디 있었지"에 답하는 화면은 없었다.
 *
 * 올리는 기능을 다시 만들지 않는다. `사진 올리기`는 모으기(/collect)로 보낸다 —
 * 올리는 길이 두 개가 되면 초안·인물 지목 흐름도 두 개가 된다.
 *
 * 조건은 주소에 둔다. 사진 한 장을 찾아 가족에게 링크로 보낼 수 있어야 하고,
 * 새로고침·뒤로 가기로 조건이 사라지면 훑던 자리를 잃는다.
 *
 * 목록·정렬·필터는 서버가 한다 (backend/services/album.py). AI를 끼우지 않는다 —
 * 같은 조건에 다른 결과가 나오면 사진첩이 아니다.
 *
 * 묶어 보는 방식도 서버가 정한 순서를 따른다. 연월별과 사건별 두 가지고, 사건별은
 * 화면에서 나눌 수 없다 — 한 페이지 60장 안에서만 묶으면 같은 사건이 페이지마다
 * 토막난다. 그래서 group을 주소에 담아 서버에 넘긴다.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { CheckSquare, Images, Trash2, Upload, X } from 'lucide-react'
import {
  AlbumEventFacet,
  AlbumEventStatus,
  AlbumGroupBy,
  AlbumMediaItem,
  AlbumSort,
  bulkDeleteMedia,
  getAlbum,
  readDetail,
} from '../lib/api'
import { useCurrentUser } from '../lib/currentUser'
import { invalidateEvents, invalidateVoiceClips, useEvents } from '../lib/useGraphData'
import { Page, PageHeader } from '../components/Page'
import AlbumFilters, { AlbumFilterValue } from '../components/album/AlbumFilters'
import AlbumGrid from '../components/album/AlbumGrid'
import MediaLightbox from '../components/album/MediaLightbox'

const SORTS: AlbumSort[] = ['captured_desc', 'captured_asc', 'uploaded_desc']
const STATUSES: AlbumEventStatus[] = ['all', 'linked', 'unlinked']
const GROUPS: AlbumGroupBy[] = ['month', 'event']
const PAGE_SIZE = 60

/** 주소에 적힌 조건을 읽는다. 모르는 값은 기본값으로 되돌린다 */
function readFilters(params: URLSearchParams): AlbumFilterValue {
  const year = Number(params.get('year'))
  const sort = params.get('sort') as AlbumSort | null
  const status = params.get('event_status') as AlbumEventStatus | null
  const group = params.get('group') as AlbumGroupBy | null
  const type = params.get('type')

  return {
    type: type === 'photo' || type === 'video' ? type : 'all',
    year: Number.isFinite(year) && year > 0 ? year : null,
    personId: params.get('person_id') || null,
    eventId: params.get('event_id') || null,
    eventStatus: status && STATUSES.includes(status) ? status : 'all',
    sort: sort && SORTS.includes(sort) ? sort : 'captured_desc',
    groupBy: group && GROUPS.includes(group) ? group : 'month',
    q: params.get('q') || '',
  }
}

export default function AlbumPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const { members } = useCurrentUser()
  const { events } = useEvents()

  const filters = useMemo(() => readFilters(searchParams), [searchParams])

  const [items, setItems] = useState<AlbumMediaItem[]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [total, setTotal] = useState(0)
  const [years, setYears] = useState<number[]>([])
  /* 고를 수 있는 사건과 개수. 서버가 준 것을 그대로 쓴다 (available_events) */
  const [eventFacets, setEventFacets] = useState<AlbumEventFacet[]>([])
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [openIndex, setOpenIndex] = useState<number | null>(null)
  /*
    바닥이 보이면 저절로 다음 페이지를 부르는데, 한 페이지가 새 사진을 하나도
    가져오지 않으면 그만둔다. 커서가 제자리를 맴돌 때 관찰자가 같은 요청을
    끝없이 되풀이하는 것을 막는다. "더 보기" 버튼은 그대로 남는다.
  */
  const [autoLoad, setAutoLoad] = useState(true)
  /* 방금 지운 원본. 사진이 조용히 없어지는 것보다 무엇이 없어졌는지가 낫다 */
  const [deleted, setDeleted] = useState<string | null>(null)
  /*
    여러 장 지우기.

    체크박스를 늘 깔아 두지 않고 "선택"으로 들어가는 모드로 둔다. 사진첩에서
    하는 일은 보는 것이고, 지울 것을 고르는 일은 그것과 섞이면 안 된다 —
    기획안도 삭제를 훑는 화면 전면에 두지 말라고 못 박았다.
  */
  const [selecting, setSelecting] = useState(false)
  const [selected, setSelected] = useState<string[]>([])
  const [confirming, setConfirming] = useState(false)
  const [bulkBusy, setBulkBusy] = useState(false)
  /* 지우지 못한 것과 그 이유 (남의 기록이 섞여 있었을 때) */
  const [failures, setFailures] = useState<Array<{ id: string; reason: string }>>([])

  // 입력 중인 검색어. 글자마다 서버를 부르지 않고 잠깐 멈춘 뒤 주소에 반영한다.
  const [draftQuery, setDraftQuery] = useState(filters.q)

  /*
    조건이 바뀌면 이전 요청의 응답을 버려야 한다. 칩을 빠르게 두 번 누르면
    먼저 보낸 요청이 나중에 도착해서, 화면에 보이는 조건과 사진이 어긋난다.
  */
  const requestId = useRef(0)

  // 서버에 보낼 모양. 문자열로 만들어 두면 effect가 이것만 보고 다시 돈다.
  const queryKey = useMemo(
    () =>
      JSON.stringify({
        types: filters.type === 'all' ? null : filters.type,
        year: filters.year,
        personId: filters.personId,
        eventId: filters.eventId,
        eventStatus: filters.eventStatus,
        sort: filters.sort,
        groupBy: filters.groupBy,
        q: filters.q,
      }),
    [filters],
  )

  useEffect(() => {
    const query = JSON.parse(queryKey)
    const id = ++requestId.current

    setLoading(true)
    setError(null)
    setOpenIndex(null)
    setAutoLoad(true)
    setDeleted(null)
    setSelecting(false)
    setSelected([])
    setConfirming(false)
    setFailures([])

    getAlbum({ ...query, limit: PAGE_SIZE })
      .then((page) => {
        if (id !== requestId.current) return
        setItems(page.items)
        setCursor(page.next_cursor ?? null)
        setTotal(page.total)
        setYears(page.available_years)
        setEventFacets(page.available_events ?? [])
      })
      .catch((e) => {
        if (id !== requestId.current) return
        console.error('[album] 사진첩을 불러오지 못했습니다', e)
        setError('사진첩을 불러오지 못했습니다. 잠시 뒤 다시 시도해 주세요.')
        setItems([])
        setTotal(0)
      })
      .finally(() => {
        if (id === requestId.current) setLoading(false)
      })
  }, [queryKey])

  const loadMore = useCallback(() => {
    if (!cursor || loadingMore || loading) return
    const id = requestId.current
    setLoadingMore(true)

    getAlbum({ ...JSON.parse(queryKey), cursor, limit: PAGE_SIZE })
      .then((page) => {
        // 그 사이에 조건이 바뀌었으면 이 페이지는 버린다
        if (id !== requestId.current) return
        setItems((prev) => {
          // 서버가 커서 뒤부터 주지만, 겹쳐 들어오면 같은 사진이 두 번 그려진다
          const seen = new Set(prev.map((i) => i.id))
          const fresh = page.items.filter((i) => !seen.has(i.id))
          if (fresh.length === 0) setAutoLoad(false)
          return [...prev, ...fresh]
        })
        setCursor(page.next_cursor ?? null)
        setTotal(page.total)
      })
      .catch((e) => {
        if (id !== requestId.current) return
        console.error('[album] 다음 페이지를 불러오지 못했습니다', e)
        setError('다음 페이지를 불러오지 못했습니다.')
      })
      .finally(() => {
        if (id === requestId.current) setLoadingMore(false)
      })
  }, [cursor, loading, loadingMore, queryKey])

  // 바닥이 보이면 다음 페이지를. 버튼도 함께 두어 관찰이 안 될 때도 넘길 수 있게 한다.
  const sentinel = useRef<HTMLDivElement | null>(null)
  useEffect(() => {
    const node = sentinel.current
    if (!node || !cursor || !autoLoad) return

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) loadMore()
      },
      { rootMargin: '400px' },
    )
    observer.observe(node)
    return () => observer.disconnect()
  }, [cursor, loadMore, autoLoad])

  /*
    조건 하나를 바꿔 주소를 다시 쓴다. 지금 주소를 인자로 받아 고치는 이유는
    검색어 대기 때문이다 — 타이핑을 기다리는 동안 사용자가 연도 칩을 누르면,
    화면이 기억해 둔 옛 조건으로 덮어써서 방금 누른 연도가 사라진다.
  */
  const patchFilters = useCallback(
    (patch: Partial<AlbumFilterValue>) => {
      setSearchParams((prev) => {
        const next = { ...readFilters(prev), ...patch }
        const params = new URLSearchParams()
        if (next.type !== 'all') params.set('type', next.type)
        if (next.year != null) params.set('year', String(next.year))
        if (next.personId) params.set('person_id', next.personId)
        if (next.eventId) params.set('event_id', next.eventId)
        if (next.eventStatus !== 'all') params.set('event_status', next.eventStatus)
        if (next.sort !== 'captured_desc') params.set('sort', next.sort)
        if (next.groupBy !== 'month') params.set('group', next.groupBy)
        if (next.q.trim()) params.set('q', next.q.trim())
        return params
      })
      // 기록을 남긴다 (replace를 쓰지 않는다) — 뒤로 가기로 직전 조건으로 돌아간다
    },
    [setSearchParams],
  )

  // 검색어는 잠깐 멈춘 뒤 주소에 넣는다 (글자마다 서버를 부르지 않는다)
  useEffect(() => {
    if (draftQuery.trim() === filters.q) return
    const timer = window.setTimeout(() => patchFilters({ q: draftQuery }), 350)
    return () => window.clearTimeout(timer)
  }, [draftQuery, filters.q, patchFilters])

  /*
    주소가 밖에서 바뀌었을 때(뒤로 가기·링크) 입력칸도 따라간다. 방금 내가 쓴
    글자가 주소에 반영된 경우는 건드리지 않는다 — 다듬은 값으로 되돌려 놓으면
    타이핑 중에 입력칸이 사용자와 싸운다 (끝의 공백이 사라진다).
  */
  useEffect(() => {
    setDraftQuery((prev) => (prev.trim() === filters.q ? prev : filters.q))
  }, [filters.q])

  /*
    조건만 지운다. 묶어 보는 방식은 필터가 아니라 보는 방식이므로 남긴다 —
    사건별로 훑던 사람이 조건을 지웠다고 연월별로 튕겨 나가지 않는다.
  */
  const resetFilters = () => {
    setDraftQuery('')
    setSearchParams((prev) => {
      const params = new URLSearchParams()
      const group = readFilters(prev).groupBy
      if (group !== 'month') params.set('group', group)
      return params
    })
  }

  const filtersActive =
    filters.type !== 'all' ||
    filters.year != null ||
    Boolean(filters.personId) ||
    Boolean(filters.eventId) ||
    filters.eventStatus !== 'all' ||
    Boolean(filters.q)

  const updateItem = useCallback((id: string, patch: Partial<AlbumMediaItem>) => {
    setItems((prev) => prev.map((item) => (item.id === id ? { ...item, ...patch } : item)))
  }, [])

  /**
   * 지운 사진을 목록에서 뺀다.
   *
   * 목록을 처음부터 다시 받지 않는다. 사진첩은 아래로 계속 받아 가는 화면이라
   * 다시 받으면 스크롤과 함께 훑던 자리를 잃는다. 그래서 지운 한 장만 빼고
   * 개수를 하나 줄인다.
   *
   * 연도 목록은 서버가 준 그대로 둔다. 그 연도의 마지막 사진을 지웠을 때만
   * 칩이 잠깐 남고, 다음 조회에서 사라진다 — 눌러도 "이 조건에 맞는 사진이
   * 없습니다"가 되므로 잘못된 화면으로 이어지지는 않는다.
   *
   * 보고 있던 사진이 사라졌으므로 상세를 다음 사진으로 옮긴다. 마지막 한 장을
   * 지웠으면 닫는다.
   */
  const removeItem = useCallback(
    (id: string) => {
      const gone = items.find((item) => item.id === id)
      const remaining = items.filter((item) => item.id !== id)

      setItems(remaining)
      setTotal((prev) => Math.max(0, prev - 1))
      setOpenIndex((prev) =>
        prev == null ? prev : remaining.length === 0 ? null : Math.min(prev, remaining.length - 1),
      )
      setDeleted(`${gone?.original_filename || id} 원본`)
    },
    [items],
  )

  // --- 여러 장 고르기 ---

  const selectedSet = useMemo(() => new Set(selected), [selected])
  const selectedItems = useMemo(
    () => items.filter((item) => selectedSet.has(item.id)),
    [items, selectedSet],
  )

  const toggleSelect = useCallback((id: string) => {
    setSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))
  }, [])

  const exitSelecting = () => {
    setSelecting(false)
    setSelected([])
    setConfirming(false)
    setFailures([])
  }

  /*
    묻는 창은 Esc로 닫힌다. 상세에서 한 장 지울 때도 Esc가 취소이므로 같게 둔다.
    지우는 중에는 닫지 않는다 — 요청은 이미 갔고, 창만 사라지면 무슨 일이
    일어났는지 알 수 없게 된다.
  */
  useEffect(() => {
    if (!confirming) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !bulkBusy) setConfirming(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [confirming, bulkBusy])

  /**
   * 고른 사진들을 지운다.
   *
   * 요청은 한 번이다 (POST /api/media/bulk-delete). 남의 기록이 섞여 있으면
   * 그것만 남고 이유가 함께 온다 — 하나 때문에 전부 되돌리지 않는다.
   *
   * 지우지 못한 것은 고른 상태로 남긴다. 무엇이 남았는지 눈으로 보이는 편이
   * "몇 개 실패"라는 문장보다 낫다.
   */
  const deleteSelected = async () => {
    setBulkBusy(true)
    setError(null)
    try {
      const result = await bulkDeleteMedia(selected)
      // 홈·지도·TV의 개수와 썸네일에서도 즉시 빠져야 한다
      invalidateEvents()
      invalidateVoiceClips()

      const removed = new Set(result.deleted)
      setItems((prev) => prev.filter((item) => !removed.has(item.id)))
      setTotal((prev) => Math.max(0, prev - result.deleted.length))
      setOpenIndex(null)
      setConfirming(false)
      setFailures(result.failed)
      setSelected(result.failed.map((f) => f.id))
      setDeleted(result.deleted.length > 0 ? `사진 ${result.deleted.length}장` : null)
      if (result.failed.length === 0) setSelecting(false)
    } catch (e) {
      console.error('[album] 고른 사진을 지우지 못했습니다', e)
      setError(readDetail(e, '고른 사진을 지우지 못했습니다.'))
      setConfirming(false)
    } finally {
      setBulkBusy(false)
    }
  }

  return (
    <Page width={1160}>
      <PageHeader
        eyebrow="Photo Album"
        title="사진첩"
        lead="가족이 모은 사진과 영상을 촬영 순서대로 한곳에서 봅니다."
        action={
          <div className="flex items-center gap-4">
            <span className="t-mono text-[12px] text-ink-300">
              {loading ? '불러오는 중…' : `사진 · 영상 ${total}개`}
            </span>
            {/*
              고르는 모드로 들어가는 문. 지우는 일은 여기를 지나야 한다 —
              훑어보는 화면에 체크박스를 늘 깔아 두지 않는다.
            */}
            {items.length > 0 && (
              <button
                onClick={() => (selecting ? exitSelecting() : setSelecting(true))}
                className={`tab tab-sm flex items-center gap-1.5 ${selecting ? 'tab-on' : ''}`}
                aria-pressed={selecting}
              >
                {selecting ? <X size={13} strokeWidth={2} /> : <CheckSquare size={13} strokeWidth={2} />}
                {selecting ? '선택 마침' : '선택'}
              </button>
            )}
            {/* 올리는 길은 하나다 — 모으기로 보낸다 */}
            <Link to="/collect" className="btn-primary no-underline hover:no-underline">
              <span className="flex items-center gap-2">
                <Upload size={15} strokeWidth={2} />
                사진 올리기
              </span>
            </Link>
          </div>
        }
      />

      <AlbumFilters
        value={filters}
        years={years}
        events={eventFacets}
        members={members}
        draftQuery={draftQuery}
        onDraftQuery={setDraftQuery}
        onChange={patchFilters}
        onReset={resetFilters}
        active={filtersActive}
      />

      {deleted && (
        <p className="t-body-sm mt-8 flex flex-wrap items-center gap-2">
          <span style={{ color: 'var(--critical-ink)' }}>{deleted}을 지웠습니다.</span>
          <span className="t-caption">
            가족이 남긴 기억 문장은 그대로 있습니다 — 원본과의 연결만 끊겼습니다.
          </span>
        </p>
      )}

      {/*
        지우지 못한 것은 개수로 뭉개지 않는다. 어느 사진이 왜 남았는지를 그대로
        적는다 — 대개 남이 올린 사진이고, 그건 사용자가 할 수 있는 일이 없다는
        뜻이므로 알려주지 않으면 계속 다시 시도한다.
      */}
      {failures.length > 0 && (
        <div className="mt-4 rounded-lg p-4" style={{ background: 'var(--critical-soft)' }}>
          <p className="t-body-sm m-0" style={{ color: 'var(--critical-ink)' }}>
            {failures.length}장은 지우지 못했습니다.
          </p>
          {failures.map((failure) => {
            const name =
              items.find((item) => item.id === failure.id)?.original_filename || failure.id
            return (
              <p
                key={failure.id}
                className="t-caption m-0 mt-1.5"
                style={{ color: 'var(--critical-ink)', opacity: 0.8 }}
              >
                {name} — {failure.reason}
              </p>
            )
          })}
        </div>
      )}

      {error && (
        <p className="mt-8 text-[13px]" style={{ color: 'var(--critical-ink)' }}>
          {error}
        </p>
      )}

      {loading ? (
        <p className="t-body-sm py-20 text-center text-ink-300">불러오는 중…</p>
      ) : items.length === 0 ? (
        // 못 불러온 것과 없는 것은 다르다. 실패했을 때 "사진이 없습니다"라고
        // 하면 기록이 사라진 것으로 읽힌다 — 그때는 위의 안내문만 남긴다.
        error ? null : (
          <EmptyState filtersActive={filtersActive} onReset={resetFilters} />
        )
      ) : (
        <>
          <AlbumGrid
            items={items}
            onOpen={setOpenIndex}
            groupBy={filters.groupBy}
            /*
              사건 묶음 머리의 "이 추억만". 이미 그 추억만 보고 있으면 주지
              않는다 — 눌러도 화면이 그대로여서 눌린 것인지 알 수 없다.
            */
            onPickEvent={
              filters.eventId ? undefined : (eventId) => patchFilters({ eventId })
            }
            selecting={selecting}
            selectedIds={selectedSet}
            onToggleSelect={toggleSelect}
          />

          {/*
            고르는 동안 화면 아래에 붙어 따라온다. 사진을 고르려면 아래로 계속
            훑어야 하는데, 지우는 단추가 맨 위에만 있으면 고를 때마다 올라가야 한다.
          */}
          {selecting && (
            <div className="sticky bottom-4 z-30 mt-10">
              <div
                className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-lg px-5 py-3.5"
                style={{
                  background: 'var(--paper-pure)',
                  border: '1px solid var(--border-strong)',
                  boxShadow: 'var(--shadow-lg)',
                }}
              >
                <span className="text-[13px] font-semibold text-ink-900">
                  {selected.length}장 선택
                </span>

                <button
                  onClick={() =>
                    setSelected(
                      selected.length === items.length ? [] : items.map((item) => item.id),
                    )
                  }
                  className="btn-link"
                >
                  {selected.length === items.length
                    ? '선택 해제'
                    : `보이는 사진 모두 (${items.length}장)`}
                </button>

                {/*
                  "모두"는 지금 받아 온 것까지다. 조건에 맞는 전체가 더 있으면
                  그걸 밝힌다 — 전체를 골랐다고 착각한 채 지우게 하지 않는다.
                */}
                {items.length < total && (
                  <span className="t-caption">
                    조건에 맞는 {total}장 중 {items.length}장을 받아 왔습니다
                  </span>
                )}

                <button
                  onClick={() => setConfirming(true)}
                  disabled={selected.length === 0}
                  className="ml-auto flex cursor-pointer items-center gap-1.5 rounded border-0
                             px-3.5 py-2 text-[13px] disabled:opacity-40"
                  style={{ background: 'var(--critical-ink)', color: 'var(--paper)' }}
                >
                  <Trash2 size={13} strokeWidth={2} />
                  선택한 사진 지우기
                </button>
                <button onClick={exitSelecting} className="btn-quiet">
                  취소
                </button>
              </div>
            </div>
          )}

          <div ref={sentinel} className="pt-10 text-center">
            {cursor ? (
              <button onClick={loadMore} disabled={loadingMore} className="btn-quiet">
                {loadingMore ? '불러오는 중…' : `더 보기 (${total - items.length}개 남음)`}
              </button>
            ) : (
              <p className="t-caption m-0">사진 {items.length}개를 모두 보았습니다.</p>
            )}
          </div>
        </>
      )}

      {/*
        되돌릴 수 없는 일이므로 한 번 더 묻는다. 한 장 삭제는 상세에서 삭제
        영향까지 보여주는데, 여러 장은 그 미리보기를 장마다 부르면 요청이 그만큼
        늘어난다. 그래서 이미 받아 둔 것으로 셀 수 있는 것만 셈해 보여준다 —
        몇 장이고, 그중 몇 장이 추억에 붙어 있는지.
      */}
      {confirming && (
        <div
          className="fixed inset-0 z-[60] flex items-center justify-center p-8"
          style={{ background: 'rgba(14,13,11,0.5)' }}
          onClick={() => (bulkBusy ? null : setConfirming(false))}
        >
          <div
            className="w-[420px] rounded-lg bg-paper-pure p-7"
            style={{ boxShadow: 'var(--shadow-lg)' }}
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-label="고른 사진 지우기"
          >
            <p className="t-eyebrow m-0" style={{ color: 'var(--critical-ink)' }}>
              되돌릴 수 없습니다
            </p>
            <h3 className="t-h3 m-0 mt-2">사진 {selected.length}장을 지웁니다</h3>

            <div className="mt-4 rounded p-4" style={{ background: 'var(--critical-soft)' }}>
              {[
                { label: '사진', value: selectedItems.filter((i) => i.media_type === 'photo').length },
                { label: '영상', value: selectedItems.filter((i) => i.media_type === 'video').length },
                { label: '추억에 연결된 것', value: selectedItems.filter((i) => i.event).length },
              ]
                .filter((row) => row.value > 0)
                .map((row) => (
                  <div
                    key={row.label}
                    className="flex justify-between gap-4 py-[6px]"
                    style={{ borderBottom: '1px solid rgba(194,84,42,0.18)' }}
                  >
                    <span className="t-body-sm" style={{ color: 'var(--critical-ink)' }}>
                      {row.label}
                    </span>
                    <span
                      className="t-mono text-[12px]"
                      style={{ color: 'var(--critical-ink)' }}
                    >
                      {row.value}개
                    </span>
                  </div>
                ))}
              <p className="t-caption m-0 mt-3" style={{ color: 'var(--critical-ink)' }}>
                가족이 남긴 기억 문장은 지워지지 않습니다. 원본과의 연결만 끊깁니다.
              </p>
            </div>

            <p className="t-caption mt-3">
              남이 올린 사진이 섞여 있으면 그 사진은 지워지지 않고 이유를 알려드립니다.
            </p>

            <div className="mt-5 flex items-center gap-3">
              <button
                onClick={deleteSelected}
                disabled={bulkBusy}
                className="cursor-pointer rounded border-0 px-4 py-2 text-[13px] disabled:opacity-40"
                style={{ background: 'var(--critical-ink)', color: 'var(--paper)' }}
              >
                {bulkBusy ? '지우는 중…' : `정말 ${selected.length}장을 지웁니다`}
              </button>
              <button
                onClick={() => setConfirming(false)}
                disabled={bulkBusy}
                className="btn-quiet"
              >
                취소
              </button>
            </div>
          </div>
        </div>
      )}

      {openIndex != null && (
        <MediaLightbox
          items={items}
          index={openIndex}
          total={total}
          members={members}
          events={events}
          onIndexChange={setOpenIndex}
          onClose={() => setOpenIndex(null)}
          onNeedMore={loadMore}
          onItemUpdate={updateItem}
          onItemDelete={removeItem}
        />
      )}
    </Page>
  )
}

function EmptyState({
  filtersActive,
  onReset,
}: {
  filtersActive: boolean
  onReset: () => void
}) {
  if (filtersActive) {
    return (
      <div className="py-20 text-center">
        <p className="t-body m-0">이 조건에 맞는 사진이 없습니다.</p>
        <button onClick={onReset} className="btn-outline mt-5">
          필터 초기화
        </button>
      </div>
    )
  }

  return (
    <div className="py-20 text-center">
      <Images size={28} strokeWidth={1.5} className="mx-auto text-ink-200" />
      <p className="t-body mx-auto mt-4 max-w-[33em]">
        아직 가족사진이 없습니다. 첫 사진을 올리면 촬영 시점과 장소를 읽어 사진첩에
        정리합니다.
      </p>
      <Link to="/collect" className="btn-primary mt-5 inline-block no-underline hover:no-underline">
        첫 사진 올리기
      </Link>
    </div>
  )
}
