/**
 * Memory Film 옵션 라벨 (기획안 "세대별 길이와 설명 수준 조정")
 *
 * 서버가 실제로 장면 길이와 내레이션 어투를 바꾼다
 * (backend/services/film_composer.py의 AUDIENCE_PACE / AUDIENCE_TONE).
 * 여기 있는 것은 그 선택을 사람 말로 적어 둔 것뿐이다.
 */

export type Audience = 'child' | 'adult' | 'elder'
export type FilmLength = 30 | 45 | 60

export const AUDIENCE_LABEL: Record<Audience, string> = {
  child: '아이용',
  adult: '성인용',
  elder: '어르신용',
}

export const AUDIENCE_DESC: Record<Audience, string> = {
  child: '쉬운 낱말, 짧은 문장, 인물 이름을 자주 부릅니다.',
  adult: '추억의 배경과 관계를 설명합니다.',
  elder: '전환을 늦추고, 당시 호칭을 그대로 씁니다.',
}
