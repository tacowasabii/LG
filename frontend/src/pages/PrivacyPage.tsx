/**
 * 공개 · 동의 (기획안 08장 TRUST & ETHICS)
 *
 * 기획안은 "개인정보 보호는 부가기능이 아니라 사업 지속 가능성"이라고 못 박았고,
 * 심사 예상 질문에도 딥페이크 거부감과 오귀속이 들어 있다. 말로만 답하지 않도록
 * 원칙(인물 동의 · Asset 권한 · AI 라벨 · 목소리 정책 · 삭제 이관)을 각각
 * 조작 가능한 화면으로 만들었다.
 *
 * 목소리 정책만 색을 쓴 면에 올린다. 이 화면에서 유일하게 사용자가 바꿀 수 없는
 * 항목이고, 딥페이크에 대한 제품의 답이라 조작 가능한 설정들과 섞이면 안 된다.
 *
 * 실기능 개발 시 교체 지점:
 *   기본 공개 범위      -> PUT /api/family/settings
 *   Asset별 공개 범위   -> PUT /api/media/{id}/visibility
 *   인물별 비공개 요청  -> PUT /api/graph/person/{id}/consent
 *   삭제 전파 미리보기  -> GET /api/media/{id}/cascade
 */

import { useState } from 'react'
import { Link } from 'react-router-dom'
import { mediaUrl } from '../lib/api'
import {
  MOCK_ASSET_SCOPE,
  MOCK_DELETE_CASCADE,
  MOCK_MEMBERS,
  VISIBILITY_LABEL,
  Visibility,
} from '../mock/family'
import { Page, PageHeader } from '../components/Page'

const VISIBILITIES: Visibility[] = ['family', 'partial', 'private']

const VISIBILITY_DESC: Record<Visibility, string> = {
  family: '참여한 가족 구성원 모두가 봅니다.',
  partial: '고른 사람만 봅니다.',
  private: '올린 사람만 봅니다.',
}

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

