/**
 * 연결된 기억 (Memory Graph)
 *
 * 이 화면은 한동안 사이드바에서 빠져 있었다. 문제는 그래프라는 발상이 아니라
 * 화면이 실제로 내놓던 것이었다 — 노드 78개를 한꺼번에 뿌리면 수가 가장 많은
 * 사진과 기억 문장이 회색 점으로 절반을 덮고, 이름은 확대해야 나타났다. 가족이
 * 자기 얼굴도 찾을 수 없는 그림이었다.
 *
 * 다시 세우면서 네 가지를 바꿨다.
 *
 *   기본을 줄였다        인물·추억·장소만 켜고 시작한다 (78개 중 21개). 사진과
 *                        기억은 필터에서 켤 수 있고, 몇 개를 접어 두었는지 밝힌다.
 *   얼굴과 이름을 그렸다  인물은 프로필 사진을 원형으로 그린다. 이름은 확대와
 *                        무관하게 항상 붙는다.
 *   고른 것만 밝힌다      고른 점과 거기 걸린 것만 남기고 나머지를 옅게 눌러,
 *                        선 239개 중 지금 읽어야 할 선이 무엇인지 보이게 한다.
 *   낱말로 설명한다       오른쪽 칸은 관계를 이름으로 적는다 — participated_in이
 *                        아니라 "함께한 추억". 그 목록을 누르면 다음 점으로
 *                        건너가므로, 캔버스를 누르기 어려운 사람도 같은 길을 쓴다.
 *
 * 데이터는 GET /api/graph 하나다 (backend/routers/graph.py).
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import ForceGraph2D from 'react-force-graph-2d'
import { Maximize2, Minus, Plus, Search, X } from 'lucide-react'
import { GraphData, GraphEdge, GraphNode, getGraph, mediaUrl } from '../lib/api'
import { STATE_CONFIG } from '../components/StatusPill'
import { Page, PageHeader } from '../components/Page'
import { useEvents } from '../lib/useGraphData'
import { useCurrentUser } from '../lib/currentUser'
import { usePrefersReducedMotion } from '../lib/reducedMotion'

const TAU = Math.PI * 2

interface TypeConfig {
  type: string
  /** 앱 전체와 같은 낱말을 쓴다 — event는 "추억", memory는 "기억"이다 */
  label: string
  color: string
  /** 그래프 좌표에서의 반지름 */
  size: number
  /** 처음부터 켜 둘지 */
  on: boolean
}

/**
 * 색은 종류를 가르는 것이 전부이므로 계조 안에서 고른다. 인물은 잉크, 추억은
 * 강조색, 장소·기억은 상태색을 빌려 쓰고, 사진은 가장 옅은 회색에 둔다.
 *
 * 사진과 기억을 꺼 두고 시작하는 것은 수 때문이다 — 둘이 노드의 4분의 3이고,
 * 점만으로는 읽을 내용이 없다. 사진은 사진첩이, 기억은 추억 상세가 이미 제대로
 * 보여 준다. 여기서는 뼈대(누가 · 무엇을 · 어디서)가 먼저다.
 */
const NODE_TYPES: TypeConfig[] = [
  { type: 'person', label: '인물', color: '#1F1D1A', size: 10, on: true },
  { type: 'event', label: '추억', color: '#8A1538', size: 8, on: true },
  { type: 'place', label: '장소', color: '#17766B', size: 6, on: true },
  { type: 'memory', label: '기억', color: '#7C5CB0', size: 5, on: false },
  { type: 'media', label: '사진 · 영상', color: '#C9C6BC', size: 4, on: false },
]

const TYPE: Record<string, TypeConfig> = Object.fromEntries(
  NODE_TYPES.map((t) => [t.type, t]),
)

const UNKNOWN_TYPE: TypeConfig = {
  type: '',
  label: '그 외',
  color: '#9C988C',
  size: 5,
  on: true,
}

const DEFAULT_TYPES = NODE_TYPES.filter((t) => t.on).map((t) => t.type)

/**
 * 연결은 고른 것의 입장에서 읽는다. 같은 선도 어느 쪽에서 보느냐에 따라 말이
 * 달라진다 — participated_in은 사람 쪽에서 "함께한 추억"이고 추억 쪽에서
 * "함께한 사람"이다. out은 고른 것이 화살의 출발점일 때, in은 도착점일 때다
 * (방향은 backend/models/graph_models.py RelationType에 적힌 그대로다).
 */
