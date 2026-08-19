/**
 * 가족 공간 · 공개 범위의 낱말 (기획안 02장 · 08장)
 *
 * 값은 서버가 정하고(backend/models/graph_models.py의 FamilyRole · Visibility),
 * 여기 있는 것은 그 값을 사람 말로 적어 둔 것이다. 화면마다 다른 낱말을 쓰면
 * "누가 무엇을 볼 수 있는가"라는 약속이 흐려진다.
 */

import type { FamilyRole, Visibility } from './api'

export const ROLE_LABEL: Record<FamilyRole, string> = {
  owner: '가족 관리자',
  contributor: '기록자',
  viewer: '열람자',
  invited: '초대 대기',
}

export const ROLE_DESC: Record<FamilyRole, string> = {
  owner: '구성원 초대, 공개 범위, 삭제·이관을 결정합니다.',
  contributor: '기록을 올리고 기억을 남기고 확인에 참여합니다.',
  viewer: '함께 보고 들을 수 있지만 기록을 바꾸지 않습니다.',
  invited: '초대 링크를 보냈고 아직 참여하지 않았습니다.',
}

export const ROLE_ORDER: FamilyRole[] = ['owner', 'contributor', 'viewer', 'invited']

export const VISIBILITY_LABEL: Record<Visibility, string> = {
  family: '가족 전체',
  partial: '일부 가족',
  private: '개인 전용',
}

export const VISIBILITY_DESC: Record<Visibility, string> = {
  family: '참여한 가족 구성원 모두가 봅니다.',
  partial: '고른 사람만 봅니다.',
  private: '올린 사람만 봅니다.',
}

export const VISIBILITIES: Visibility[] = ['family', 'partial', 'private']
