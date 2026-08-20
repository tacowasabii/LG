/**
 * 현재 사용자(= 로그인한 사람) 컨텍스트
 *
 * 기획안 08장은 "누가 남긴 기억이고 누가 확인했는지"를 제품의 핵심으로 둔다.
 * 그래서 화면에 보이는 프로필은 로그인한 본인 하나다 — 다른 구성원으로
 * 갈아타는 UI는 두지 않는다. 남의 이름으로 기억을 남길 수 있으면 귀속이
 * 무너진다.
 *
 * 이 사람은 api.setViewer로 심어 모든 조회에 함께 나간다. 서버가 그 사람의
 * 열람 범위에 맞춰 기록을 가려 준다 (backend/services/visibility.py).
 *
 * 계정 로그인 자체는 아직 없다. 세션 대신 초대 참여(JoinPage)에서 정해진
 * 사람을 브라우저에 기억해 두고, 아무것도 없으면 가족 관리자로 시작한다.
 * 로그인이 붙으면 이 파일은 저장소 대신 세션에서 사용자를 읽는다.
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
  /** 로그인하는 지점에서만 부른다 — 초대로 참여한 사람(JoinPage)이 그대로 쓴다 */
  setCurrentId: (id: string) => void
  /** 역할·동의가 바뀐 뒤 다시 받아온다 */
  reload: () => void
}

const CurrentUserContext = createContext<CurrentUserValue | null>(null)

/** 로그인한 사람을 기억한다 (새로고침해도 같은 사람으로) — 세션 대신이다 */
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

  // 초대 대기는 아직 로그인할 수 있는 사람이 아니다
  const active = members.filter((m) => m.role !== 'invited')
  const current =
    active.find((m) => m.id === currentId) ||
    // 참여 기록이 없으면 가족 관리자로 시작한다 (기획안이 지목한 30~50대 기록자)
    active.find((m) => m.role === 'owner') ||
    active[0] ||
    null

  // 로그인한 사람을 API 계층에 심는다 — 이후 모든 조회가 이 사람의 시야로 나간다
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
