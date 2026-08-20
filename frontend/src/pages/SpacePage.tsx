/**
 * 가족 공간 (기획안 02장 CORE · COLLECT · Family Space)
 *
 * 기존 앱에는 "지금 쓰는 사람이 누구인가"라는 개념이 없어서, 인터뷰 답변이
 * 실제로 누구의 기억인지 화면에서 보장되지 않았다. 기획안 08장의 귀속·동의
 * 원칙을 지키려면 이 화면이 먼저 있어야 한다.
 *
 * 구성원은 그래프의 인물 노드 그대로다. 역할과 동의가 그 노드에 얹혀 있어서
 * "사진 속 그 사람"과 "이 서비스를 쓰는 사람"이 갈라지지 않는다.
 *
 * 사용자 전환 카드를 이 화면에서 뺐다. 사이드바에 항상 떠 있는 전환기와 같은
 * 일을 하는데, 두 곳에 두면 어느 쪽이 진짜인지 헷갈린다. 여기서는 구성원 줄에
 * "사용 중" 표시만 남긴다.
 *
 * 자리표시 QR도 뺐다. 실제 QR 인코딩이 아니라 난수 격자였고, 스캔되지 않는 QR은
 * 화면에서 거짓말을 한다. 대신 초대 코드를 크게 적어 TV 화면과 같은 것을 보게 한다.
 *
 * 남은 교체 지점: 현재 사용자 -> 로그인 세션 (지금은 화면에서 고른다)
 */

import { useEffect, useState } from 'react'
import {
  FamilyInvite,
  FamilyRole,
  FamilySpace,
  createInvite,
  getFamilySpace,
  inviteLink,
  mediaUrl,
  updateMember,
} from '../lib/api'
import { ROLE_DESC, ROLE_LABEL, ROLE_ORDER } from '../lib/familyLabels'
import { useCurrentUser } from '../lib/currentUser'
import { Page, PageHeader } from '../components/Page'

/**
 * 서버가 403과 함께 보내는 이유를 뽑아낸다.
 * fetchJSON이 "API Error 403: {\"detail\":\"...\"}" 모양으로 던진다.
 */
function readDetail(error: unknown, fallback: string): string {
  const message = error instanceof Error ? error.message : String(error)
  const match = message.match(/"detail"\s*:\s*"([^"]+)"/)
  return match ? match[1] : fallback
}

