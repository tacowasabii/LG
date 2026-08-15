import { useEffect, useState, useRef, useCallback } from 'react'
import ForceGraph2D from 'react-force-graph-2d'
import { getGraph, GraphData, GraphNode } from '../lib/api'

const NODE_COLORS: Record<string, string> = {
  person: '#3b82f6',
  event: '#f97316',
  place: '#22c55e',
  media: '#8b5cf6',
  memory: '#ec4899',
}

const NODE_SIZES: Record<string, number> = {
  person: 8,
  event: 7,
  place: 6,
  media: 5,
  memory: 5,
}

export default function GraphPage() {
  const [graphData, setGraphData] = useState<GraphData | null>(null)
  const [selected, setSelected] = useState<GraphNode | null>(null)
  const [relatedMedia, setRelatedMedia] = useState<GraphNode[]>([])
  const [loading, setLoading] = useState(true)
  const graphRef = useRef<any>(null)

  useEffect(() => {
    getGraph()
      .then(setGraphData)
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  const handleNodeClick = useCallback((node: any) => {
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
          (n) => connectedIds.has(n.id) && n.node_type === 'event'
        )
        for (const event of connectedEvents) {
          for (const edge of graphData.edges) {
            if (edge.target === event.id || edge.source === event.id) {
              const otherId = edge.source === event.id ? edge.target : edge.source
              const otherNode = graphData.nodes.find((n) => n.id === otherId)
              if (otherNode && otherNode.node_type === 'media' && !mediaNodes.find((m) => m.id === otherNode.id)) {
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
  }, [graphData])

  if (loading) {
    return <div className="flex items-center justify-center h-64"><p className="text-gray-400">그래프 로딩 중...</p></div>
  }

  if (!graphData || graphData.nodes.length === 0) {
    return (
      <div className="text-center py-20">
        <p className="text-gray-400">그래프 데이터가 없습니다. 먼저 미디어를 업로드해주세요.</p>
      </div>
    )
  }

  // Transform data for force-graph
  const forceData = {
    nodes: graphData.nodes.map((n) => ({
      ...n,
      label: n.name || n.title || n.content?.slice(0, 20) || n.original_filename || n.id,
      color: NODE_COLORS[n.node_type] || '#94a3b8',
      val: NODE_SIZES[n.node_type] || 5,
    })),
    links: graphData.edges.map((e) => ({
      source: e.source,
      target: e.target,
      relation: e.relation,
    })),
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Memory Graph</h1>
          <p className="text-gray-500 mt-1">
            노드 {graphData.nodes.length}개 · 연결 {graphData.edges.length}개
          </p>
        </div>
        {/* Legend */}
        <div className="flex gap-3">
          {Object.entries(NODE_COLORS).map(([type, color]) => (
            <div key={type} className="flex items-center gap-1.5 text-xs text-gray-600">
              <div className="w-3 h-3 rounded-full" style={{ backgroundColor: color }} />
              <span>{type}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="flex gap-4">
        {/* Graph */}
        <div className="flex-1 card p-0 overflow-hidden" style={{ height: '600px' }}>
          <ForceGraph2D
            ref={graphRef}
            graphData={forceData}
            nodeLabel="label"
            nodeColor="color"
            nodeVal="val"
            linkDirectionalArrowLength={4}
            linkDirectionalArrowRelPos={1}
            linkColor={() => '#d1d5db'}
            onNodeClick={handleNodeClick}
            nodeCanvasObject={(node: any, ctx, globalScale) => {
              const size = node.val || 5
              // Circle
              ctx.beginPath()
              ctx.arc(node.x, node.y, size, 0, 2 * Math.PI)
              ctx.fillStyle = node.color
              ctx.fill()

              // Label (only at higher zoom)
              if (globalScale > 1.5) {
                ctx.font = `${Math.max(10 / globalScale, 3)}px sans-serif`
                ctx.textAlign = 'center'
                ctx.textBaseline = 'top'
                ctx.fillStyle = '#374151'
                ctx.fillText(node.label || '', node.x, node.y + size + 2)
              }
            }}
          />
        </div>

        {/* Detail Panel */}
        {selected && (
          <div className="w-72 card space-y-3">
            <div className="flex items-center gap-2">
              <div
                className="w-4 h-4 rounded-full"
                style={{ backgroundColor: NODE_COLORS[selected.node_type] || '#94a3b8' }}
              />
              <span className="text-xs font-medium text-gray-500 uppercase">{selected.node_type}</span>
            </div>

            <h3 className="font-semibold text-gray-900">
              {selected.name || selected.title || selected.content?.slice(0, 50) || selected.original_filename}
            </h3>

            {selected.relation && <p className="text-sm text-gray-600">관계: {selected.relation}</p>}
            {selected.description && <p className="text-sm text-gray-600">{selected.description}</p>}
            {selected.date_start && <p className="text-sm text-gray-500">📅 {selected.date_start}</p>}
            {selected.exif_date && <p className="text-sm text-gray-500">📅 {selected.exif_date?.slice(0, 10)}</p>}
            {selected.content && <p className="text-sm text-gray-600 italic">"{selected.content}"</p>}

            {selected.file_path && (
              <div className="rounded-lg overflow-hidden bg-gray-100">
                <img src={selected.file_path} alt="" className="w-full" />
              </div>
            )}

            {/* Related Media */}
            {relatedMedia.length > 0 && (
              <div className="space-y-2">
                <p className="text-xs font-medium text-gray-500 uppercase">연관 사진 ({relatedMedia.length})</p>
                <div className="grid grid-cols-2 gap-1.5">
                  {relatedMedia.map((media) => (
                    <div key={media.id} className="aspect-square rounded-md overflow-hidden bg-gray-100">
                      {media.media_type === 'video' ? (
                        <video src={media.file_path} className="w-full h-full object-cover" muted playsInline />
                      ) : (
                        <img
                          src={media.thumbnail_path || media.file_path}
                          alt={media.original_filename || ''}
                          className="w-full h-full object-cover"
                        />
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            <button onClick={() => { setSelected(null); setRelatedMedia([]) }} className="text-xs text-gray-400 hover:text-gray-600">
              닫기
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