const RELATION_LABELS: Record<string, { out: string; in: string }> = {
  related_to: { out: '가족', in: '가족' },
  participated_in: { out: '함께한 추억', in: '함께한 사람' },
  located_at: { out: '있었던 곳', in: '여기서 생긴 추억' },
  captured_during: { out: '그날의 추억', in: '그날 남은 사진 · 영상' },
  taken_at: { out: '찍힌 곳', in: '여기서 찍은 사진 · 영상' },
  depicts: { out: '사진에 찍힌 사람', in: '이 사람이 찍힌 사진' },
  narrated_by: { out: '말하는 사람', in: '이 사람의 목소리' },
  remembers: { out: '남긴 기억', in: '기억을 남긴 사람' },
  about: { out: '어떤 추억의 기억인가', in: '가족이 남긴 기억' },
  evidenced_by: { out: '근거가 된 기록', in: '이 기록에서 나온 기억' },
}

/**
 * 오른쪽 칸에서 연결 묶음을 세우는 순서. 사람과 추억이 먼저 읽히고 사진이
 * 마지막이다. 이름이 같아지는 묶음(가족의 out·in)은 하나로 합친다.
 */
const GROUP_ORDER: Array<[string, 'out' | 'in']> = [
  ['related_to', 'out'],
  ['related_to', 'in'],
  ['participated_in', 'out'],
  ['participated_in', 'in'],
  ['located_at', 'out'],
  ['located_at', 'in'],
  ['about', 'out'],
  ['about', 'in'],
  ['remembers', 'out'],
  ['remembers', 'in'],
  ['captured_during', 'out'],
  ['captured_during', 'in'],
  ['depicts', 'out'],
  ['depicts', 'in'],
  ['narrated_by', 'out'],
  ['narrated_by', 'in'],
  ['taken_at', 'out'],
  ['taken_at', 'in'],
  ['evidenced_by', 'out'],
  ['evidenced_by', 'in'],
]

const LINK_CONFIRMED = '#B8B4A9'
const LINK_INFERRED = '#D5D2C8'
/** 고르지 않은 선. 지우지 않고 눌러 둔다 — 전체 모양은 남아 있어야 한다 */
const LINK_DIM = '#EFEDE7'
const LINK_ON = 'rgba(138, 21, 56, 0.5)'

/** 점 옆에 적을 이름 */
function nodeTitle(node: GraphNode): string {
  if (node.name) return node.name
  if (node.title) return node.title
  if (node.content) {
    return node.content.length > 22 ? `${node.content.slice(0, 22)}…` : node.content
  }
  return node.original_filename || node.id
}

function nodeDate(node: GraphNode): string {
  return node.date_start || node.exif_date?.slice(0, 10) || ''
}

/**
 * force-graph는 넘긴 선의 source·target을 노드 객체로 바꿔 놓는다. 문자열일
 * 때와 객체일 때가 섞이므로 id를 꺼내는 자리를 하나로 둔다.
 */
function endId(end: unknown): string {
  if (typeof end === 'string') return end
  return String((end as { id?: string } | null)?.id ?? '')
}

interface Connection {
  edge: GraphEdge
  otherId: string
  /** 고른 것이 출발점(out)인지 도착점(in)인지 */
  dir: 'out' | 'in'
}

interface Group {
  label: string
  items: Array<{ node: GraphNode; note: string }>
}

/** 한 묶음에 늘어놓는 최대 개수 (사진은 썸네일이라 더 많이 들어간다) */
const GROUP_LIMIT = 12
const GROUP_LIMIT_MEDIA = 9

