import { useState } from 'react'
import { Outlet, NavLink } from 'react-router-dom'
import {
  AlertCircle,
  BarChart3,
  Download,
  Film,
  Home,
  Lock,
  MapPin,
  MessageCircle,
  Mic,
  ShieldCheck,
  Share2,
  Sparkles,
  Tv,
  Upload,
  Users,
  Users2,
} from 'lucide-react'
import { mediaUrl } from '../lib/api'
import { useCurrentUser } from '../lib/currentUser'
import { MOCK_TIMELINE } from '../mock/timeline'

/**
 * 사이드바를 기획안의 가치 흐름(모으기 → 이해 → 확인 → 경험)대로 묶었다.
 * 화면이 16개로 늘어나 평면 목록으로는 무엇을 하는 앱인지 읽히지 않는다.
 *
 * 묶음 제목은 대문자 라벨로 작게 눌러 두고 항목만 읽히게 한다. 지금 있는
 * 화면은 강조색을 옅게 깐 면으로 표시한다 — 사이드바에서 색을 쓰는 곳은
 * 여기와 확인 대기 건수뿐이다.
 */
const navGroups = [
  {
    title: '기억',
    items: [
      { to: '/', icon: Home, label: '홈' },
      { to: '/map', icon: MapPin, label: '타임라인 · 지도' },
      { to: '/graph', icon: Share2, label: '그래프' },
      { to: '/family', icon: Users, label: '인물' },
    ],
  },
  {
    title: '모으기',
    items: [
      { to: '/onboarding', icon: Sparkles, label: '시작하기' },
      { to: '/upload', icon: Upload, label: '업로드' },
      { to: '/interview', icon: Mic, label: 'AI 인터뷰' },
    ],
  },
  {
    title: '확인',
    items: [
      { to: '/verify', icon: ShieldCheck, label: '확인 요청', badge: true },
      { to: '/gaps', icon: AlertCircle, label: 'Memory Gap' },
    ],
  },
  {
    title: '경험',
    items: [
      { to: '/chat', icon: MessageCircle, label: '채팅' },
      { to: '/film', icon: Film, label: 'Memory Film' },
      { to: '/tv', icon: Tv, label: 'TV' },
    ],
  },
  {
    title: '가족',
    items: [
      { to: '/space', icon: Users2, label: '가족 공간' },
      { to: '/privacy', icon: Lock, label: '공개 · 동의' },
      { to: '/export', icon: Download, label: '내보내기' },
      { to: '/trust', icon: BarChart3, label: '신뢰도 리포트' },
    ],
  },
]

