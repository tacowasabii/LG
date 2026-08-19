/**
 * 목데이터 — Family Space / 역할 / 동의 (기획안 02장 Family Space, 08장 Trust & Ethics)
 *
 * 실기능 개발 시 교체 지점:
 *   MOCK_MEMBERS     -> GET  /api/family/members
 *   MOCK_INVITE      -> POST /api/family/invite
 *   MOCK_ASSET_SCOPE -> GET/PUT /api/family/visibility
 *
 * 인물 id는 실제 그래프(P01~P07)와 같게 맞춰 두었다. 실제 API로 바꿀 때
 * 화면 코드를 고치지 않아도 되도록 필드명도 백엔드 후보 스키마를 따랐다.
 */

export type FamilyRole = 'owner' | 'contributor' | 'viewer' | 'invited'
export type Visibility = 'family' | 'partial' | 'private'

export interface FamilyMember {
  id: string
  name: string
  relation: string
  birth_year: number
  role: FamilyRole
  thumbnail_url: string | null
  joined_at: string | null
  /** 이 사람이 올린 원본 기록 수 */
  asset_count: number
  /** 이 사람이 남긴 기억 수 */
  memory_count: number
  /** 이 사람이 확인해 준 사건 수 */
  verified_count: number
  /** 인물별 비공개 요청 (기획안 08장 인물 동의) */
  private_request: boolean
}

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

export const VISIBILITY_LABEL: Record<Visibility, string> = {
  family: '가족 전체',
  partial: '일부 가족',
  private: '개인 전용',
}

export const MOCK_MEMBERS: FamilyMember[] = [
  {
    id: 'P03',
    name: '김하늘',
    relation: '딸',
    birth_year: 1996,
    role: 'owner',
    thumbnail_url: '/media-files/profile_P03.jpg',
    joined_at: '2026-06-02',
    asset_count: 14,
    memory_count: 2,
    verified_count: 6,
    private_request: false,
  },
  {
    id: 'P01',
    name: '김민수',
    relation: '아빠',
    birth_year: 1970,
    role: 'contributor',
    thumbnail_url: '/media-files/profile_P01.jpg',
    joined_at: '2026-06-04',
    asset_count: 9,
    memory_count: 2,
    verified_count: 5,
    private_request: false,
  },
  {
    id: 'P02',
    name: '박서연',
    relation: '엄마',
    birth_year: 1973,
    role: 'contributor',
    thumbnail_url: '/media-files/profile_P02.jpg',
    joined_at: '2026-06-04',
    asset_count: 3,
    memory_count: 2,
    verified_count: 4,
    private_request: false,
  },
  {
    id: 'P05',
    name: '이정자',
    relation: '할머니',
    birth_year: 1940,
    role: 'contributor',
    thumbnail_url: '/media-files/profile_P05.jpg',
    joined_at: '2026-06-11',
    asset_count: 0,
    memory_count: 1,
    verified_count: 2,
    private_request: false,
  },
  {
    id: 'P04',
    name: '김지우',
    relation: '아들',
    birth_year: 2000,
    role: 'viewer',
    thumbnail_url: '/media-files/profile_P04.jpg',
    joined_at: '2026-06-05',
    asset_count: 2,
    memory_count: 1,
    verified_count: 1,
    private_request: false,
  },
  {
    id: 'P07',
    name: '이준호',
    relation: '연인',
    birth_year: 1994,
    role: 'viewer',
    thumbnail_url: null,
    joined_at: '2026-07-01',
    asset_count: 0,
    memory_count: 0,
    verified_count: 0,
    private_request: false,
  },
  {
    id: 'P06',
    name: '최민지',
    relation: '친구',
    birth_year: 1996,
    role: 'invited',
    thumbnail_url: null,
    joined_at: null,
    asset_count: 0,
    memory_count: 0,
    verified_count: 0,
    // 친구는 가족 아카이브 전체 열람 대상이 아니라는 전제
    private_request: true,
  },
]

export const MOCK_INVITE = {
  space_name: '김민수·박서연 가족',
  link: 'https://homestory.lge.com/join/HS-4F2K-98QD',
  code: 'HS-4F2K-98QD',
  expires_in_hours: 72,
}

/** 기록 단위 공개 범위 — Asset 단위로 소유자와 범위를 따로 둔다 */
export interface AssetScope {
  id: string
  label: string
  owner_id: string
  owner_name: string
  visibility: Visibility
  /** partial일 때 열람 가능한 인물 */
  allowed_ids: string[]
  media_count: number
}

export const MOCK_ASSET_SCOPE: AssetScope[] = [
  {
    id: 'E01',
    label: '1998 부산 가족여행',
    owner_id: 'P01',
    owner_name: '김민수',
    visibility: 'family',
    allowed_ids: [],
    media_count: 4,
  },
  {
    id: 'E04',
    label: '2010 할머니 칠순잔치',
    owner_id: 'P02',
    owner_name: '박서연',
    visibility: 'family',
    allowed_ids: [],
    media_count: 3,
  },
  {
    id: 'E05',
    label: '2015 하늘 고등학교 졸업식',
    owner_id: 'P03',
    owner_name: '김하늘',
    visibility: 'partial',
    allowed_ids: ['P01', 'P02', 'P03', 'P04'],
    media_count: 3,
  },
  {
    id: 'E07',
    label: '2021 하늘 결혼식',
    owner_id: 'P03',
    owner_name: '김하늘',
    visibility: 'family',
    allowed_ids: [],
    media_count: 5,
  },
  {
    id: 'V04',
    label: '아빠 인터뷰 음성 · 캠코더 이야기',
    owner_id: 'P01',
    owner_name: '김민수',
    visibility: 'private',
    allowed_ids: ['P01'],
    media_count: 1,
  },
]

/** 원본 하나를 지우면 함께 사라져야 하는 파생물 (기획안 08장 삭제 전파) */
export const MOCK_DELETE_CASCADE = {
  target: 'E01_002 · 아버지가 캠코더로 하늘을 촬영하는 장면',
  derived: [
    { label: '썸네일 1개', detail: 'thumb_E01_002.jpg' },
    { label: 'Memory Live 1편', detail: '1998 부산 가족여행 · 3번째 장면' },
    { label: 'Memory Film 장면 1개', detail: '30초 버전 2번째 컷' },
    { label: '그래프 엣지 4개', detail: 'CAPTURED_DURING · TAKEN_AT · DEPICTS ×2' },
    { label: '검색 인덱스', detail: '장면 설명 임베딩 1건' },
  ],
}
