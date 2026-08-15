import { Outlet, NavLink } from 'react-router-dom'
import {
  Home,
  Upload,
  Share2,
  MessageCircle,
  Mic,
  AlertCircle,
  Tv,
  Users,
} from 'lucide-react'

const navItems = [
  { to: '/', icon: Home, label: '홈' },
  { to: '/upload', icon: Upload, label: '업로드' },
  { to: '/graph', icon: Share2, label: '그래프' },
  { to: '/chat', icon: MessageCircle, label: '채팅' },
  { to: '/interview', icon: Mic, label: '인터뷰' },
  { to: '/gaps', icon: AlertCircle, label: 'Gap' },
  { to: '/tv', icon: Tv, label: 'TV' },
  { to: '/family', icon: Users, label: '가족' },
]

export default function AppLayout() {
  return (
    <div className="flex h-screen overflow-hidden">
      {/* Sidebar */}
      <nav className="w-64 bg-white border-r border-gray-200 flex flex-col">
        {/* Logo */}
        <div className="p-5 border-b border-gray-100">
          <div className="flex items-center gap-2">
            <img src="/vite.svg" className="w-8 h-8" alt="logo" />
            <div>
              <h1 className="font-bold text-gray-900 text-sm">Family Memory Graph</h1>
              <p className="text-xs text-gray-500">가족 기억 공간</p>
            </div>
          </div>
        </div>

        {/* Navigation */}
        <div className="flex-1 py-4 overflow-y-auto">
          <ul className="space-y-1 px-3">
            {navItems.map((item) => (
              <li key={item.to}>
                <NavLink
                  to={item.to}
                  end={item.to === '/'}
                  className={({ isActive }) =>
                    `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors ${
                      isActive
                        ? 'bg-primary-50 text-primary-700 font-medium'
                        : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
                    }`
                  }
                >
                  <item.icon size={18} />
                  <span>{item.label}</span>
                </NavLink>
              </li>
            ))}
          </ul>
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-gray-100">
          <p className="text-xs text-gray-400 text-center tracking-wide">Family Memory Graph · LG Promptathon 2026</p>
        </div>
      </nav>

      {/* Main Content */}
      <main className="flex-1 overflow-y-auto">
        <div className="p-6">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
