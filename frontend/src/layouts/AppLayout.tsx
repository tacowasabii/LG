import { Outlet, NavLink } from 'react-router-dom'
import {
  BarChart3,
  Download,
  Film,
  Heart,
  Home,
  Images,
  Lock,
  MapPin,
  MessageCircle,
  Mic,
  Tv,
  Upload,
  Users,
  Users2,
} from 'lucide-react'
import { mediaUrl } from '../lib/api'
import { useCurrentUser } from '../lib/currentUser'

/**
 * 사이드바를 가치 흐름(모으기 → 이해 → 이어가기 → 경험)대로 묶었다.
 * 화면이 여럿이라 평면 목록으로는 무엇을 하는 앱인지 읽히지 않는다.
 *
 * 묶음 제목은 대문자 라벨로 작게 눌러 두고 항목만 읽히게 한다. 지금 있는
 * 화면은 강조색을 옅게 깐 면으로 표시한다 — 사이드바에서 색을 쓰는 곳은
 * 여기뿐이다.
 *
 * 예전에는 "확인" 묶음에 확인 요청과 Memory Gap이 있었고, 확인 대기 건수를
 * 강조색 뱃지로 달았다. 둘 다 없앴다. 남의 기억을 확인해 줄 의무가 사라졌고,
 * 밀린 건수를 뱃지로 세우면 그 순간 이 앱은 다시 할 일 목록이 된다.
 *
 * 그래프(/graph)는 목록에서 뺐다. 기억을 찾는 길로는 사진첩·타임라인·인물이
 * 앞서고, 노드와 엣지를 보는 화면은 가족이 쓸 자리가 아니다. 주소와 기능은
 * 그대로 살아 있다 — 시연과 점검에서 직접 열어 쓴다 (App.tsx의 /graph).
 */
const navGroups = [
  {
    title: '기억',
    items: [
      { to: '/', icon: Home, label: '홈' },
      { to: '/album', icon: Images, label: '사진첩' },
      { to: '/map', icon: MapPin, label: '타임라인 · 지도' },
      { to: '/family', icon: Users, label: '인물' },
    ],
  },
  {
    title: '모으기',
    items: [
      { to: '/collect', icon: Upload, label: '모으기' },
      { to: '/interview', icon: Mic, label: 'AI 인터뷰' },
    ],
  },
  {
    title: '이어가기',
    items: [{ to: '/continue', icon: Heart, label: '기억 이어가기' }],
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
  const { current, error: familyError } = useCurrentUser()

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

        {/*
          로그인한 사람의 프로필 — 남기는 기억과 확인의 귀속 대상.
          고르는 목록이 아니라 본인 프로필 하나만 보여 준다.
        */}
        <div className="px-4 pb-4">
          <div
            className="flex w-full items-center gap-2.5 rounded bg-ink-50 p-2.5"
            style={{ border: '1px solid var(--border)' }}
          >
            {current?.thumbnail_url ? (
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
                {current?.name.slice(0, 1) || '·'}
              </span>
            )}
            <span className="min-w-0 flex-1">
              <span className="block truncate text-[13px] font-semibold text-ink-700">
                {current?.name || (familyError ? '연결 안 됨' : '불러오는 중…')}
              </span>
              <span className="mt-px block text-[11px] text-ink-300">
                {current?.relation ?? ''}
              </span>
            </span>
          </div>

          {/*
            백엔드에 못 붙으면 여기서 말한다. 예전에는 "불러오는 중…"에 갇혀서
            서버가 죽은 것처럼 보였고, 원인(주소·CORS)을 찾는 데 한참 걸렸다.
          */}
          {familyError && (
            <p
              className="m-0 mt-2 px-2 text-[11px] leading-snug"
              style={{ color: 'var(--critical-ink)' }}
            >
              {familyError}
            </p>
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
