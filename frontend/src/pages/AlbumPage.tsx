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
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Images, Upload } from 'lucide-react'
import {
  AlbumEventStatus,
  AlbumMediaItem,
  AlbumSort,
  getAlbum,
} from '../lib/api'
import { useCurrentUser } from '../lib/currentUser'
import { useEvents } from '../lib/useGraphData'
import { Page, PageHeader } from '../components/Page'
import AlbumFilters, { AlbumFilterValue } from '../components/album/AlbumFilters'
import AlbumGrid from '../components/album/AlbumGrid'
import MediaLightbox from '../components/album/MediaLightbox'

const SORTS: AlbumSort[] = ['captured_desc', 'captured_asc', 'uploaded_desc']
const STATUSES: AlbumEventStatus[] = ['all', 'linked', 'unlinked']
const PAGE_SIZE = 60

/** 주소에 적힌 조건을 읽는다. 모르는 값은 기본값으로 되돌린다 */
function readFilters(params: URLSearchParams): AlbumFilterValue {
  const year = Number(params.get('year'))
  const sort = params.get('sort') as AlbumSort | null
  const status = params.get('event_status') as AlbumEventStatus | null
  const type = params.get('type')

  return {
    type: type === 'photo' || type === 'video' ? type : 'all',
    year: Number.isFinite(year) && year > 0 ? year : null,
    personId: params.get('person_id') || null,
    eventStatus: status && STATUSES.includes(status) ? status : 'all',
    sort: sort && SORTS.includes(sort) ? sort : 'captured_desc',
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
        eventStatus: filters.eventStatus,
        sort: filters.sort,
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

    getAlbum({ ...query, limit: PAGE_SIZE })
      .then((page) => {
        if (id !== requestId.current) return
        setItems(page.items)
        setCursor(page.next_cursor ?? null)
        setTotal(page.total)
        setYears(page.available_years)
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
        if (next.eventStatus !== 'all') params.set('event_status', next.eventStatus)
        if (next.sort !== 'captured_desc') params.set('sort', next.sort)
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

  const resetFilters = () => {
    setDraftQuery('')
    setSearchParams(new URLSearchParams())
  }

  const filtersActive =
    filters.type !== 'all' ||
    filters.year != null ||
    Boolean(filters.personId) ||
    filters.eventStatus !== 'all' ||
    Boolean(filters.q)

  const updateItem = useCallback((id: string, patch: Partial<AlbumMediaItem>) => {
    setItems((prev) => prev.map((item) => (item.id === id ? { ...item, ...patch } : item)))
  }, [])

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
        members={members}
        draftQuery={draftQuery}
        onDraftQuery={setDraftQuery}
        onChange={patchFilters}
        onReset={resetFilters}
        active={filtersActive}
      />

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
          <AlbumGrid items={items} onOpen={setOpenIndex} />

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
      <p className="t-body mx-auto mt-4 max-w-[44ch]">
        아직 가족사진이 없습니다. 첫 사진을 올리면 촬영 시점과 장소를 읽어 사진첩에
        정리합니다.
      </p>
      <Link to="/collect" className="btn-primary mt-5 inline-block no-underline hover:no-underline">
        첫 사진 올리기
      </Link>
    </div>
  )
}
