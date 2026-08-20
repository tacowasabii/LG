/**
 * 초대 참여 (기획안 02장 CORE · COLLECT · Family Space)
 *
 * 초대 링크가 실제로 도착하는 화면이다. 그전까지 초대는 발급만 됐고, 링크는
 * 존재하지 않는 도메인을 가리켰다 — 눌러도 열리지 않는 링크는 화면에서
 * 거짓말을 한다.
 *
 * 두 갈래를 받는다.
 *   지목된 초대   가족 관리자가 "누구를 초대한다"고 정한 경우. 이름을 다시 묻지
 *                 않는다. 물으면 이미 그래프에 있는 사람이 중복으로 생긴다.
 *   일반 초대     이미 구성원이면 자기 이름을 고르고, 처음이면 이름·관계를 적는다.
 *
 * 참여하면 그 사람이 "지금 쓰는 사람"이 된다. 다음 화면은 온보딩이다 —
 * 초대의 목적이 각자의 기록을 모으는 것이므로 업로드·인터뷰로 바로 이어 준다.
 */

import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { FamilyMember, InviteCheck, checkInvite, getFamilySpace, joinFamily } from '../lib/api'
import { useCurrentUser } from '../lib/currentUser'
import { Page, PageHeader } from '../components/Page'

/** 서버가 보내는 이유를 그대로 화면에 쓴다 */
function readDetail(error: unknown, fallback: string): string {
  const message = error instanceof Error ? error.message : String(error)
  const match = message.match(/"detail"\s*:\s*"([^"]+)"/)
  return match ? match[1] : fallback
}

export default function JoinPage() {
  const { code = '' } = useParams()
  const navigate = useNavigate()
  const { setCurrentId, reload } = useCurrentUser()

  const [invite, setInvite] = useState<InviteCheck | null>(null)
  const [members, setMembers] = useState<FamilyMember[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [joining, setJoining] = useState(false)
  const [joined, setJoined] = useState<FamilyMember | null>(null)

  // 일반 초대에서 누가 들어오는지 — 기존 구성원을 고르거나 새로 적는다
  const [pickedId, setPickedId] = useState('')
  const [name, setName] = useState('')
  const [relation, setRelation] = useState('')

  useEffect(() => {
    let alive = true
    checkInvite(code)
      .then((found) => {
        if (!alive) return
        setInvite(found)
        // 지목된 초대는 상대를 고를 필요가 없다
        if (!found.person_id) return getFamilySpace().then((space) => {
          if (alive) setMembers(space.members)
        })
      })
      .catch((e) => {
        if (alive) setError(readDetail(e, '초대를 확인할 수 없습니다.'))
      })
      .finally(() => {
        if (alive) setLoading(false)
      })
    return () => {
      alive = false
    }
  }, [code])

  const submit = async () => {
    setJoining(true)
    setError(null)
    try {
      const result = await joinFamily(code, {
        person_id: pickedId || undefined,
        name: pickedId ? undefined : name.trim() || undefined,
        relation: pickedId ? undefined : relation.trim() || undefined,
      })
      setJoined(result.member)
      // 들어온 사람이 지금 쓰는 사람이 된다 (기억의 귀속이 여기서 갈린다)
      setCurrentId(result.member.id)
      reload()
    } catch (e) {
      setError(readDetail(e, '참여하지 못했습니다.'))
    } finally {
      setJoining(false)
    }
  }

  if (loading) {
    return (
      <Page width={720}>
        <p className="t-caption">초대를 확인하는 중…</p>
      </Page>
    )
  }

  // 코드가 죽었으면 폼을 보여주지 않는다. 적게 만들고 실패하는 것보다 낫다.
  if (!invite) {
    return (
      <Page width={720}>
        <PageHeader
          eyebrow="Family Space"
          title="쓸 수 없는 초대입니다"
          lead={error ?? '만료됐거나 이미 사용된 코드입니다.'}
        />
        <p className="t-body-sm mt-8">
          초대는 72시간 동안 살아 있고 한 번 쓰면 소진됩니다. 가족 관리자에게 새 링크를
          받아 주세요.
        </p>
        <button onClick={() => navigate('/')} className="btn-quiet mt-6">
          홈으로
        </button>
      </Page>
    )
  }

  if (joined) {
    return (
      <Page width={720}>
        <PageHeader
          eyebrow="Family Space"
          title={joined.name + '님, 들어왔습니다'}
          lead={
            invite.space_name +
            '의 기록자로 참여했습니다. 올리는 기록과 남기는 기억은 모두 이 이름으로 귀속됩니다.'
          }
        />
        <div className="mt-8 flex flex-wrap gap-3">
          <button onClick={() => navigate('/collect')} className="btn-primary">
            기록 올리고 첫 질문에 답하기
          </button>
          <button onClick={() => navigate('/interview')} className="btn-quiet">
            AI 인터뷰로 바로 가기
          </button>
        </div>
      </Page>
    )
  }

  const canSubmit = Boolean(invite.person_id || pickedId || name.trim())

  return (
    <Page width={720}>
      <PageHeader
        eyebrow="Family Space"
        title={invite.space_name + '에 초대받았습니다'}
        lead="참여하면 사진·영상·음성을 올리고, AI 인터뷰로 기억을 남길 수 있습니다. 가족 데이터는 기본 비공개이고, 기록마다 공개 범위를 정합니다."
      />

      <div className="surface mt-8 p-7">
        <p className="t-eyebrow m-0 mb-2.5 text-ink-300">참여 코드</p>
        <p className="t-mono m-0 text-xl tracking-[0.08em] text-ink-900">{invite.code}</p>

        {invite.person_id ? (
          <p className="t-body-sm mt-5">
            <span className="text-ink-900">{invite.person_name ?? '초대받은 분'}</span>
            으로 참여합니다.
          </p>
        ) : (
          <div className="mt-6">
            {members.length > 0 && (
              <>
                <p className="t-eyebrow m-0 mb-2.5 text-ink-300">이미 구성원이라면</p>
                <select
                  value={pickedId}
                  onChange={(e) => setPickedId(e.target.value)}
                  className="field field-inline"
                >
                  <option value="">처음 참여합니다</option>
                  {members.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.name}
                      {m.relation ? ' · ' + m.relation : ''}
                    </option>
                  ))}
                </select>
              </>
            )}

            {!pickedId && (
              <div className="mt-6 flex flex-wrap gap-3">
                <input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="이름"
                  className="field min-w-0 flex-[1_1_180px]"
                />
                <input
                  value={relation}
                  onChange={(e) => setRelation(e.target.value)}
                  placeholder="관계 (아빠, 엄마, 할머니…)"
                  className="field min-w-0 flex-[1_1_180px]"
                />
              </div>
            )}
          </div>
        )}

        <button
          onClick={submit}
          disabled={joining || !canSubmit}
          className="btn-primary mt-7 disabled:opacity-40"
        >
          {joining ? '참여하는 중…' : '가족 공간에 참여하기'}
        </button>

        {error && (
          <p className="t-body-sm mt-4 mb-0" style={{ color: 'var(--critical-ink)' }}>
            {error}
          </p>
        )}
      </div>

      <p className="t-caption mt-4">
        이 코드는 {new Date(invite.expires_at).toLocaleString('ko-KR')}에 만료됩니다.
      </p>
    </Page>
  )
}
