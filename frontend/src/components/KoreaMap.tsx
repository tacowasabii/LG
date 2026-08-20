/**
 * 가족 이동 지도 (기획안 02장 Family Timeline & Map)
 *
 * 외부 지도 SDK를 붙이지 않고 SVG로 그린다. 이 단계의 목적은 화면 설계 확정이고,
 * 지도 타일은 네트워크·키·비용이 따라오므로 배치와 상호작용만 먼저 굳힌다.
 *
 * 격자선을 깔지 않는다. 이 지도가 답하는 질문은 "정확히 어디"가 아니라 "우리
 * 가족의 기억이 어느 쪽에 몰려 있나"이고, 격자는 그 답을 읽는 데 방해만 된다.
 * 남는 것은 해안선 한 겹, 연도순 이동을 잇는 점선, 그리고 기록 수만큼 커지는 점.
 *
 * 실기능 개발 시 교체 지점:
 *   이 컴포넌트 전체 -> 지도 SDK(예: Leaflet/Mapbox) 컴포넌트로 교체.
 *   project() 좌표 변환과 마커·라벨 규칙은 그대로 옮겨 쓸 수 있다.
 */

import { useState } from 'react'
import type { MemoryState } from '../lib/api'

export interface MapPoint {
  id: string
  name: string
  lat: number
  lng: number
  /** 마커 크기에 반영할 기록 수 */
  count: number
  state?: MemoryState
}

const VIEW_W = 320
const VIEW_H = 440

// 남한이 들어가는 경계 상자
const LAT_MAX = 38.7
const LAT_MIN = 32.9
const LNG_MIN = 125.6
const LNG_MAX = 130.0

export function project(lat: number, lng: number): { x: number; y: number } {
  return {
    x: ((lng - LNG_MIN) / (LNG_MAX - LNG_MIN)) * VIEW_W,
    y: ((LAT_MAX - lat) / (LAT_MAX - LAT_MIN)) * VIEW_H,
  }
}

/** 단순화한 남한 해안선 (경도, 위도) */
const MAINLAND: Array<[number, number]> = [
  [126.0, 38.35],
  [126.9, 38.3],
  [127.6, 38.35],
  [128.35, 38.45],
  [129.05, 37.55],
  [129.35, 36.8],
  [129.45, 36.05],
  [129.35, 35.55],
  [129.1, 35.1],
  [128.6, 34.95],
  [128.0, 34.8],
  [127.45, 34.6],
  [126.85, 34.35],
  [126.4, 34.6],
  [126.3, 35.15],
  [126.45, 35.75],
  [126.6, 36.15],
  [126.35, 36.55],
  [126.75, 36.95],
  [126.55, 37.3],
  [126.75, 37.6],
  [126.55, 37.9],
]

/** 제주도 */
const JEJU: Array<[number, number]> = [
  [126.15, 33.35],
  [126.35, 33.52],
  [126.7, 33.55],
  [126.95, 33.45],
  [126.9, 33.25],
  [126.55, 33.18],
  [126.25, 33.22],
]

function toPath(coords: Array<[number, number]>): string {
  return (
    coords
      .map(([lng, lat], i) => {
        const { x, y } = project(lat, lng)
        return (i === 0 ? 'M' : 'L') + x.toFixed(1) + ' ' + y.toFixed(1)
      })
      .join(' ') + ' Z'
  )
}

interface Props {
  points: MapPoint[]
  selectedId?: string | null
  onSelect?: (id: string) => void
  /** 사건을 연도순으로 이은 이동 경로 */
  showRoute?: boolean
}

export default function KoreaMap({ points, selectedId, onSelect, showRoute = true }: Props) {
  const [hovered, setHovered] = useState<string | null>(null)

  const routePath = points
    .map((p, i) => {
      const { x, y } = project(p.lat, p.lng)
      return (i === 0 ? 'M' : 'L') + x.toFixed(1) + ' ' + y.toFixed(1)
    })
    .join(' ')

  return (
    <svg
      viewBox={'0 0 ' + VIEW_W + ' ' + VIEW_H}
      className="h-auto w-full"
      style={{
        background: 'var(--paper-pure)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--r-lg)',
      }}
      role="img"
      aria-label="가족의 기억이 남은 장소"
    >
      <path d={toPath(MAINLAND)} fill="var(--ink-50)" stroke="var(--ink-100)" strokeWidth="1" />
      <path d={toPath(JEJU)} fill="var(--ink-50)" stroke="var(--ink-100)" strokeWidth="1" />

      {/* 이동 경로 — 사건을 연도순으로 이은 점선 */}
      {showRoute && points.length > 1 && (
        <path
          d={routePath}
          fill="none"
          stroke="var(--accent)"
          strokeWidth="1"
          strokeDasharray="3 3"
          opacity="0.35"
        />
      )}

      {points.map((p) => {
        const { x, y } = project(p.lat, p.lng)
        const isActive = selectedId === p.id || hovered === p.id
        const r = 4 + Math.min(6, p.count)

        return (
          <g
            key={p.id}
            onClick={() => onSelect?.(p.id)}
            onMouseEnter={() => setHovered(p.id)}
            onMouseLeave={() => setHovered(null)}
            className="cursor-pointer"
          >
            <circle
              cx={x}
              cy={y}
              r={r + 5}
              fill="var(--accent)"
              opacity={isActive ? 0.16 : 0.07}
            />
            <circle
              cx={x}
              cy={y}
              r={r}
              fill={isActive ? 'var(--accent)' : 'var(--accent-ink)'}
              stroke="var(--paper-pure)"
              strokeWidth="1.5"
            />
            {isActive && (
              <g>
                <rect
                  x={x + r + 6}
                  y={y - 9}
                  width={p.name.length * 8 + 12}
                  height={18}
                  rx="4"
                  fill="var(--ink-900)"
                />
                <text x={x + r + 6} y={y + 3.5} dx="6" fontSize="10" fill="var(--paper)">
                  {p.name}
                </text>
              </g>
            )}
          </g>
        )
      })}
    </svg>
  )
}
