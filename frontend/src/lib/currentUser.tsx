/**
 * 현재 사용자(= 지금 쓰는 사람) 컨텍스트
 *
 * 기획안 08장은 "누가 남긴 기억이고 누가 확인했는지"를 제품의 핵심으로 둔다.
 * 계정 로그인은 아직 없으므로, 가족 공간 안에서 "지금 나는 누구인가"를
 * 명시적으로 고르는 방식으로 귀속을 분명히 한다.
 *
 * 고른 사람은 api.setViewer로 심어 모든 조회에 함께 나간다. 서버가 그 사람의
 * 열람 범위에 맞춰 기록을 가려 준다 (backend/services/visibility.py).
 *
 * 로그인이 붙으면 이 파일은 세션에서 사용자를 읽고 고르는 UI는 사라진다.
 */

import { createContext, useContext, useEffect, useState, ReactNode } from 'react'
import { FamilyMember, getFamilySpace, setViewer } from './api'

interface CurrentUserValue {
  current: FamilyMember | null
  members: FamilyMember[]
  spaceName: string
  loading: boolean
  /** 백엔드에 못 붙었을 때의 이유. 화면이 "불러오는 중"에 갇히지 않게 한다 */
  error: string | null
  setCurrentId: (id: string) => void
  /** 역할·동의가 바뀐 뒤 다시 받아온다 */
  reload: () => void
}

const CurrentUserContext = createContext<CurrentUserValue | null>(null)

/** 마지막으로 고른 사람을 기억한다 (새로고침해도 같은 사람으로) */
const STORAGE_KEY = 'homestory.viewer'

export function CurrentUserProvider({ children }: { children: ReactNode }) {
  const [members, setMembers] = useState<FamilyMember[]>([])
  const [spaceName, setSpaceName] = useState('')
  const [currentId, setCurrentId] = useState<string | null>(
    () => window.localStorage.getItem(STORAGE_KEY),
  )
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = () => {
    setError(null)
    getFamilySpace()
      .then((space) => {
        setSpaceName(space.space_name)
        setMembers(space.members)
      })
      .catch((e) => {
        console.error('[family] 구성원을 불러오지 못했습니다', e)
        // 배포에서 가장 흔한 두 가지 원인을 그대로 알려 준다.
        // 이 화면이 조용히 비어 있으면 원인을 찾는 데 한참 걸린다 (겪었다).
        setError(
          '백엔드에 연결할 수 없습니다. VITE_API_URL(프론트)과 ALLOWED_ORIGINS(백엔드)를 확인하세요.',
        )
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    load()
  }, [])

  // 초대 대기는 아직 쓰는 사람이 아니다
  const active = members.filter((m) => m.role !== 'invited')
  const current =
    active.find((m) => m.id === currentId) ||
    // 처음 열었으면 가족 관리자로 시작한다 (기획안이 지목한 30~50대 기록자)
    active.find((m) => m.role === 'owner') ||
    active[0] ||
    null

  // 고른 사람을 API 계층에 심는다 — 이후 모든 조회가 이 사람의 시야로 나간다
  useEffect(() => {
    setViewer(current?.id ?? null)
    if (current) window.localStorage.setItem(STORAGE_KEY, current.id)
  }, [current?.id])

  return (
    <CurrentUserContext.Provider
      value={{
        current,
        members: active,
        spaceName,
        loading,
        error,
        setCurrentId,
        reload: load,
      }}
    >
      {children}
    </CurrentUserContext.Provider>
  )
}

export function useCurrentUser(): CurrentUserValue {
  const ctx = useContext(CurrentUserContext)
  if (!ctx) {
    throw new Error('useCurrentUser는 CurrentUserProvider 안에서만 쓸 수 있습니다.')
  }
  return ctx
}