export default function PrivacyPage() {
  const [defaultScope, setDefaultScope] = useState<Visibility>('family')
  const [scopes, setScopes] = useState<Record<string, Visibility>>(
    MOCK_ASSET_SCOPE.reduce((acc, a) => ({ ...acc, [a.id]: a.visibility }), {}),
  )
  const [privateRequests, setPrivateRequests] = useState<Record<string, boolean>>(
    MOCK_MEMBERS.reduce((acc, m) => ({ ...acc, [m.id]: m.private_request }), {}),
  )
  const [showCascade, setShowCascade] = useState(false)

  const memberName = (id: string) => MOCK_MEMBERS.find((m) => m.id === id)?.name || id

  return (
    <Page width={900}>
      <PageHeader
        mock
        eyebrow="Trust & Consent"
        title="공개 · 동의"
        lead="가족 기록은 기본 비공개입니다. 누가 무엇을 볼 수 있는지 여기서 정합니다."
      />

      <div className="mt-10">
        <p className="t-eyebrow m-0 mb-3">새 기록의 기본 공개 범위</p>
        <div className="grid grid-cols-3 gap-3">
          {VISIBILITIES.map((v) => (
            <button
              key={v}
              onClick={() => setDefaultScope(v)}
              className="cursor-pointer rounded-lg p-5 text-left"
              style={{
                background:
                  defaultScope === v ? 'var(--accent-soft)' : 'var(--paper-pure)',
                border: `1px solid ${defaultScope === v ? 'var(--accent)' : 'var(--border)'}`,
              }}
            >
              <span className="block text-[15px] font-semibold text-ink-900">
                {VISIBILITY_LABEL[v]}
              </span>
              <span className="t-caption mt-1.5 block">{VISIBILITY_DESC[v]}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="mt-10">
        <p className="t-eyebrow m-0 mb-1">기록별 공개 범위</p>
        <p className="t-caption m-0 mb-3">
          사진·음성마다 따로 정합니다. 소유자는 올린 사람입니다.
        </p>
        <div className="rule-strong">
          {MOCK_ASSET_SCOPE.map((asset) => (
            <div
              key={asset.id}
              className="flex items-center gap-5 px-1 py-4"
              style={{ borderBottom: '1px solid var(--border)' }}
            >
              <span className="min-w-0 flex-1">
                <span className="block text-[15px] text-ink-900">{asset.label}</span>
                <span className="t-caption mt-[3px] block">
                  {asset.owner_name} 소유 · 파일 {asset.media_count}개
                  {scopes[asset.id] === 'partial' &&
                    asset.allowed_ids.length > 0 &&
                    ` · 열람 ${asset.allowed_ids.map(memberName).join(', ')}`}
                </span>
              </span>

              <select
                value={scopes[asset.id]}
                onChange={(e) =>
                  setScopes((prev) => ({ ...prev, [asset.id]: e.target.value as Visibility }))
                }
                className="field field-inline shrink-0"
              >
                {VISIBILITIES.map((v) => (
                  <option key={v} value={v}>
                    {VISIBILITY_LABEL[v]}
                  </option>
                ))}
              </select>
            </div>
          ))}
        </div>
      </div>

      <div className="mt-10">
        <p className="t-eyebrow m-0 mb-1">인물별 비공개 요청</p>
        <p className="t-caption m-0 mb-3">
          사진 속 인물이 원하면 그 사람이 등장하는 기록을 가족 공유에서 뺍니다. 원본은 지우지
          않고 소유자만 볼 수 있게 둡니다.
        </p>
        <div style={{ borderTop: '1px solid var(--border)' }}>
          {MOCK_MEMBERS.map((m) => {
            const on = privateRequests[m.id]
            return (
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
                    {on ? '가족 공유에서 제외됨' : '가족 공유 허용'}
                  </span>
                </span>
                <button
                  onClick={() => setPrivateRequests((prev) => ({ ...prev, [m.id]: !on }))}
                  className="cursor-pointer rounded px-3.5 py-1.5 text-xs"
                  style={
                    on
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
                  {on ? '비공개' : '공개'}
                </button>
              </div>
            )
          })}
        </div>
      </div>

      {/* AI 라벨 — 끌 수 없다 */}
      <div className="mt-10">
        <p className="t-eyebrow m-0 mb-1">AI 생성 요소 표시</p>
        <p className="t-caption m-0 mb-3">
          제품 원칙이라 끌 수 없습니다. 무엇이 원본이고 무엇이 만들어진 것인지 항상 보입니다.
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
                style={{
                  background: 'var(--positive-soft)',
                  color: 'var(--positive-ink)',
                }}
              >
                항상 켜짐
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* 고인 음성 정책 — 이 화면에서 유일하게 끌 수 없는 원칙 */}
      <div
        className="mt-10 rounded-lg px-7 py-6"
        style={{ background: 'var(--critical-soft)' }}
      >
        <p className="t-eyebrow m-0" style={{ color: 'var(--critical-ink)' }}>
          목소리 정책
        </p>
        <p
          className="t-body mt-3 max-w-[64ch]"
          style={{ color: 'var(--critical-ink)' }}
        >
          돌아가신 분의 목소리를 학습해 새로운 문장을 말하게 하지 않습니다. 남아 있는 음성은
          원본 구간과 출처를 표시해 그대로 재생하고, 음성이 없으면 중립적인 AI 내레이터를
          씁니다. 본인이 직접 남기는 목소리 기록은 명시적으로 동의한 경우에만 다룹니다.
        </p>
      </div>

      <div className="mt-10">
        <p className="t-eyebrow m-0 mb-1">삭제 · 이관</p>
        <p className="t-caption m-0 mb-4">
          원본을 지우면 그 원본으로 만든 것들도 함께 지워집니다. 지우기 전에 무엇이 사라지는지
          먼저 보여줍니다.
        </p>

        <button
          onClick={() => setShowCascade((v) => !v)}
          className="btn-quiet px-[18px] py-2.5 text-[13px]"
        >
          {showCascade ? '미리보기 닫기' : '삭제 영향 미리보기'}
        </button>

        {showCascade && (
          <div
            className="mt-4 rounded-lg p-6"
            style={{ background: 'var(--critical-soft)' }}
          >
            <p className="t-body-sm m-0" style={{ color: 'var(--critical-ink)' }}>
              지울 원본 · {MOCK_DELETE_CASCADE.target}
            </p>
            <p
              className="t-eyebrow mb-2.5 mt-4"
              style={{ color: 'var(--critical-ink)' }}
            >
              함께 사라지는 것
            </p>
            {MOCK_DELETE_CASCADE.derived.map((d) => (
              <div
                key={d.label}
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
              가족이 남긴 기억 문장은 지워지지 않습니다. 사진과의 연결만 끊깁니다.
            </p>
          </div>
        )}

        <div className="mt-5 flex flex-wrap gap-2">
          <Link
            to="/export"
            className="btn-quiet px-[18px] py-2.5 text-[13px] no-underline hover:no-underline"
          >
            가족 아카이브 내보내기
          </Link>
          <button className="btn-quiet px-[18px] py-2.5 text-[13px]">
            가족 관리자 넘기기
          </button>
          <button className="btn-outline px-[18px] py-2.5 text-[13px]">
            내 기록 전부 삭제 요청
          </button>
        </div>
      </div>
    </Page>
  )
}
