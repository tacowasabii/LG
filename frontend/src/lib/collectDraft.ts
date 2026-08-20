/**
 * 모으기에서 하던 일을 탭을 옮겨도 붙잡아 둔다
 *
 * 올리기와 저장 사이에는 사람이 손으로 만든 것이 쌓여 있다 — 사진마다 지목한
 * 사람, AI 초안을 고친 제목·날짜·장소·설명, 되물음에 "아니요"라고 답한 후보.
 * 그런데 모으기 화면은 라우트가 바뀌면 언마운트되고, 그 상태가 전부 컴포넌트
 * 안에만 있었다. 사진을 올린 뒤 사진첩을 잠깐 열어 보고 돌아오면 초안이
 * 사라져 있었다. 서버에는 파일만 올라간 채라, 사용자에게는 "올린 사진이 미분류로
 * 떨어졌고 처음부터 다시 해야 하는" 상태로 보였다.
 *
 * 그래서 저장하기 전의 상태를 여기 둔다. sessionStorage를 쓰는 이유는 이것이
 * 지금 앉아서 하는 일이기 때문이다 — 새로고침과 탭 이동은 견디되, 브라우저를
 * 닫고 다음 날 열었을 때 몇 달 전 초안이 되살아나지는 않는다.
 *
 * 담지 않는 것: 올리는 중·초안 쓰는 중·저장 중 같은 진행 표시와 오류 문구.
 * 그 요청은 화면이 사라진 순간 이미 끝났거나 끊겼으므로, 되살리면 영원히 도는
 * 스피너가 된다.
 */

import { MediaUploadResult, MemoryDraft, normalizeDraft } from './api'

export interface DraftForm {
  title: string
  date_start: string
  /** 그래프에 있는 장소를 그대로 쓰는 경우. 이름을 고치면 비워진다 */
  place_id: string | null
  place_name: string
  description: string
  person_ids: string[]
}

/** 묶음 하나 — 초안 + 편집 중인 값 + 그 결과 */
export interface Group {
  draft: MemoryDraft
  form: DraftForm
  /** 인물 후보 중 "아니요"로 넘긴 사람 (다시 묻지 않는다) */
  dismissed: string[]
  /** 만들어진 추억 (여기까지 오면 이미 가족 공간에 게시된 상태다) */
  created?: { id: string; title: string }
  /** 기존 추억에 붙인 경우 */
  attached?: { id: string; title: string }
}

/** 모으기 화면이 저장 전까지 들고 있는 것 전부 */
export interface CollectDraft {
  results: MediaUploadResult[]
  /** 기록별로 지목된 사람 */
  personTags: Record<string, string[]>
  groups: Group[]
  /** AI가 갈랐는가 */
  grouped: boolean
  /** 지금 전부 하나로 합쳐 놓은 상태인가 */
  merged: boolean
}

const STORAGE_KEY = 'homestory.collect'

export const EMPTY_COLLECT_DRAFT: CollectDraft = {
  results: [],
  personTags: {},
  groups: [],
  grouped: false,
  merged: false,
}

/**
 * 저장해 둔 것을 읽는다. 읽을 수 없으면 빈 상태로 시작한다.
 *
 * 저장소에 남은 모양은 지금 코드보다 오래된 배포가 쓴 것일 수 있다. 초안은
 * 서버 응답과 같은 길로 다시 정규화해서(normalizeDraft) 배열이 빠진 채로
 * 화면에 들어가지 않게 한다 — 그리는 중에 예외가 나면 모으기 화면 전체가
 * 사라지고, 되살리려고 만든 장치가 오히려 화면을 죽인다.
 */
export function loadCollectDraft(): CollectDraft {
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY)
    if (!raw) return EMPTY_COLLECT_DRAFT
    const parsed = JSON.parse(raw) as Partial<CollectDraft>
    const groups = Array.isArray(parsed.groups) ? parsed.groups : []
    return {
      results: Array.isArray(parsed.results) ? parsed.results : [],
      personTags:
        parsed.personTags && typeof parsed.personTags === 'object' ? parsed.personTags : {},
      groups: groups
        .filter((g): g is Group => !!g && typeof g === 'object' && !!g.form)
        .map((g) => ({
          ...g,
          draft: normalizeDraft(g.draft),
          dismissed: Array.isArray(g.dismissed) ? g.dismissed : [],
          form: { ...g.form, person_ids: Array.isArray(g.form.person_ids) ? g.form.person_ids : [] },
        })),
      grouped: !!parsed.grouped,
      merged: !!parsed.merged,
    }
  } catch (e) {
    console.error('[collect] 저장해 둔 초안을 읽지 못했습니다', e)
    return EMPTY_COLLECT_DRAFT
  }
}

/** 아무것도 올리지 않은 상태는 굳이 저장하지 않는다 (비운 것과 같다) */
export function saveCollectDraft(draft: CollectDraft): void {
  try {
    if (draft.results.length === 0 && draft.groups.length === 0) {
      window.sessionStorage.removeItem(STORAGE_KEY)
      return
    }
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(draft))
  } catch (e) {
    // 용량을 넘겨도 화면은 계속 돌아야 한다. 못 붙잡아 두는 것이 최악이지만
    // 저장 중에 터져서 편집이 멈추는 것보다는 낫다.
    console.error('[collect] 초안을 저장하지 못했습니다', e)
  }
}

export function clearCollectDraft(): void {
  try {
    window.sessionStorage.removeItem(STORAGE_KEY)
  } catch (e) {
    console.error('[collect] 초안을 비우지 못했습니다', e)
  }
}
