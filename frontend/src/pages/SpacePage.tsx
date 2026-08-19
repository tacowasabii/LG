/**
 * 가족 공간 (기획안 02장 CORE · COLLECT · Family Space)
 *
 * 기존 앱에는 "지금 쓰는 사람이 누구인가"라는 개념이 없어서, 인터뷰 답변이
 * 실제로 누구의 기억인지 화면에서 보장되지 않았다. 기획안 08장의 귀속·동의
 * 원칙을 지키려면 이 화면이 먼저 있어야 한다.
 *
 * 사용자 전환 카드를 이 화면에서 뺐다. 사이드바에 항상 떠 있는 전환기와 같은
 * 일을 하는데, 두 곳에 두면 어느 쪽이 진짜인지 헷갈린다. 여기서는 구성원 줄에
 * "사용 중" 표시만 남긴다.
 *
 * 자리표시 QR도 뺐다. 실제 QR 인코딩이 아니라 난수 격자였고, 스캔되지 않는 QR은
 * 화면에서 거짓말을 한다. 대신 초대 코드를 크게 적어 TV 화면과 같은 것을 보게 한다.
 *
 * 실기능 개발 시 교체 지점:
 *   MOCK_MEMBERS   -> GET  /api/family/members
 *   역할 변경       -> PUT  /api/family/member/{id}/role
 *   초대 링크 발급  -> POST /api/family/invite
 *   현재 사용자     -> 로그인 세션
 */

import { useState } from 'react'
import { mediaUrl } from '../lib/api'
import { FamilyRole, MOCK_INVITE, MOCK_MEMBERS, ROLE_DESC, ROLE_LABEL } from '../mock/family'
import { useCurrentUser } from '../lib/currentUser'
import { Page, PageHeader } from '../components/Page'

const ROLE_ORDER: FamilyRole[] = ['owner', 'contributor', 'viewer', 'invited']

export default function SpacePage() {
  const { current } = useCurrentUser()
  const [roles, setRoles] = useState<Record<string, FamilyRole>>(
    MOCK_MEMBERS.reduce((acc, m) => ({ ...acc, [m.id]: m.role }), {}),
  )
  const [copied, setCopied] = useState(false)
  const [invited, setInvited] = useState<string[]>([])

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(MOCK_INVITE.link)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1600)
    } catch {
      setCopied(false)
    }
  }

  const totalAssets = MOCK_MEMBERS.reduce((sum, m) => sum + m.asset_count, 0)
  const joined = MOCK_MEMBERS.filter((m) => m.role !== 'invited').length
  const pendingCount = MOCK_MEMBERS.filter((m) => m.role === 'invited').length

  return (
    <Page width={900}>
      <PageHeader
        mock
        eyebrow="Family Space"
        title={MOCK_INVITE.space_name}
        lead={`참여 ${joined}명 · 초대 대기 ${pendingCount}명 · 남기는 기억과 확인 기록은 지금 사용 중인 사람 이름으로 저장됩니다.`}
      />

      <div className="surface mt-10 flex flex-wrap gap-8 p-7">
        <div className="min-w-0 flex-[1_1_320px]">
          <p className="t-eyebrow m-0 mb-2.5 text-ink-300">
            초대 링크 · {MOCK_INVITE.expires_in_hours}시간 뒤 만료
          </p>
          <div className="flex min-w-0 flex-wrap gap-2">
            <input
              readOnly
              value={MOCK_INVITE.link}
              className="field field-sm min-w-0 flex-[1_1_180px] bg-ink-50 text-ink-500"
            />
            <button onClick={copy} className="btn-quiet px-4 py-0 text-[13px]">
              {copied ? '복사됨' : '링크 복사'}
            </button>
          </div>
          <p className="t-caption mt-3.5">
            휴대폰에서 링크를 열면 사진 업로드와 음성 인터뷰를 바로 할 수 있습니다.
          </p>
        </div>

        <div className="min-w-0 flex-[0_1_200px]">
          <p className="t-eyebrow m-0 mb-2.5 text-ink-300">참여 코드</p>
          <p className="t-mono m-0 text-xl tracking-[0.08em] text-ink-900">{MOCK_INVITE.code}</p>
          <p className="t-caption mt-2.5">TV 화면에서도 같은 코드를 보여줍니다.</p>
        </div>
      </div>

      <div className="mt-10">
        <p className="t-eyebrow m-0 mb-3">구성원과 역할</p>
        <div className="rule-strong">
          {MOCK_MEMBERS.map((m) => {
            const role = roles[m.id]
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
                      {m.relation} · {m.birth_year}년생
                    </span>
                    {current.id === m.id && (
                      <span
                        className="pill text-[10px] font-normal"
                        style={{
                          background: 'var(--accent-soft)',
                          color: 'var(--accent-ink)',
                        }}
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
                      : `${m.joined_at} 참여 · 기록 ${m.asset_count}개 · 기억 ${m.memory_count}개 · 확인 ${m.verified_count}건`}
                  </p>
                  <p className="t-caption m-0 mt-[3px] text-ink-300">{ROLE_DESC[role]}</p>
                </div>

                <div className="flex shrink-0 flex-col items-end gap-1.5">
                  <select
                    value={role}
                    onChange={(e) =>
                      setRoles((prev) => ({ ...prev, [m.id]: e.target.value as FamilyRole }))
                    }
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
                      onClick={() => setInvited((prev) => [...prev, m.id])}
                      disabled={invited.includes(m.id)}
                      className="btn-quiet px-2.5 py-[5px] text-[11px] disabled:opacity-50"
                    >
                      {invited.includes(m.id) ? '보냈습니다' : '초대 다시 보내기'}
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
        {MOCK_MEMBERS.filter((m) => m.asset_count > 0).map((m) => (
          <div key={m.id} className="flex items-center gap-4 py-2.5">
            <span className="w-[60px] shrink-0 text-sm text-ink-700">{m.name}</span>
            <div className="h-1.5 flex-1 bg-ink-50">
              <div
                className="h-1.5"
                style={{
                  background: 'var(--accent)',
                  width: (m.asset_count / totalAssets) * 100 + '%',
                }}
              />
            </div>
            <span className="t-mono w-11 shrink-0 text-right text-xs text-ink-300">
              {m.asset_count}개
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
