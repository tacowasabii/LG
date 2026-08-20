/**
 * 공개 · 동의 (기획안 08장 TRUST & ETHICS)
 *
 * 기획안은 "개인정보 보호는 부가기능이 아니라 사업 지속 가능성"이라고 못 박았고,
 * 심사 예상 질문에도 딥페이크 거부감과 오귀속이 들어 있다. 말로만 답하지 않도록
 * 다섯 가지 원칙(인물 동의 · Asset 권한 · 출처 보존 · AI 라벨 · 삭제 이관)을
 * 각각 조작 가능한 화면으로 만들었다.
 *
 * 여기서 바꾼 값은 저장만 되는 게 아니라 실제로 가려진다. 서버가 목록·검색·
 * 근거에서 그 사람이 볼 수 없는 원본을 빼기 때문이다
 * (backend/services/visibility.py). 설정만 저장하고 보여 주기는 그대로면
 * 동의는 형식이 된다.
 */

import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  CascadePreview,
  FamilyMember,
  MediaItem,
  Visibility,
  deleteMedia,
  getDeleteCascade,
  getFamilySpace,
  getMediaList,
  mediaUrl,
  setMediaVisibility,
  updateMember,
} from '../lib/api'
import {
  VISIBILITIES,
  VISIBILITY_DESC,
  VISIBILITY_LABEL,
} from '../lib/familyLabels'
import { useCurrentUser } from '../lib/currentUser'
import { invalidateEvents, invalidateVoiceClips } from '../lib/useGraphData'
import { Page, PageHeader } from '../components/Page'

const AI_LABELS = [
  {
    label: '움직임 효과 표시',
    detail: '패닝·줌·미세 배경 움직임이 적용된 장면에 화면 라벨을 붙입니다.',
  },
  {
    label: '내레이션 표시',
    detail: 'AI가 쓴 자막·내레이션임을 함께 밝힙니다.',
  },
  {
    label: '보정 표시',
    detail: '색·해상도 보정이 들어간 원본에 표시를 남깁니다.',
  },
]

/** 서버가 403과 함께 보내는 이유를 뽑아낸다 */
function readDetail(error: unknown, fallback: string): string {
  const message = error instanceof Error ? error.message : String(error)
  const match = message.match(/"detail"\s*:\s*"([^"]+)"/)
  return match ? match[1] : fallback
}

