/**
 * 현재 사용자(= 지금 답하는 사람) 컨텍스트
 *
 * 기획안 08장은 "누가 남긴 기억이고 누가 확인했는지"를 제품의 핵심으로 둔다.
 * 계정 로그인은 아직 없으므로, 가족 공간 안에서 "지금 나는 누구인가"를
 * 명시적으로 고르는 방식으로 귀속을 분명히 한다.
 *
 * 실기능 개발 시 교체 지점: MOCK_MEMBERS -> 로그인 세션 / GET /api/family/me
 */

import { createContext, useContext, useState, ReactNode } from 'react'
import { MOCK_MEMBERS, FamilyMember } from '../mock/family'

interface CurrentUserValue {
  current: FamilyMember
  members: FamilyMember[]
  setCurrentId: (id: string) => void
}

const CurrentUserContext = createContext<CurrentUserValue | null>(null)

/** 기본값은 가족 관리자(김하늘) — 기획안이 지목한 30~50대 "가족 기록자" */
const DEFAULT_ID = 'P03'

export function CurrentUserProvider({ children }: { children: ReactNode }) {
  const [currentId, setCurrentId] = useState(DEFAULT_ID)

  const members = MOCK_MEMBERS.filter((m) => m.role !== 'invited')
  const current = members.find((m) => m.id === currentId) || members[0]

  return (
    <CurrentUserContext.Provider value={{ current, members, setCurrentId }}>
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
