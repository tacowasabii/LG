import { useEffect, useState, useRef, useCallback } from 'react'
import ForceGraph2D from 'react-force-graph-2d'
import { getGraph, GraphData, GraphNode, mediaUrl } from '../lib/api'
import { STATE_CONFIG } from '../components/StatusPill'
import { Page } from '../components/Page'
import { useEvents } from '../lib/useGraphData'

/**
 * 노드 색은 종류를 구분하는 것이 전부이므로 계조 안에서 고른다. 인물은 잉크,
 * 사건은 강조색, 장소·기억은 상태색을 빌려 쓰고, 원본 기록은 가장 옅은 회색에
 * 둔다 — 기록은 수가 가장 많고 그 자체로 읽을 내용이 없다.
 */
const NODE_COLORS: Record<string, string> = {
  person: '#1F1D1A',
  event: '#8A1538',
  place: '#17766B',
  media: '#C9C6BC',
  memory: '#7C5CB0',
}

/** 화면에 쓰는 낱말을 기획안 용어로 맞춘다 */
const NODE_LABELS: Record<string, string> = {
  person: '인물',
  event: '사건',
  place: '장소',
  media: '기록',
  memory: '기억',
}

const NODE_SIZES: Record<string, number> = {
  person: 8,
  event: 7,
  place: 6,
  media: 5,
  memory: 5,
}

const LINK_CONFIRMED = '#9C988C'
const LINK_INFERRED = '#C9C6BC'