export default function GraphPage() {
  // 추억 노드에 기억이 쌓인 정도를 붙이기 위해 사건 요약을 함께 받는다
  const { eventById } = useEvents()
  const { current } = useCurrentUser()
  const reduced = usePrefersReducedMotion()

  const [graph, setGraph] = useState<GraphData | null>(null)
  const [loading, setLoading] = useState(true)
  const [failed, setFailed] = useState(false)
  const [visibleTypes, setVisibleTypes] = useState<string[]>(DEFAULT_TYPES)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [hoverId, setHoverId] = useState<string | null>(null)
  const [query, setQuery] = useState('')

  const graphRef = useRef<any>(null)

  /*
   * ForceGraph2D는 크기를 주지 않으면 창 크기를 그대로 쓴다. 그래프가 화면의
   * 한 칸을 차지하는 배치에서는 캔버스가 칸을 넘겨 잘리므로, 칸의 실제 폭을
   * 재서 넘긴다. 높이는 디자인의 4:3 비율을 따르되 너무 납작해지지 않게 한다.
   */
  const boxRef = useRef<HTMLDivElement>(null)
  const [box, setBox] = useState({ w: 0, h: 0 })

  useEffect(() => {
    const el = boxRef.current
    if (!el) return
    const observer = new ResizeObserver(([entry]) => {
      const w = Math.round(entry.contentRect.width)
      setBox({ w, h: Math.max(420, Math.round((w * 540) / 720)) })
    })
    observer.observe(el)
    return () => observer.disconnect()
  }, [loading])

  useEffect(() => {
    getGraph()
      .then(setGraph)
      .catch((e) => {
        console.error('[graph] 불러오지 못했습니다', e)
        setFailed(true)
      })
      .finally(() => setLoading(false))
  }, [])

  /*
   * 프로필 사진은 캔버스가 그린다. canvas는 이미 받은 이미지만 그릴 수 있고
   * 받는 것은 비동기이므로, 도착한 뒤 한 번 다시 칠하게 상태를 하나 올린다
   * (그리는 함수가 바뀌면 force-graph가 캔버스를 다시 칠한다).
   */
  const avatars = useRef<Map<string, HTMLImageElement>>(new Map())
  const [avatarTick, setAvatarTick] = useState(0)

  useEffect(() => {
    if (!graph) return
    for (const node of graph.nodes) {
      if (node.node_type !== 'person' || !node.thumbnail_url) continue
      if (avatars.current.has(node.id)) continue
      const img = new Image()
      img.onload = () => setAvatarTick((t) => t + 1)
      img.src = mediaUrl(node.thumbnail_url)
      avatars.current.set(node.id, img)
    }
  }, [graph])

  const nodeById = useMemo(() => {
    const map = new Map<string, GraphNode>()
    for (const node of graph?.nodes ?? []) map.set(node.id, node)
    return map
  }, [graph])

  const counts = useMemo(() => {
    const map: Record<string, number> = {}
    for (const node of graph?.nodes ?? []) {
      map[node.node_type] = (map[node.node_type] ?? 0) + 1
    }
    return map
  }, [graph])

  /** 어느 점에 무엇이 걸려 있는지. 화면에서 끈 종류까지 모두 담는다 */
  const connectionsById = useMemo(() => {
    const map = new Map<string, Connection[]>()
    const push = (id: string, conn: Connection) => {
      const list = map.get(id)
      if (list) list.push(conn)
      else map.set(id, [conn])
    }
    for (const edge of graph?.edges ?? []) {
      push(edge.source, { edge, otherId: edge.target, dir: 'out' })
      push(edge.target, { edge, otherId: edge.source, dir: 'in' })
    }
    return map
  }, [graph])

  /*
   * force-graph가 쓰는 점 객체를 그대로 들고 있는다. 이 라이브러리는 넘긴 객체에
   * 좌표를 직접 써 넣으므로, 필터를 켤 때마다 새 객체를 만들면 이미 자리를 잡은
   * 점들까지 무작위 위치에서 다시 출발한다 — 사진을 켜는 순간 화면 전체가
   * 흔들리고, 방금 보던 사람이 어디로 갔는지 알 수 없다.
   */
  const nodeObjects = useRef<{ src: GraphData | null; map: Map<string, any> }>({
    src: null,
    map: new Map(),
  })

  /*
   * 캔버스에 넘기는 데이터. 원본과 visibleTypes 말고는 아무것에도 매지 않는다 —
   * 고르거나 스칠 때마다 다시 만들면 그때마다 배치가 다시 계산된다.
   */
  const forceData = useMemo(() => {
    if (!graph) return { nodes: [] as any[], links: [] as any[] }
    if (nodeObjects.current.src !== graph) {
      nodeObjects.current = { src: graph, map: new Map() }
    }
    const kept = nodeObjects.current.map
    const shown = new Set(
      graph.nodes.filter((n) => visibleTypes.includes(n.node_type)).map((n) => n.id),
    )
    const inferred = (id: string) => nodeById.get(id)?.confidence === 'ai_inferred'
    return {
      nodes: graph.nodes
        .filter((n) => shown.has(n.id))
        .map((n) => {
          const existing = kept.get(n.id)
          if (existing) return existing
          const made = { ...n, label: nodeTitle(n) }
          kept.set(n.id, made)
          return made
        }),
      links: graph.edges
        .filter((e) => shown.has(e.source) && shown.has(e.target))
        .map((e) => ({
          source: e.source,
          target: e.target,
          relation: e.relation,
          // 엣지 자체에 신뢰도 필드가 생기기 전까지는 양 끝 점의 confidence로
          // 대신 표시한다 (기획안은 모든 관계에 근거와 신뢰도를 붙인다고 했다)
          inferred: inferred(e.source) || inferred(e.target),
        })),
    }
  }, [graph, visibleTypes, nodeById])

  const hiddenCount = (graph?.nodes.length ?? 0) - forceData.nodes.length

  /** 고른 것이 없으면 스친 것을 쓴다. 둘 다 없으면 아무것도 누르지 않는다 */
  const focusId = hoverId ?? selectedId

  const focusSet = useMemo(() => {
    if (!focusId) return null
    const set = new Set<string>([focusId])
    for (const conn of connectionsById.get(focusId) ?? []) set.add(conn.otherId)
    return set
  }, [focusId, connectionsById])

  const fitAll = useCallback(() => {
    graphRef.current?.zoomToFit(reduced ? 0 : 400, 48)
  }, [reduced])

  /*
   * 배치가 멈출 때 전체를 화면에 맞추는 것은 데이터가 바뀐 다음 한 번뿐이다.
   * 점을 끌어 옮기면 force-graph가 배치를 다시 데우고, 멈출 때 또 맞추면 방금
   * 확대해 둔 자리가 매번 풀려 버린다.
   */
  const pendingFit = useRef(true)

  useEffect(() => {
    pendingFit.current = true
  }, [forceData])

  const fitAfterLayout = useCallback(() => {
    if (!pendingFit.current) return
    pendingFit.current = false
    fitAll()
  }, [fitAll])

  /**
   * 한 점으로 옮겨 간다. 오른쪽 목록·찾기 결과·캔버스가 모두 이 문을 쓴다.
   *
   * 꺼 둔 종류를 골랐으면 그 종류를 켜 준다. 목록에는 있는데 화면에는 없으면
   * 누른 것이 아무 데도 닿지 않은 것처럼 보인다.
   */
  const focusNode = useCallback(
    (id: string) => {
      const node = nodeById.get(id)
      if (!node) return
      setSelectedId(id)
      setQuery('')
      if (!visibleTypes.includes(node.node_type)) {
        setVisibleTypes((prev) => [...prev, node.node_type])
        // 방금 켠 종류는 아직 좌표가 없다. 배치가 끝나면 onEngineStop이 전체를
        // 화면에 맞추므로 여기서 따라가지 않는다.
        return
      }
      const live = forceData.nodes.find((n) => n.id === id)
      if (!live || live.x == null || !graphRef.current) return
      graphRef.current.centerAt(live.x, live.y, reduced ? 0 : 500)
      graphRef.current.zoom(2.2, reduced ? 0 : 500)
    },
    [nodeById, visibleTypes, forceData, reduced],
  )

  const toggleType = (type: string) => {
    // 지금 열어 둔 것이 사라지는 종류면 오른쪽 칸도 닫는다
    if (
      visibleTypes.includes(type) &&
      selectedId &&
      nodeById.get(selectedId)?.node_type === type
    ) {
      setSelectedId(null)
    }
    setVisibleTypes((prev) =>
      prev.includes(type) ? prev.filter((t) => t !== type) : [...prev, type],
    )
  }

  const zoomBy = (factor: number) => {
    const g = graphRef.current
    if (!g) return
    const next = Math.min(8, Math.max(0.2, g.zoom() * factor))
    g.zoom(next, reduced ? 0 : 220)
  }

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q || !graph) return []
    return graph.nodes.filter((n) => nodeTitle(n).toLowerCase().includes(q)).slice(0, 7)
  }, [query, graph])

  // --- 캔버스 그리기 ---

  const paintNode = useCallback(
    (node: any, ctx: CanvasRenderingContext2D, scale: number) => {
      const config = TYPE[node.node_type] ?? UNKNOWN_TYPE
      const r = config.size
      const lit = !focusSet || focusSet.has(node.id)
      const chosen = node.id === selectedId

      ctx.globalAlpha = lit ? 1 : 0.16

      const img = avatars.current.get(node.id)
      if (node.node_type === 'person' && img?.complete && img.naturalWidth > 0) {
        ctx.save()
        ctx.beginPath()
        ctx.arc(node.x, node.y, r, 0, TAU)
        ctx.clip()
        ctx.drawImage(img, node.x - r, node.y - r, r * 2, r * 2)
        ctx.restore()
        // 밝은 사진은 종이 바탕과 붙는다. 테를 한 겹 둘러 원형을 남긴다
        ctx.beginPath()
        ctx.arc(node.x, node.y, r, 0, TAU)
        ctx.strokeStyle = config.color
        ctx.lineWidth = 1.2 / scale
        ctx.stroke()
      } else {
        ctx.beginPath()
        ctx.arc(node.x, node.y, r, 0, TAU)
        ctx.fillStyle = config.color
        ctx.fill()
      }

      if (chosen) {
        ctx.beginPath()
        ctx.arc(node.x, node.y, r + 3.5, 0, TAU)
        ctx.strokeStyle = '#8A1538'
        ctx.lineWidth = 2 / scale
        ctx.stroke()
      }

      /*
       * 이름은 인물·추억·장소에 항상 붙인다. 예전에는 1.5배 넘게 확대해야
       * 나타났는데, 처음 열었을 때 이름 없는 점만 보이면 무엇을 눌러야 할지
       * 알 수 없다. 수가 많은 사진·기억은 확대했을 때만 적는다.
       */
      const always =
        node.node_type === 'person' ||
        node.node_type === 'event' ||
        node.node_type === 'place'
      if (!always && scale < 2.2) {
        ctx.globalAlpha = 1
        return
      }

      const size = Math.max(11 / scale, 2.6)
      ctx.font = `${chosen ? 600 : 400} ${size}px Pretendard, sans-serif`
      ctx.textAlign = 'center'
      ctx.textBaseline = 'top'
      const y = node.y + r + 3
      // 선 위에 글자가 겹쳐도 읽히게 종이색을 한 겹 깔고 쓴다
      ctx.strokeStyle = 'rgba(250, 250, 247, 0.92)'
      ctx.lineWidth = 3 / scale
      ctx.lineJoin = 'round'
      ctx.strokeText(node.label || '', node.x, y)
      ctx.fillStyle = chosen ? '#0E0D0B' : '#3F3C36'
      ctx.fillText(node.label || '', node.x, y)
      ctx.globalAlpha = 1
    },
    // avatarTick은 그리는 데 쓰지 않는다. 사진이 도착했을 때 이 함수를 새로
    // 만들어 캔버스를 다시 칠하게 하는 것이 목적이다.
    [focusSet, selectedId, avatarTick],
  )

  const paintPointerArea = useCallback(
    (node: any, color: string, ctx: CanvasRenderingContext2D) => {
      const config = TYPE[node.node_type] ?? UNKNOWN_TYPE
      ctx.fillStyle = color
      ctx.beginPath()
      // 누르는 자리는 그린 것보다 조금 넉넉하게 — 작은 점을 정확히 맞히기 어렵다
      ctx.arc(node.x, node.y, config.size + 3, 0, TAU)
      ctx.fill()
    },
    [],
  )

  const linkLit = useCallback(
    (link: any) =>
      !focusId || endId(link.source) === focusId || endId(link.target) === focusId,
    [focusId],
  )

  // --- 오른쪽 칸 ---

  const selected = selectedId ? nodeById.get(selectedId) : undefined
  const conns = selectedId ? connectionsById.get(selectedId) ?? [] : []
  const selectedEvent = selected?.node_type === 'event' ? eventById(selected.id) : undefined

  const groups = useMemo(() => {
    const byLabel = new Map<string, Group>()
    for (const [relation, dir] of GROUP_ORDER) {
      const label = RELATION_LABELS[relation]?.[dir]
      if (!label) continue
      for (const conn of conns) {
        if (conn.edge.relation !== relation || conn.dir !== dir) continue
        const node = nodeById.get(conn.otherId)
        if (!node) continue
        const group = byLabel.get(label) ?? { label, items: [] }
        // 사람 사이 관계는 "부부 · 부녀"처럼 구체적인 이름이 properties에 있다
        const note =
          relation === 'related_to'
            ? String(
                (conn.edge.properties as Record<string, unknown> | undefined)
                  ?.relation_type ?? '',
              )
            : node.relation || ''
        group.items.push({ node, note })
        byLabel.set(label, group)
      }
    }
    return Array.from(byLabel.values())
  }, [conns, nodeById])

  if (loading) {
    return (
      <Page width={1160}>
        <PageHeader eyebrow="Memory Graph" title="연결된 기억" />
        <p className="t-caption mt-8">불러오는 중…</p>
      </Page>
    )
  }

  if (failed) {
    return (
      <Page width={1160}>
        <PageHeader eyebrow="Memory Graph" title="연결된 기억" />
        <p className="t-body-sm mt-8 text-ink-400">
          연결을 불러오지 못했습니다. 잠시 뒤 다시 열어 주세요.
        </p>
      </Page>
    )
  }

  if (!graph || graph.nodes.length === 0) {
    return (
      <Page width={1160}>
        <PageHeader
          eyebrow="Memory Graph"
          title="연결된 기억"
          lead="가족·추억·장소가 어떻게 이어져 있는지 한 장에 보여 줍니다."
        />
        <div className="surface mt-8 p-8">
          <p className="t-body-sm m-0 text-ink-400">
            아직 이을 것이 없습니다. 사진을 올리고 첫 추억을 만들면 여기에 이어집니다.
          </p>
          <Link
            to="/collect"
            className="btn-outline mt-5 inline-block no-underline hover:no-underline"
          >
            사진 올리기
          </Link>
        </div>
      </Page>
    )
  }

  return (
    <Page width={1160}>
      <PageHeader
        eyebrow="Memory Graph"
        title="연결된 기억"
        lead="가족·추억·장소가 어떻게 이어져 있는지 한 장에 봅니다. 점을 누르면 그 사람이나 추억에 걸린 것이 오른쪽에 열립니다."
      />

      {/*
        필터와 찾기는 카드에 가두지 않고 화면 폭을 가로지르는 띠로 깔았다 —
        타임라인 · 지도와 같은 방식이다. 무엇이 켜져 있는지가 그림보다 먼저
        읽혀야 한다. 색 점을 칩 안에 넣어 범례를 따로 두지 않는다.
      */}
      <div
        className="mt-10 flex flex-wrap items-start gap-x-10 gap-y-6 py-5"
        style={{
          borderTop: '1px solid var(--border)',
          borderBottom: '1px solid var(--border)',
        }}
      >
        <div className="min-w-[340px]">
          <p className="t-eyebrow m-0 mb-2.5 text-ink-300">무엇을 볼까요</p>
          <div className="flex flex-wrap gap-1.5">
            {NODE_TYPES.map((config) => {
              const on = visibleTypes.includes(config.type)
              return (
                <button
                  key={config.type}
                  onClick={() => toggleType(config.type)}
                  aria-pressed={on}
                  className={`chip inline-flex items-center gap-1.5 ${on ? 'chip-on' : ''}`}
                >
                  <span
                    className="h-2 w-2 shrink-0 rounded-full"
                    style={{ background: config.color, opacity: on ? 1 : 0.35 }}
                  />
                  {config.label}
                  <span className={on ? 'text-accent-ink' : 'text-ink-300'}>
                    {counts[config.type] ?? 0}
                  </span>
                </button>
              )
            })}
          </div>
          {hiddenCount > 0 && (
            <p className="t-caption m-0 mt-2.5">
              {hiddenCount}개를 접어 두었습니다. 사진과 기억은 수가 많아 처음에는 끄고
              시작합니다 — 칩을 누르면 함께 나옵니다.
            </p>
          )}
        </div>

        <div className="min-w-[260px] flex-1">
          <p className="t-eyebrow m-0 mb-2.5 text-ink-300">찾기</p>
          <div className="relative">
            <Search
              size={15}
              strokeWidth={1.75}
              className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-300"
            />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="이름이나 추억 제목"
              aria-label="이름이나 추억 제목으로 찾기"
              className="field field-sm pl-9"
            />
          </div>
          {query.trim() && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {matches.length === 0 ? (
                <p className="t-caption m-0">찾는 것이 없습니다.</p>
              ) : (
                matches.map((node) => (
                  <button
                    key={node.id}
                    onClick={() => focusNode(node.id)}
                    className="chip inline-flex items-center gap-1.5"
                  >
                    <span
                      className="h-2 w-2 shrink-0 rounded-full"
                      style={{ background: (TYPE[node.node_type] ?? UNKNOWN_TYPE).color }}
                    />
                    {nodeTitle(node)}
                  </button>
                ))
              )}
            </div>
          )}
        </div>
      </div>

      <div
        className="mt-8 grid items-start gap-8"
        style={{ gridTemplateColumns: 'minmax(0,1.9fr) minmax(260px,0.72fr)' }}
      >
        <div>
          <div className="flex items-baseline justify-between gap-4">
            <p className="t-eyebrow m-0">
              {forceData.nodes.length}개가 선 {forceData.links.length}개로 이어져 있습니다
            </p>
            {/*
              확대·축소를 단추로도 둔다. 바퀴를 굴려야만 되는 화면은 노트북
              터치패드와 태블릿에서 아무 반응이 없는 것처럼 느껴진다.
            */}
            <div className="flex shrink-0 items-center gap-1">
              <button
                onClick={() => zoomBy(1.4)}
                className="btn-quiet px-2.5 py-1.5"
                aria-label="확대"
              >
                <Plus size={14} strokeWidth={2} />
              </button>
              <button
                onClick={() => zoomBy(1 / 1.4)}
                className="btn-quiet px-2.5 py-1.5"
                aria-label="축소"
              >
                <Minus size={14} strokeWidth={2} />
              </button>
              <button
                onClick={() => {
                  setSelectedId(null)
                  fitAll()
                }}
                className="btn-quiet inline-flex items-center gap-1.5"
              >
                <Maximize2 size={13} strokeWidth={2} />
                전체 보기
              </button>
            </div>
          </div>

          <div ref={boxRef} className="surface mt-3 overflow-hidden">
            {box.w > 0 && (
              <ForceGraph2D
                ref={graphRef}
                width={box.w}
                height={box.h}
                graphData={forceData}
                backgroundColor="#FFFFFF"
                nodeLabel={(node: any) =>
                  `${node.label} · ${(TYPE[node.node_type] ?? UNKNOWN_TYPE).label}`
                }
                nodeCanvasObject={paintNode}
                nodePointerAreaPaint={paintPointerArea}
                linkColor={(link: any) => {
                  if (!linkLit(link)) return LINK_DIM
                  if (focusId) return LINK_ON
                  return link.inferred ? LINK_INFERRED : LINK_CONFIRMED
                }}
                linkWidth={(link: any) => (focusId && linkLit(link) ? 1.8 : 0.7)}
                linkLineDash={(link: any) => (link.inferred ? [3, 3] : null)}
                onNodeClick={(node: any) => focusNode(node.id)}
                onNodeHover={(node: any) => setHoverId(node?.id ?? null)}
                onBackgroundClick={() => setSelectedId(null)}
                /*
                  배치를 200틱에서 멈추고 전체를 화면에 맞춘다. 기본값은 15초를
                  기다리므로 처음 열었을 때 한참 흔들린다.
                */
                warmupTicks={40}
                cooldownTicks={200}
                onEngineStop={fitAfterLayout}
              />
            )}
          </div>

          <div className="mt-2.5 flex flex-wrap items-center gap-x-5 gap-y-2">
            <p className="t-caption m-0">
              점을 누르면 걸린 것만 밝아집니다. 끌어서 옮기고, 바퀴나 위 단추로 확대합니다.
            </p>
            <span className="flex items-center gap-1.5 text-xs text-ink-400">
              <svg width="22" height="6" aria-hidden="true">
                <line x1="0" y1="3" x2="22" y2="3" stroke={LINK_CONFIRMED} strokeWidth="1" />
              </svg>
              확인된 연결
            </span>
            <span className="flex items-center gap-1.5 text-xs text-ink-400">
              <svg width="22" height="6" aria-hidden="true">
                <line
                  x1="0"
                  y1="3"
                  x2="22"
                  y2="3"
                  stroke={LINK_INFERRED}
                  strokeWidth="1"
                  strokeDasharray="3 3"
                />
              </svg>
              AI 추정 연결
            </span>
          </div>
        </div>

        {selected ? (
          <div className="surface p-6">
            <div className="flex items-center gap-2">
              <span
                className="h-2 w-2 rounded-full"
                style={{ background: (TYPE[selected.node_type] ?? UNKNOWN_TYPE).color }}
              />
              <span className="t-eyebrow text-ink-300">
                {(TYPE[selected.node_type] ?? UNKNOWN_TYPE).label}
              </span>
              <button
                onClick={() => setSelectedId(null)}
                className="ml-auto cursor-pointer border-0 bg-transparent p-0 text-ink-300"
                aria-label="닫기"
              >
                <X size={15} strokeWidth={2} />
              </button>
            </div>

            <p
              className="m-0 mt-3 text-lg font-semibold text-ink-900"
              style={{ textWrap: 'pretty' }}
            >
              {nodeTitle(selected)}
            </p>

            {/* 무엇인지 한 줄로 — 예전에는 이 자리에 노드 id가 있었다 */}
            <p className="t-body-sm m-0 mt-1 text-ink-400">
              {[
                selected.node_type === 'person' ? selected.relation : '',
                nodeDate(selected),
                `연결 ${conns.length}개`,
              ]
                .filter(Boolean)
                .join(' · ')}
            </p>

            {selectedEvent && (
              <span
                className="pill mt-3"
                style={{
                  background: (STATE_CONFIG[selectedEvent.state] ?? STATE_CONFIG.alone).bg,
                  color: (STATE_CONFIG[selectedEvent.state] ?? STATE_CONFIG.alone).fg,
                }}
              >
                {(STATE_CONFIG[selectedEvent.state] ?? STATE_CONFIG.alone).label}
              </span>
            )}

            {selected.confidence === 'ai_inferred' && (
              <span className="pill mt-3 bg-ink-50 font-normal text-ink-400">AI 추정</span>
            )}

            {selected.description && (
              <p className="t-body-sm mt-3" style={{ textWrap: 'pretty' }}>
                {selected.description}
              </p>
            )}
            {selected.content && (
              <p className="t-body-sm mt-3" style={{ textWrap: 'pretty' }}>
                “{selected.content}”
                {selected.contributor_id && (
                  <span className="t-caption ml-1.5">
                    — {nodeById.get(selected.contributor_id)?.name ?? '가족'}
                  </span>
                )}
              </p>
            )}

            {/* 그래프에서 끝나지 않게 한다. 여기서 본 것을 제대로 읽는 자리로 보낸다 */}
            {selected.node_type === 'event' && (
              <Link
                to={`/memory/${selected.id}`}
                className="btn-outline mt-4 inline-block no-underline hover:no-underline"
              >
                추억 열어 보기
              </Link>
            )}
            {selected.node_type === 'person' && (
              <Link
                to={`/album?person_id=${selected.id}`}
                className="btn-outline mt-4 inline-block no-underline hover:no-underline"
              >
                이 사람의 사진 보기
              </Link>
            )}
            {selected.node_type === 'place' && (
              <Link
                to="/map"
                className="btn-outline mt-4 inline-block no-underline hover:no-underline"
              >
                지도에서 보기
              </Link>
            )}
            {selected.node_type === 'media' && (
              <img
                src={mediaUrl(selected.thumbnail_path || selected.file_path)}
                alt={selected.original_filename || ''}
                className="mt-4 w-full rounded bg-ink-50 object-cover"
              />
            )}

            {groups.map((group) => {
              const isMedia = group.items[0]?.node.node_type === 'media'
              const limit = isMedia ? GROUP_LIMIT_MEDIA : GROUP_LIMIT
              const rest = group.items.length - limit

              return (
                <div key={group.label} className="mt-5">
                  <p className="t-eyebrow m-0 mb-2 text-ink-300">
                    {group.label} {group.items.length}
                  </p>
                  {/*
                    사진 묶음은 파일 이름을 늘어놓는 대신 썸네일을 깐다.
                    IMG_2481.jpg인 줄이 여섯 개 있으면 아무것도 고를 수 없다.
                  */}
                  {isMedia ? (
                    <div className="grid grid-cols-3 gap-1.5">
                      {group.items.slice(0, limit).map(({ node }) => (
                        <button
                          key={node.id}
                          onClick={() => focusNode(node.id)}
                          className="cursor-pointer border-0 bg-transparent p-0"
                          aria-label={`${nodeTitle(node)} 보기`}
                        >
                          <img
                            src={mediaUrl(node.thumbnail_path || node.file_path)}
                            alt=""
                            className="aspect-square w-full rounded bg-ink-50 object-cover"
                          />
                        </button>
                      ))}
                    </div>
                  ) : (
                    <div className="flex flex-wrap gap-1.5">
                      {group.items.slice(0, limit).map(({ node, note }) => (
                        <button
                          key={node.id}
                          onClick={() => focusNode(node.id)}
                          className="chip"
                        >
                          {nodeTitle(node)}
                          {note && <span className="ml-1.5 text-ink-300">{note}</span>}
                        </button>
                      ))}
                    </div>
                  )}
                  {rest > 0 && (
                    <p className="t-caption m-0 mt-1.5">이 밖에 {rest}개가 더 걸려 있습니다.</p>
                  )}
                </div>
              )
            })}
          </div>
        ) : (
          <div className="rounded-lg p-6" style={{ border: '1px dashed var(--border-strong)' }}>
            <p className="t-body-sm m-0 text-ink-900">이렇게 보세요</p>
            <ol className="t-body-sm m-0 mt-3 flex list-none flex-col gap-2.5 p-0 text-ink-400">
              <li>점을 하나 누릅니다 — 걸린 것만 밝아집니다.</li>
              <li>여기 열리는 목록에서 다음 사람이나 추억으로 건너갑니다.</li>
              <li>점선은 AI가 추정한 연결입니다. 가족이 확인하면 실선이 됩니다.</li>
            </ol>
            {/* 처음 열었을 때 무엇부터 누를지 정해 준다 — 자기 얼굴이 가장 쉽다 */}
            {current && nodeById.has(current.id) && (
              <button onClick={() => focusNode(current.id)} className="btn-outline mt-5">
                나부터 보기
              </button>
            )}
          </div>
        )}
      </div>
    </Page>
  )
}