export default function AppLayout() {
  const { current, members, setCurrentId } = useCurrentUser()
  const [switcherOpen, setSwitcherOpen] = useState(false)

  // 확인 대기 건수 — 실기능 개발 시 GET /api/graph/verify 의 합계로 교체
  const pending = MOCK_TIMELINE.filter(
    (e) => e.state === 'inferred' || e.state === 'conflicted',
  ).length

  return (
    <div className="flex h-screen overflow-hidden bg-paper">
      <aside
        className="flex w-[268px] shrink-0 flex-col bg-paper-pure"
        style={{ borderRight: '1px solid var(--border)' }}
      >
        <div className="px-6 pb-5 pt-7">
          <p className="t-eyebrow m-0 mb-2">Family Memory Graph</p>
          <h1 className="m-0 text-[21px] font-bold tracking-[-0.02em] text-ink-900">
            LG HomeStory
          </h1>
          <p className="t-caption m-0 mt-1">기억을 잇는 공간</p>
        </div>

        {/* 지금 사용 중인 사람 — 남기는 기억과 확인의 귀속 대상 */}
        <div className="px-4 pb-4">
          <button
            onClick={() => setSwitcherOpen((v) => !v)}
            className="flex w-full items-center gap-2.5 rounded bg-ink-50 p-2.5 text-left
                       transition-colors duration-150 ease-out hover:bg-accent-soft"
            style={{ border: '1px solid var(--border)' }}
          >
            {current.thumbnail_url ? (
              <img
                src={mediaUrl(current.thumbnail_url)}
                alt=""
                className="h-8 w-8 shrink-0 rounded-full bg-ink-100 object-cover"
              />
            ) : (
              <span
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full
                           bg-ink-100 text-xs text-ink-300"
              >
                {current.name.slice(0, 1)}
              </span>
            )}
            <span className="min-w-0 flex-1">
              <span className="block truncate text-[13px] font-semibold text-ink-700">
                {current.name}
              </span>
              <span className="mt-px block text-[11px] text-ink-300">
                {current.relation}으로 사용 중
              </span>
            </span>
            <span className="text-[10px] text-ink-300">{switcherOpen ? '▲' : '▼'}</span>
          </button>

          {switcherOpen && (
            <ul
              className="mt-1.5 overflow-hidden rounded bg-paper-pure"
              style={{ border: '1px solid var(--border)', boxShadow: 'var(--shadow-sm)' }}
            >
              {members
                .filter((m) => m.id !== current.id)
                .map((m) => (
                  <li key={m.id}>
                    <button
                      onClick={() => {
                        setCurrentId(m.id)
                        setSwitcherOpen(false)
                      }}
                      className="flex w-full items-center gap-2 px-2.5 py-2 text-left hover:bg-ink-50"
                      style={{ borderBottom: '1px solid var(--ink-50)' }}
                    >
                      {m.thumbnail_url ? (
                        <img
                          src={mediaUrl(m.thumbnail_url)}
                          alt=""
                          className="h-[22px] w-[22px] rounded-full bg-ink-100 object-cover"
                        />
                      ) : (
                        <span
                          className="flex h-[22px] w-[22px] items-center justify-center
                                     rounded-full bg-ink-100 text-[10px] text-ink-300"
                        >
                          {m.name.slice(0, 1)}
                        </span>
                      )}
                      <span className="text-[13px] text-ink-500">{m.name}</span>
                      <span className="ml-auto text-[11px] text-ink-300">{m.relation}</span>
                    </button>
                  </li>
                ))}
            </ul>
          )}
        </div>

        <nav className="flex-1 overflow-y-auto px-4 pb-4 pt-1">
          {navGroups.map((group) => (
            <div key={group.title} className="mb-[18px]">
              <p className="t-eyebrow m-0 mb-2 ml-2.5 text-[10px] text-ink-300">
                {group.title}
              </p>
              <ul className="flex flex-col gap-px">
                {group.items.map((item) => (
                  <li key={item.to}>
                    <NavLink
                      to={item.to}
                      end={item.to === '/'}
                      className={({ isActive }) =>
                        `flex items-center gap-2.5 rounded px-2.5 py-2 text-sm
                         transition-colors duration-150 ease-out ${
                           isActive
                             ? 'bg-accent-soft font-semibold text-accent-ink'
                             : 'text-ink-500 hover:bg-ink-50'
                         }`
                      }
                    >
                      <item.icon size={17} strokeWidth={1.75} className="shrink-0 opacity-80" />
                      <span className="flex-1">{item.label}</span>
                      {'badge' in item && item.badge && pending > 0 && (
                        <span
                          className="t-mono rounded-full px-1.5 py-px text-[10px]"
                          style={{ background: 'var(--accent)', color: 'var(--accent-fg)' }}
                        >
                          {pending}
                        </span>
                      )}
                    </NavLink>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </nav>

        <div className="px-6 py-4" style={{ borderTop: '1px solid var(--border)' }}>
          <p className="t-caption m-0 text-[11px] text-ink-300">
            LG Promptathon 2026
            <br />
            Memory Graph · EXAONE
          </p>
        </div>
      </aside>

      {/* 여백은 각 화면이 스스로 잡는다 — 화면마다 본문 폭이 다르다 */}
      <main className="flex-1 overflow-y-auto">
        <Outlet />
      </main>
    </div>
  )
}