export default function GraphPage() {
  // 사건 노드에 가족 확인 상태를 붙이기 위해 사건 요약을 함께 받는다
  const { eventById } = useEvents()
  const [graphData, setGraphData] = useState<GraphData | null>(null)
  const [selected, setSelected] = useState<GraphNode | null>(null)
  const [relatedMedia, setRelatedMedia] = useState<GraphNode[]>([])
  const [loading, setLoading] = useState(true)
  const graphRef = useRef<any>(null)

  /*
   * ForceGraph2D는 크기를 주지 않으면 창 크기를 그대로 쓴다. 그래프가 화면의
   * 한 칸을 차지하는 배치에서는 캔버스가 칸을 넘겨 잘리므로, 칸의 실제 폭을
   * 재서 넘긴다. 높이는 디자인의 4:3 비율을 따른다.
   */
  const boxRef = useRef<HTMLDivElement>(null)
  const [box, setBox] = useState({ w: 0, h: 0 })

  useEffect(() => {
    const el = boxRef.current
    if (!el) return
    const observer = new ResizeObserver(([entry]) => {
      const w = Math.round(entry.contentRect.width)
      setBox({ w, h: Math.round((w * 540) / 720) })
    })
    observer.observe(el)
    return () => observer.disconnect()
  }, [loading])

  useEffect(() => {
    getGraph()
      .then(setGraphData)
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  const handleNodeClick = useCallback(
    (node: any) => {
      setSelected(node)
      // Find related media nodes via edges
      if (graphData) {
        const nodeId = node.id
        const connectedIds = new Set<string>()

        // Find all nodes connected to this node
        for (const edge of graphData.edges) {
          if (edge.source === nodeId) connectedIds.add(edge.target)
          if (edge.target === nodeId) connectedIds.add(edge.source)
        }

        // If selected is not media, find media in connected nodes
        // If selected is media, also find media connected to the same event
        const mediaNodes: GraphNode[] = []

        if (node.node_type === 'media') {
          mediaNodes.push(node)
        } else {
          // Direct media connections
          for (const n of graphData.nodes) {
            if (connectedIds.has(n.id) && n.node_type === 'media') {
              mediaNodes.push(n)
            }
          }
        }

        // If it's a person/place, also find media connected through events
        if (node.node_type === 'person' || node.node_type === 'place') {
          const connectedEvents = graphData.nodes.filter(
            (n) => connectedIds.has(n.id) && n.node_type === 'event',
          )
          for (const event of connectedEvents) {
            for (const edge of graphData.edges) {
              if (edge.target === event.id || edge.source === event.id) {
                const otherId = edge.source === event.id ? edge.target : edge.source
                const otherNode = graphData.nodes.find((n) => n.id === otherId)
                if (
                  otherNode &&
                  otherNode.node_type === 'media' &&
                  !mediaNodes.find((m) => m.id === otherNode.id)
                ) {
                  mediaNodes.push(otherNode)
                }
              }
            }
          }
        }

        setRelatedMedia(mediaNodes.slice(0, 6))
      }

      // Zoom to node
      if (graphRef.current) {
        graphRef.current.centerAt(node.x, node.y, 500)
        graphRef.current.zoom(3, 500)
      }
    },
    [graphData],
  )

  if (loading) {
    return (
      <Page width={1160}>
        <p className="t-caption">그래프를 불러오는 중…</p>
      </Page>
    )
  }

  if (!graphData || graphData.nodes.length === 0) {
    return (
      <Page width={1160}>
        <p className="t-body-sm text-ink-300">
          그래프에 아직 아무것도 없습니다. 먼저 기록을 올려 주세요.
        </p>
      </Page>
    )
  }

  // 노드별 신뢰도를 미리 뽑아 엣지 선 모양에 반영한다.
  // 기획안은 "모든 관계에 근거와 신뢰도를 부여"한다고 했다. 엣지 자체에 신뢰도
  // 필드가 생기기 전까지는 양 끝 노드의 confidence로 대신 표시한다.
  const nodeConfidence: Record<string, string> = {}
  graphData.nodes.forEach((n) => {
    nodeConfidence[n.id] = (n as any).confidence || 'user_unverified'
  })

  // Transform data for force-graph
  const forceData = {
    nodes: graphData.nodes.map((n) => ({
      ...n,
      label: n.name || n.title || n.content?.slice(0, 20) || n.original_filename || n.id,
      color: NODE_COLORS[n.node_type] || '#9C988C',
      val: NODE_SIZES[n.node_type] || 5,
    })),
    links: graphData.edges.map((e) => ({
      source: e.source,
      target: e.target,
      relation: e.relation,
      inferred:
        nodeConfidence[e.source] === 'ai_inferred' || nodeConfidence[e.target] === 'ai_inferred',
    })),
  }

  const inferredCount = forceData.links.filter((l) => l.inferred).length

  const connCount = selected
    ? graphData.edges.filter((e) => e.source === selected.id || e.target === selected.id).length
    : 0
  const selectedEvent = selected?.node_type === 'event' ? eventById(selected.id) : undefined

  return (
    <Page width={1160}>
      <div className="flex flex-wrap items-end justify-between gap-8">
        <div>
          <p className="t-eyebrow m-0 mb-3">Memory Graph</p>
          <h2 className="t-title m-0">연결된 기억</h2>
          <p className="t-mono m-0 mt-3 text-xs text-ink-400">
            노드 {graphData.nodes.length} · 연결 {graphData.edges.length} · 추정 연결{' '}
            {inferredCount}
          </p>
        </div>

        <div className="flex flex-col items-end gap-2.5">
          <div className="flex gap-4">
            {Object.entries(NODE_COLORS).map(([type, color]) => (
              <span key={type} className="flex items-center gap-1.5 text-xs text-ink-500">
                <span className="h-2 w-2 rounded-full" style={{ background: color }} />
                {NODE_LABELS[type] || type}
              </span>
            ))}
          </div>
          <div className="flex gap-4">
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
      </div>

      <div
        className="mt-8 grid items-start gap-8"
        style={{ gridTemplateColumns: 'minmax(0,1.9fr) minmax(200px,0.65fr)' }}
      >
        <div ref={boxRef} className="surface overflow-hidden">
          {box.w > 0 && (
            <ForceGraph2D
              ref={graphRef}
              width={box.w}
              height={box.h}
              graphData={forceData}
              nodeLabel="label"
              nodeColor="color"
              nodeVal="val"
              backgroundColor="#FFFFFF"
              linkDirectionalArrowLength={4}
              linkDirectionalArrowRelPos={1}
              linkColor={(link: any) => (link.inferred ? LINK_INFERRED : LINK_CONFIRMED)}
              linkLineDash={(link: any) => (link.inferred ? [3, 3] : null)}
              onNodeClick={handleNodeClick}
              nodeCanvasObject={(node: any, ctx, globalScale) => {
                const size = node.val || 5
                ctx.beginPath()
                ctx.arc(node.x, node.y, size, 0, 2 * Math.PI)
                ctx.fillStyle = node.color
                ctx.fill()

                // 이름은 확대했을 때만 — 다 보이면 점의 밀도가 읽히지 않는다
                if (globalScale > 1.5) {
                  ctx.font = `${Math.max(10 / globalScale, 3)}px Pretendard, sans-serif`
                  ctx.textAlign = 'center'
                  ctx.textBaseline = 'top'
                  ctx.fillStyle = '#3F3C36'
                  ctx.fillText(node.label || '', node.x, node.y + size + 2)
                }
              }}
            />
          )}
        </div>

        {selected ? (
          <div className="surface p-6">
            <div className="flex items-center gap-2">
              <span
                className="h-2 w-2 rounded-full"
                style={{ background: NODE_COLORS[selected.node_type] || '#9C988C' }}
              />
              <span className="t-eyebrow text-ink-300">
                {NODE_LABELS[selected.node_type] || selected.node_type}
              </span>
              <button
                onClick={() => {
                  setSelected(null)
                  setRelatedMedia([])
                }}
                className="ml-auto cursor-pointer border-0 bg-transparent text-sm text-ink-300"
                aria-label="닫기"
              >
                ✕
              </button>
            </div>

            <p
              className="m-0 mt-3 text-lg font-semibold text-ink-900"
              style={{ textWrap: 'pretty' }}
            >
              {selected.name ||
                selected.title ||
                selected.content?.slice(0, 50) ||
                selected.original_filename}
            </p>
            <p className="t-mono m-0 mt-1 text-[11px] text-ink-300">
              {selected.id} · 연결 {connCount}개
            </p>

            {/* 추억이면 기억이 얼마나 쌓였는지 함께 보여준다 */}
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

            {(selected as any).confidence === 'ai_inferred' && (
              <span className="pill mt-3 bg-ink-50 font-normal text-ink-400">AI 추정</span>
            )}

            {selected.relation && <p className="t-body-sm mt-3">{selected.relation}</p>}
            {selected.description && (
              <p className="t-body-sm mt-3" style={{ textWrap: 'pretty' }}>
                {selected.description}
              </p>
            )}
            {selected.content && (
              <p className="t-body-sm mt-3" style={{ textWrap: 'pretty' }}>
                “{selected.content}”
              </p>
            )}
            {(selected.date_start || selected.exif_date) && (
              <p className="t-mono m-0 mt-2.5 text-[11px] text-ink-400">
                {selected.date_start || selected.exif_date?.slice(0, 10)}
              </p>
            )}

            {relatedMedia.length > 0 && (
              <div className="mt-5">
                <p className="t-eyebrow m-0 mb-2 text-ink-300">연관 기록</p>
                <div className="grid grid-cols-2 gap-1.5">
                  {relatedMedia.map((media) =>
                    media.media_type === 'video' ? (
                      <video
                        key={media.id}
                        src={mediaUrl(media.file_path)}
                        className="aspect-square w-full rounded bg-ink-50 object-cover"
                        muted
                        playsInline
                      />
                    ) : (
                      <img
                        key={media.id}
                        src={mediaUrl(media.thumbnail_path || media.file_path)}
                        alt={media.original_filename || ''}
                        className="aspect-square w-full rounded bg-ink-50 object-cover"
                      />
                    ),
                  )}
                </div>
              </div>
            )}
          </div>
        ) : (
          <div
            className="rounded-lg p-6"
            style={{ border: '1px dashed var(--border-strong)' }}
          >
            <p className="t-body-sm m-0 text-ink-400">
              노드를 누르면 그 사람·사건·장소에 걸린 연결과 원본 기록이 열립니다.
            </p>
            <p className="t-caption m-0 mt-3">
              점선은 AI가 추정한 연결입니다. 가족이 확인하면 실선이 됩니다.
            </p>
          </div>
        )}
      </div>
    </Page>
  )
}
