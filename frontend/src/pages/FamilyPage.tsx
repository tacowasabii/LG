import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getPersons, createPerson, PersonData, mediaUrl } from '../lib/api'
import AudioClip from '../components/AudioClip'
import MockBadge from '../components/MockBadge'
import { Page, PageHeader } from '../components/Page'
import { MOCK_MEMBERS, ROLE_LABEL, ROLE_DESC } from '../mock/family'
import { MOCK_VOICE_CLIPS } from '../mock/voice'
import { MOCK_TIMELINE } from '../mock/timeline'

/**
 * 인물 (기획안 02장 People)
 *
 * 관계마다 다른 색을 주던 방식을 버렸다. 색을 관계에 배분하면 사람 수만큼 색이
 * 늘어나면서 정작 중요한 신호(누가 목소리를 남겼나, 누가 열람을 제한했나)가
 * 묻힌다. 관계는 이름 옆 강조색 캡션 하나로 충분하고, 나머지는 잉크 계조로 둔다.
 */
export default function FamilyPage() {
  const [persons, setPersons] = useState<PersonData[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [formData, setFormData] = useState({ name: '', relation: '', birth_year: '' })
  const [selectedPerson, setSelectedPerson] = useState<PersonData | null>(null)

  useEffect(() => {
    loadPersons()
  }, [])

  const loadPersons = async () => {
    try {
      const data = await getPersons()
      setPersons(data)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  const handleCreate = async () => {
    if (!formData.name.trim()) return
    try {
      await createPerson({
        name: formData.name,
        relation: formData.relation,
        birth_year: formData.birth_year ? parseInt(formData.birth_year) : undefined,
      })
      setFormData({ name: '', relation: '', birth_year: '' })
      setShowForm(false)
      loadPersons()
    } catch (e) {
      console.error(e)
    }
  }

  /** 가족 공간의 역할·동의 정보는 아직 목데이터에서 붙인다 (id는 그래프와 동일) */
  const memberInfo = (id: string) => MOCK_MEMBERS.find((m) => m.id === id)
  const clipsOf = (id: string) => MOCK_VOICE_CLIPS.filter((c) => c.speaker_id === id)
  const eventsOf = (id: string) => MOCK_TIMELINE.filter((e) => e.participant_ids.includes(id))

  if (loading) {
    return (
      <Page width={1040}>
        <p className="t-caption">불러오는 중…</p>
      </Page>
    )
  }

  const selectedInfo = selectedPerson ? memberInfo(selectedPerson.id) : undefined
  const selectedClips = selectedPerson ? clipsOf(selectedPerson.id) : []

  return (
    <Page width={1040}>
      <PageHeader
        eyebrow="People"
        title="인물"
        lead="Memory Graph에 등록된 사람들입니다. 가족·친구·연인 모두 포함됩니다."
        action={
          <button onClick={() => setShowForm((v) => !v)} className="btn-quiet">
            인물 추가
          </button>
        }
      />

      {showForm && (
        <div className="surface mt-8 p-6">
          <p className="t-eyebrow m-0 mb-4">인물 추가</p>
          <div className="grid grid-cols-3 gap-3">
            <input
              type="text"
              placeholder="이름"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              className="field field-sm"
            />
            <input
              type="text"
              placeholder="관계 (아빠, 엄마, 친구…)"
              value={formData.relation}
              onChange={(e) => setFormData({ ...formData, relation: e.target.value })}
              className="field field-sm"
            />
            <input
              type="number"
              placeholder="출생연도"
              value={formData.birth_year}
              onChange={(e) => setFormData({ ...formData, birth_year: e.target.value })}
              className="field field-sm"
            />
          </div>
          <div className="mt-4 flex gap-2">
            <button onClick={handleCreate} className="btn-primary">
              추가
            </button>
            <button onClick={() => setShowForm(false)} className="btn-quiet">
              취소
            </button>
          </div>
        </div>
      )}

      {persons.length === 0 ? (
        <p className="t-body-sm mt-10 text-ink-300">등록된 인물이 없습니다.</p>
      ) : (
        <div className="mt-10 grid grid-cols-2 gap-4">
          {persons.map((person) => {
            const info = memberInfo(person.id)
            const clips = clipsOf(person.id)
            const eventCount = person.events?.length ?? eventsOf(person.id).length

            return (
              <button
                key={person.id}
                onClick={() => setSelectedPerson(person)}
                className="surface hover-border-strong flex cursor-pointer items-center gap-5
                           p-6 text-left transition-colors duration-150 ease-out"
              >
                {person.thumbnail_url ? (
                  <img
                    src={mediaUrl(person.thumbnail_url)}
                    alt=""
                    className="h-16 w-16 shrink-0 rounded-full bg-ink-50 object-cover"
                  />
                ) : (
                  <span
                    className="flex h-16 w-16 shrink-0 items-center justify-center rounded-full
                               bg-ink-50 text-xl text-ink-300"
                  >
                    {person.name.charAt(0)}
                  </span>
                )}

                <span className="min-w-0 flex-1">
                  <span className="flex items-baseline gap-2">
                    <span className="text-lg font-semibold text-ink-900">{person.name}</span>
                    {person.relation && (
                      <span className="t-caption text-accent-ink">{person.relation}</span>
                    )}
                  </span>
                  <span className="t-caption mt-0.5 block text-ink-300">
                    {person.birth_year ? `${person.birth_year}년생 · ` : ''}
                    {eventCount}개 사건
                  </span>
                  <span className="mt-2.5 flex flex-wrap gap-1.5">
                    {info && (
                      <span className="pill bg-ink-50 font-normal text-ink-500">
                        {ROLE_LABEL[info.role]}
                      </span>
                    )}
                    {clips.length > 0 && (
                      <span
                        className="pill font-normal"
                        style={{
                          background: 'var(--accent-soft)',
                          color: 'var(--accent-ink)',
                        }}
                      >
                        목소리 {clips.length}개
                      </span>
                    )}
                    {info?.private_request && (
                      <span className="pill bg-ink-50 font-normal text-ink-400">열람 제한</span>
                    )}
                  </span>
                </span>
              </button>
            )
          })}
        </div>
      )}

      {selectedPerson && (
        <div
          onClick={() => setSelectedPerson(null)}
          className="fixed inset-0 z-[60] flex items-center justify-center p-8"
          style={{ background: 'rgba(14,13,11,0.5)' }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="w-[420px] max-h-[86vh] overflow-y-auto rounded-lg bg-paper-pure p-8"
            style={{ boxShadow: 'var(--shadow-lg)' }}
          >
            <div className="flex items-start gap-5">
              {selectedPerson.thumbnail_url ? (
                <img
                  src={mediaUrl(selectedPerson.thumbnail_url)}
                  alt=""
                  className="h-[88px] w-[88px] rounded-full bg-ink-50 object-cover"
                />
              ) : (
                <span
                  className="flex h-[88px] w-[88px] items-center justify-center rounded-full
                             bg-ink-50 text-3xl text-ink-300"
                >
                  {selectedPerson.name.charAt(0)}
                </span>
              )}

              <div className="min-w-0 flex-1">
                <p className="m-0 text-2xl font-bold tracking-[-0.02em] text-ink-900">
                  {selectedPerson.name}
                </p>
                <p className="t-caption m-0 mt-1 text-accent-ink">
                  {selectedPerson.relation}
                  {selectedPerson.birth_year && ` · ${selectedPerson.birth_year}년생`}
                </p>
                {selectedInfo && (
                  <p className="t-caption m-0 mt-2">
                    {ROLE_LABEL[selectedInfo.role]} — {ROLE_DESC[selectedInfo.role]}
                  </p>
                )}
              </div>

              <button
                onClick={() => setSelectedPerson(null)}
                className="cursor-pointer border-0 bg-transparent text-[15px] text-ink-300"
                aria-label="닫기"
              >
                ✕
              </button>
            </div>

            {selectedInfo && (
              <>
                <p
                  className="t-body-sm mt-6 pt-5"
                  style={{ borderTop: '1px solid var(--border)' }}
                >
                  확인해 준 사건 {selectedInfo.verified_count}건 · 올린 기록{' '}
                  {selectedInfo.asset_count}개 · 남긴 기억 {selectedInfo.memory_count}개
                </p>
                <p className="t-caption m-0 mt-1.5">
                  {selectedInfo.private_request
                    ? '이 사람이 등장하는 기록은 가족 공유에서 제외됩니다'
                    : '가족 공유를 허용했습니다'}
                </p>
                <Link to="/privacy" className="mt-1.5 inline-block text-xs">
                  공개 범위 바꾸기
                </Link>
              </>
            )}

            {selectedClips.length > 0 && (
              <div className="mt-6">
                <div className="mb-3 flex items-center gap-2">
                  <p className="t-eyebrow m-0">남긴 목소리</p>
                  <MockBadge label="음성 목데이터" />
                </div>
                <div className="flex flex-col gap-2">
                  {selectedClips.map((clip) => (
                    <AudioClip key={clip.id} clip={clip} compact />
                  ))}
                </div>
              </div>
            )}

            <div className="mt-6">
              <p className="t-eyebrow m-0 mb-2.5">함께한 사건</p>
              {(selectedPerson.events?.length
                ? selectedPerson.events.map((e) => ({
                    key: e.id,
                    label: `${e.date_start?.slice(0, 4) || ''} · ${e.title.replace(/^\d{4}\s*/, '')}`,
                  }))
                : eventsOf(selectedPerson.id).map((e) => ({
                    key: e.id,
                    label: `${e.date.slice(0, 4)} · ${e.title.replace(/^\d{4}\s*/, '')}`,
                  }))
              ).map((e) => (
                <p
                  key={e.key}
                  className="t-body-sm m-0 py-2"
                  style={{ borderBottom: '1px solid var(--ink-50)' }}
                >
                  {e.label}
                </p>
              ))}
            </div>
          </div>
        </div>
      )}
    </Page>
  )
}