export default function PrivacyPage() {
  const { current, members, reload: reloadMembers } = useCurrentUser()
  const [media, setMedia] = useState<MediaItem[]>([])
  const [space, setSpace] = useState<{ visible: number; hidden: number; total: number } | null>(
    null,
  )
  const [scopes, setScopes] = useState<Record<string, Visibility>>({})
  const [busy, setBusy] = useState<string | null>(null)
  const [cascade, setCascade] = useState<CascadePreview | null>(null)
  const [cascadeFor, setCascadeFor] = useState<string | null>(null)
  // 삭제는 되돌릴 수 없다. 한 번 더 누르게 한다 (확인을 요구한 id)
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null)
  const [deleted, setDeleted] = useState<string | null>(null)
  // 공개 범위는 올린 사람과 가족 관리자만 바꿀 수 있다. 막히면 이유를 보여준다.
  const [error, setError] = useState<string | null>(null)

  const load = async () => {
    const [items, familySpace] = await Promise.all([getMediaList(), getFamilySpace()])
    setMedia(items)
    setSpace({
      visible: familySpace.visibility.visible,
      hidden: familySpace.visibility.hidden,
      total: familySpace.visibility.media_total,
    })
  }

  useEffect(() => {
    load().catch(console.error)
  }, [current?.id])

  const changeScope = async (mediaId: string, visibility: Visibility) => {
    setBusy(mediaId)
    setError(null)
    setScopes((prev) => ({ ...prev, [mediaId]: visibility }))
    try {
      // 비공개·부분공개로 바꿀 때 소유자를 함께 남긴다 —
      // 소유자가 없으면 아무도 볼 수 없는 기록이 된다
      await setMediaVisibility(mediaId, visibility, undefined, current?.id ?? null)
      // 가려진 기록은 홈·지도·TV의 개수와 썸네일에서도 빠져야 한다
      invalidateEvents()
      invalidateVoiceClips()
      await load()
    } catch (e) {
      console.error(e)
      // 실패했으므로 화면의 선택도 되돌린다
      setScopes((prev) => {
        const next = { ...prev }
        delete next[mediaId]
        return next
      })
      setError(readDetail(e, '공개 범위를 바꾸지 못했습니다.'))
    } finally {
      setBusy(null)
    }
  }

  const togglePrivateRequest = async (member: FamilyMember) => {
    setBusy(member.id)
    setError(null)
    try {
      await updateMember(member.id, { private_request: !member.private_request })
      reloadMembers()
      invalidateEvents()
      await load()
    } catch (e) {
      console.error(e)
      setError(readDetail(e, '비공개 요청을 바꾸지 못했습니다.'))
    } finally {
      setBusy(null)
    }
  }

  const showCascade = async (mediaId: string) => {
    if (cascadeFor === mediaId) {
      setCascadeFor(null)
      setCascade(null)
      setConfirmDelete(null)
      return
    }
    setBusy(mediaId)
    setConfirmDelete(null)
    try {
      setCascade(await getDeleteCascade(mediaId))
      setCascadeFor(mediaId)
    } catch (e) {
      console.error(e)
      setError(readDetail(e, '삭제 영향을 불러오지 못했습니다.'))
    } finally {
      setBusy(null)
    }
  }

  /**
   * 원본을 실제로 지운다 (기획안 08장 "삭제·이관").
   *
   * 미리보기까지만 있으면 "지워진다"는 약속이 화면에서 증명되지 않는다. 서버가
   * 파일과 노드를 함께 지우고, 노드가 사라지면 그 원본을 가리키던 연결도 함께
   * 끊긴다. 가족이 남긴 기억 문장은 남는다 — 지우는 것은 원본이다.
   */
  const removeMedia = async (mediaId: string) => {
    const item = media.find((m) => m.id === mediaId)
    setBusy(mediaId)
    setError(null)
    try {
      await deleteMedia(mediaId)
      // 홈·지도·TV의 개수와 썸네일에서도 즉시 빠져야 한다
      invalidateEvents()
      invalidateVoiceClips()
      setCascadeFor(null)
      setCascade(null)
      setConfirmDelete(null)
      setDeleted(item?.original_filename || mediaId)
      await load()
    } catch (e) {
      console.error(e)
      setError(readDetail(e, '기록을 지우지 못했습니다.'))
    } finally {
      setBusy(null)
    }
  }

  // 사진이 많으므로 사건 대신 파일 단위로, 최근 것부터 보여준다
  const visibleMedia = media.slice(0, 12)

  return (
    <Page width={900}>
      <PageHeader
        eyebrow="Trust & Consent"
        title="공개 · 동의"
        lead="가족 기록은 기본 비공개입니다. 여기서 정한 범위는 목록·검색·답변 근거에서 실제로 지켜집니다."
      />

      {space && (
        <p className="t-caption mt-6">
          지금 사용 중인 {current?.name ?? '사람'}에게 보이는 기록 {space.visible}개 · 전체{' '}
          {space.total}개
          {space.hidden > 0 && ' · 열람 범위 밖 ' + space.hidden + '개'}
        </p>
      )}

      {error && (
        <p className="t-body-sm mt-4" style={{ color: 'var(--critical-ink)' }}>
          {error}
        </p>
      )}

      {deleted && (
        <p className="t-body-sm mt-4" style={{ color: 'var(--positive-ink)' }}>
          {deleted}을 지웠습니다. 원본 파일과 그래프 연결이 함께 사라졌습니다.
        </p>
      )}

      <div className="mt-10">
        <p className="t-eyebrow m-0 mb-3">공개 범위의 뜻</p>
        <div className="grid grid-cols-3 gap-3">
          {VISIBILITIES.map((v) => (
            <div
              key={v}
              className="rounded-lg p-5"
              style={{ background: 'var(--paper-pure)', border: '1px solid var(--border)' }}
            >
              <span className="block text-[15px] font-semibold text-ink-900">
                {VISIBILITY_LABEL[v]}
              </span>
              <span className="t-caption mt-1.5 block">{VISIBILITY_DESC[v]}</span>
            </div>
          ))}
        </div>
        <p className="t-caption mt-3">
          새 기록은 가족 전체로 들어옵니다. 올린 사람은 언제든 자기 기록의 범위를 좁힐 수
          있습니다.
        </p>
      </div>

      <div className="mt-10">
        <p className="t-eyebrow m-0 mb-1">기록별 공개 범위</p>
        <p className="t-caption m-0 mb-3">
          사진·영상·음성마다 따로 정합니다. 최근 올라온 {visibleMedia.length}개를 보여줍니다.
        </p>

        <div className="rule-strong">
          {visibleMedia.length === 0 && (
            <p className="t-body-sm py-6 text-ink-300">아직 올라온 기록이 없습니다.</p>
          )}

          {visibleMedia.map((item) => {
            const scope = scopes[item.id] || 'family'
            const owner = members.find((m) => m.id === item.speaker_id)

            return (
              <div key={item.id} style={{ borderBottom: '1px solid var(--border)' }}>
                <div className="flex items-center gap-5 px-1 py-4">
                  {item.media_type === 'photo' ? (
                    <img
                      src={mediaUrl(item.thumbnail_path || item.file_path)}
                      alt=""
                      className="h-11 w-14 shrink-0 rounded bg-ink-50 object-cover"
                    />
                  ) : (
                    <span
                      className="t-mono flex h-11 w-14 shrink-0 items-center justify-center
                                 rounded bg-ink-50 text-[10px] text-ink-300"
                    >
                      {item.media_type === 'audio' ? '음성' : '영상'}
                    </span>
                  )}

                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[15px] text-ink-900">
                      {item.original_filename || item.id}
                    </span>
                    <span className="t-caption mt-[3px] block">
                      {owner ? owner.name + ' 소유' : '소유자 미지정'}
                      {item.event_title ? ' · ' + item.event_title : ''}
                      {item.exif_date ? ' · ' + item.exif_date.slice(0, 10) : ''}
                    </span>
                  </span>

                  <select
                    value={scope}
                    disabled={busy === item.id}
                    onChange={(e) => changeScope(item.id, e.target.value as Visibility)}
                    className="field field-inline shrink-0"
                  >
                    {VISIBILITIES.map((v) => (
                      <option key={v} value={v}>
                        {VISIBILITY_LABEL[v]}
                      </option>
                    ))}
                  </select>

                  <button
                    onClick={() => showCascade(item.id)}
                    disabled={busy === item.id}
                    className="btn-quiet shrink-0 px-3 py-[6px] text-[11px]"
                  >
                    {cascadeFor === item.id ? '닫기' : '삭제 영향'}
                  </button>
                </div>

                {cascadeFor === item.id && cascade && (
                  <div
                    className="mb-4 ml-[76px] rounded-lg p-5"
                    style={{ background: 'var(--critical-soft)' }}
                  >
                    <p className="t-body-sm m-0" style={{ color: 'var(--critical-ink)' }}>
                      지울 원본 · {cascade.target}
                    </p>
                    {cascade.scene_description && (
                      <p
                        className="t-caption m-0 mt-1"
                        style={{ color: 'var(--critical-ink)', opacity: 0.75 }}
                      >
                        {cascade.scene_description}
                      </p>
                    )}
                    <p className="t-eyebrow mb-2 mt-4" style={{ color: 'var(--critical-ink)' }}>
                      함께 사라지는 것
                    </p>
                    {cascade.derived.map((d) => (
                      <div
                        key={d.label + d.detail}
                        className="flex justify-between gap-5 py-[7px]"
                        style={{ borderBottom: '1px solid rgba(194,84,42,0.18)' }}
                      >
                        <span className="t-body-sm" style={{ color: 'var(--critical-ink)' }}>
                          {d.label}
                        </span>
                        <span
                          className="t-mono text-[11px] opacity-70"
                          style={{ color: 'var(--critical-ink)' }}
                        >
                          {d.detail}
                        </span>
                      </div>
                    ))}
                    <p className="t-caption mt-3.5" style={{ color: 'var(--critical-ink)' }}>
                      가족이 남긴 기억 문장은 지워지지 않습니다. 원본과의 연결만 끊깁니다.
                    </p>

                    {/* 되돌릴 수 없는 일이라 한 번 더 묻는다 */}
                    <div className="mt-4 flex flex-wrap items-center gap-3">
                      {confirmDelete === item.id ? (
                        <>
                          <button
                            onClick={() => removeMedia(item.id)}
                            disabled={busy === item.id}
                            className="cursor-pointer rounded px-3.5 py-1.5 text-xs disabled:opacity-40"
                            style={{ background: 'var(--critical-ink)', color: 'var(--paper)' }}
                          >
                            {busy === item.id ? '지우는 중…' : '정말 지웁니다'}
                          </button>
                          <button
                            onClick={() => setConfirmDelete(null)}
                            disabled={busy === item.id}
                            className="btn-quiet px-3.5 py-1.5 text-xs"
                          >
                            취소
                          </button>
                          <span className="t-caption" style={{ color: 'var(--critical-ink)' }}>
                            원본 파일까지 지워집니다. 되돌릴 수 없습니다.
                          </span>
                        </>
                      ) : (
                        <button
                          onClick={() => setConfirmDelete(item.id)}
                          disabled={busy === item.id}
                          className="btn-quiet px-3.5 py-1.5 text-xs"
                          style={{ color: 'var(--critical-ink)' }}
                        >
                          이 원본 지우기
                        </button>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </div>

      <div className="mt-10">
        <p className="t-eyebrow m-0 mb-1">인물별 비공개 요청</p>
        <p className="t-caption m-0 mb-3">
          사진 속 인물이 원하면 그 사람이 등장하는 기록을 가족 공유에서 뺍니다. 원본은 지우지
          않고 올린 사람만 볼 수 있게 둡니다. 본인은 자기가 나온 기록을 그대로 봅니다.
        </p>

        <div style={{ borderTop: '1px solid var(--border)' }}>
          {members.map((m) => (
            <div
              key={m.id}
              className="flex items-center gap-3.5 px-1 py-3.5"
              style={{ borderBottom: '1px solid var(--border)' }}
            >
              {m.thumbnail_url ? (
                <img
                  src={mediaUrl(m.thumbnail_url)}
                  alt=""
                  className="h-8 w-8 rounded-full bg-ink-50 object-cover"
                />
              ) : (
                <span
                  className="flex h-8 w-8 items-center justify-center rounded-full
                             bg-ink-50 text-xs text-ink-300"
                >
                  {m.name.slice(0, 1)}
                </span>
              )}
              <span className="min-w-0 flex-1">
                <span className="text-sm text-ink-900">{m.name}</span>
                <span className="t-caption ml-2 text-ink-300">{m.relation}</span>
                <span className="t-caption mt-0.5 block">
                  {m.private_request ? '가족 공유에서 제외됨' : '가족 공유 허용'}
                </span>
              </span>
              <button
                onClick={() => togglePrivateRequest(m)}
                disabled={busy === m.id}
                className="cursor-pointer rounded px-3.5 py-1.5 text-xs disabled:opacity-40"
                style={
                  m.private_request
                    ? {
                        border: '1px solid var(--border-strong)',
                        background: 'var(--ink-50)',
                        color: 'var(--ink-700)',
                      }
                    : {
                        border: '1px solid var(--border)',
                        background: 'transparent',
                        color: 'var(--ink-500)',
                      }
                }
              >
                {m.private_request ? '비공개' : '공개'}
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* AI 라벨 — 끌 수 없다 */}
      <div className="mt-10">
        <p className="t-eyebrow m-0 mb-1">AI 생성 요소 표시</p>
        <p className="t-caption m-0 mb-3">
          제품 원칙이라 끌 수 없습니다. 무엇이 원본이고 무엇이 만들어진 것인지 항상 보입니다.
          Film 장면의 효과 목록은 신뢰도 리포트에서 허용 범위를 넘지 않는지 함께 검사합니다.
        </p>
        <div style={{ borderTop: '1px solid var(--border)' }}>
          {AI_LABELS.map((item) => (
            <div
              key={item.label}
              className="flex items-start gap-5 px-1 py-4"
              style={{ borderBottom: '1px solid var(--border)' }}
            >
              <span className="flex-1">
                <span className="block text-sm text-ink-900">{item.label}</span>
                <span className="t-caption mt-[3px] block">{item.detail}</span>
              </span>
              <span
                className="pill px-2.5 py-1 font-normal"
                style={{ background: 'var(--positive-soft)', color: 'var(--positive-ink)' }}
              >
                항상 켜짐
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* 목소리 정책 — 이 화면에서 유일하게 바꿀 수 없는 원칙 */}
      <div className="mt-10 rounded-lg px-7 py-6" style={{ background: 'var(--critical-soft)' }}>
        <p className="t-eyebrow m-0" style={{ color: 'var(--critical-ink)' }}>
          목소리 정책
        </p>
        <p className="t-body mt-3 max-w-[64ch]" style={{ color: 'var(--critical-ink)' }}>
          돌아가신 분의 목소리를 학습해 새로운 문장을 말하게 하지 않습니다. 남아 있는 음성은
          원본 구간과 출처를 표시해 그대로 재생하고, 음성이 없으면 중립적인 AI 내레이터를
          씁니다. 본인이 직접 남기는 목소리 기록은 명시적으로 동의한 경우에만 다룹니다.
        </p>
      </div>

      <div className="mt-10">
        <p className="t-eyebrow m-0 mb-1">이관 · 아카이브</p>
        <p className="t-caption m-0 mb-4">
          기록은 가족의 것입니다. 서비스를 그만 쓰더라도 원본과 관계, 이야기가 파일로 남습니다.
        </p>

        <div className="flex flex-wrap gap-2">
          <Link
            to="/export"
            className="btn-quiet px-[18px] py-2.5 text-[13px] no-underline hover:no-underline"
          >
            가족 아카이브 내보내기
          </Link>
          <Link
            to="/space"
            className="btn-quiet px-[18px] py-2.5 text-[13px] no-underline hover:no-underline"
          >
            가족 관리자 넘기기
          </Link>
        </div>
      </div>
    </Page>
  )
}