export default function SpacePage() {
  const { current, reload: reloadMembers } = useCurrentUser()
  const [space, setSpace] = useState<FamilySpace | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const [invite, setInvite] = useState<FamilyInvite | null>(null)
  // 역할 가드에 막히면 이유를 화면에 남긴다. 조용히 실패하면 사용자는
  // 자기가 뭘 못 하는지 모른다 (backend/services/permissions.py).
  const [error, setError] = useState<string | null>(null)

  const load = () =>
    getFamilySpace()
      .then((data) => {
        setSpace(data)
        // 살아 있는 초대가 있으면 가장 최근 것을 보여준다
        setInvite(data.invites[data.invites.length - 1] || null)
      })
      .catch(console.error)
      .finally(() => setLoading(false))

  useEffect(() => {
    load()
  }, [])

  const changeRole = async (personId: string, role: FamilyRole) => {
    setBusy(personId)
    setError(null)
    try {
      await updateMember(personId, { role })
      await load()
      // 사이드바의 사용자 목록도 함께 바뀐다 (초대 대기는 목록에서 빠진다)
      reloadMembers()
    } catch (e) {
      console.error(e)
      setError(readDetail(e, '역할을 바꾸지 못했습니다.'))
    } finally {
      setBusy(null)
    }
  }

  const issueInvite = async (personId?: string) => {
    setBusy(personId || 'invite')
    setError(null)
    try {
      const created = await createInvite(personId)
      setInvite(created)
      await load()
      reloadMembers()
    } catch (e) {
      console.error(e)
      setError(readDetail(e, '초대 링크를 만들지 못했습니다.'))
    } finally {
      setBusy(null)
    }
  }

  const copy = async () => {
    if (!invite) return
    try {
      await navigator.clipboard.writeText(inviteLink(invite))
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1600)
    } catch {
      setCopied(false)
    }
  }

  if (loading || !space) {
    return (
      <Page width={900}>
        <p className="t-caption">불러오는 중…</p>
      </Page>
    )
  }

  const members = space.members
  const totalAssets = space.ownership.reduce((sum, o) => sum + o.count, 0) || 1
  const joined = members.filter((m) => m.role !== 'invited').length
  const pendingCount = members.filter((m) => m.role === 'invited').length

  return (
    <Page width={900}>
      <PageHeader
        eyebrow="Family Space"
        title={space.space_name}
        lead={
          '참여 ' +
          joined +
          '명 · 초대 대기 ' +
          pendingCount +
          '명 · 남기는 기억과 확인 기록은 지금 사용 중인 사람 이름으로 저장됩니다.'
        }
      />

      <div className="surface mt-10 flex flex-wrap gap-8 p-7">
        <div className="min-w-0 flex-[1_1_320px]">
          <p className="t-eyebrow m-0 mb-2.5 text-ink-300">
            {invite ? '초대 링크 · ' + invite.expires_in_hours + '시간 뒤 만료' : '초대 링크'}
          </p>

          {invite ? (
            <>
              <div className="flex min-w-0 flex-wrap gap-2">
                <input
                  readOnly
                  value={inviteLink(invite)}
                  className="field field-sm min-w-0 flex-[1_1_180px] bg-ink-50 text-ink-500"
                />
                <button onClick={copy} className="btn-quiet px-4 py-0 text-[13px]">
                  {copied ? '복사됨' : '링크 복사'}
                </button>
              </div>
              <p className="t-caption mt-3.5">
                휴대폰에서 링크를 열면 사진 업로드와 음성 인터뷰를 바로 할 수 있습니다.
              </p>
            </>
          ) : (
            <>
              <p className="t-body-sm m-0 text-ink-400">
                아직 살아 있는 초대가 없습니다. 링크를 만들면 72시간 동안 쓸 수 있습니다.
              </p>
              <button
                onClick={() => issueInvite()}
                disabled={busy === 'invite'}
                className="btn-primary mt-4 disabled:opacity-40"
              >
                {busy === 'invite' ? '만드는 중…' : '초대 링크 만들기'}
              </button>
            </>
          )}
        </div>

        {invite && (
          <div className="min-w-0 flex-[0_1_200px]">
            <p className="t-eyebrow m-0 mb-2.5 text-ink-300">참여 코드</p>
            <p className="t-mono m-0 text-xl tracking-[0.08em] text-ink-900">{invite.code}</p>
            <p className="t-caption mt-2.5">TV 화면에서도 같은 코드를 보여줍니다.</p>
            <button
              onClick={() => issueInvite()}
              disabled={busy === 'invite'}
              className="btn-link mt-3 px-0"
            >
              새 코드 만들기
            </button>
          </div>
        )}
      </div>

      {/* 공개 범위가 말뿐이 아님을 숫자로 보여준다 */}
      <p className="t-caption mt-4">
        지금 사용 중인 {current?.name ?? '사람'}에게 보이는 기록 {space.visibility.visible}개
        {space.visibility.hidden > 0 && ' · 열람 범위 밖 ' + space.visibility.hidden + '개'}
      </p>

      {error && (
        <p className="t-body-sm mt-4" style={{ color: 'var(--critical-ink)' }}>
          {error}
        </p>
      )}

      <div className="mt-10">
        <p className="t-eyebrow m-0 mb-3">구성원과 역할</p>
        <div className="rule-strong">
          {members.map((m) => {
            const role = m.role
            const pending = role === 'invited'

            return (
              <div
                key={m.id}
                className="flex items-start gap-4 px-1 py-5"
                style={{ borderBottom: '1px solid var(--border)' }}
              >
                {m.thumbnail_url ? (
                  <img
                    src={mediaUrl(m.thumbnail_url)}
                    alt=""
                    className="h-10 w-10 shrink-0 rounded-full bg-ink-50 object-cover"
                  />
                ) : (
                  <span
                    className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full
                               bg-ink-50 text-sm text-ink-300"
                  >
                    {m.name.slice(0, 1)}
                  </span>
                )}

                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-base font-semibold text-ink-900">{m.name}</span>
                    <span className="t-caption text-ink-300">
                      {m.relation}
                      {m.birth_year ? ' · ' + m.birth_year + '년생' : ''}
                    </span>
                    {current?.id === m.id && (
                      <span
                        className="pill text-[10px] font-normal"
                        style={{ background: 'var(--accent-soft)', color: 'var(--accent-ink)' }}
                      >
                        사용 중
                      </span>
                    )}
                    {m.private_request && (
                      <span className="pill bg-ink-50 text-[10px] font-normal text-ink-400">
                        열람 범위 제한 요청
                      </span>
                    )}
                  </div>

                  <p className="t-caption m-0 mt-[5px]">
                    {pending
                      ? '초대 링크를 보냈습니다. 아직 참여하지 않았습니다.'
                      : (m.joined_at ? m.joined_at + ' 참여 · ' : '') +
                        '기록 ' +
                        m.asset_count +
                        '개 · 기억 ' +
                        m.memory_count +
                        '개 · 확인 ' +
                        m.verified_count +
                        '건'}
                  </p>
                  <p className="t-caption m-0 mt-[3px] text-ink-300">{ROLE_DESC[role]}</p>
                </div>

                <div className="flex shrink-0 flex-col items-end gap-1.5">
                  <select
                    value={role}
                    disabled={busy === m.id}
                    onChange={(e) => changeRole(m.id, e.target.value as FamilyRole)}
                    className="field field-inline"
                  >
                    {ROLE_ORDER.map((r) => (
                      <option key={r} value={r}>
                        {ROLE_LABEL[r]}
                      </option>
                    ))}
                  </select>

                  {pending && (
                    <button
                      onClick={() => issueInvite(m.id)}
                      disabled={busy === m.id}
                      className="btn-quiet px-2.5 py-[5px] text-[11px] disabled:opacity-50"
                    >
                      {busy === m.id ? '만드는 중…' : '초대 링크 새로 보내기'}
                    </button>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      </div>

      <div className="mt-10">
        <p className="t-eyebrow m-0 mb-1">누가 모았나</p>
        <p className="t-caption m-0 mb-4">
          기록은 올린 사람의 것입니다. 공개 범위는 공개 · 동의 화면에서 각자 정합니다.
        </p>

        {space.ownership.length === 0 && (
          <p className="t-body-sm m-0 text-ink-300">아직 올라온 기록이 없습니다.</p>
        )}

        {space.ownership.map((o) => (
          <div key={o.id ?? 'unowned'} className="flex items-center gap-4 py-2.5">
            <span className="w-[76px] shrink-0 text-sm text-ink-700">{o.name}</span>
            <div className="h-1.5 flex-1 bg-ink-50">
              <div
                className="h-1.5"
                style={{
                  // 소유자가 정해지지 않은 기록은 강조하지 않는다 (자랑할 것이 아니다)
                  background: o.id ? 'var(--accent)' : 'var(--ink-200)',
                  width: (o.count / totalAssets) * 100 + '%',
                }}
              />
            </div>
            <span className="t-mono w-11 shrink-0 text-right text-xs text-ink-300">
              {o.count}개
            </span>
          </div>
        ))}
      </div>

      <p className="t-body-sm mt-10 rounded-lg bg-ink-50 px-6 py-5">
        가족 데이터는 기본 비공개입니다. 초대받지 않은 사람은 어떤 기록도 볼 수 없습니다.
      </p>
    </Page>
  )
}
