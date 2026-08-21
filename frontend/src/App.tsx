import { Routes, Route, Navigate } from 'react-router-dom'
import AppLayout from './layouts/AppLayout'
import TVLayout from './layouts/TVLayout'
import { CurrentUserProvider } from './lib/currentUser'
import HomePage from './pages/HomePage'
import AlbumPage from './pages/AlbumPage'
import CollectPage from './pages/CollectPage'
import GraphPage from './pages/GraphPage'
import ChatPage from './pages/ChatPage'
import InterviewPage from './pages/InterviewPage'
import ContinuePage from './pages/ContinuePage'
import MemoryDetailPage from './pages/MemoryDetailPage'
import TVViewPage from './pages/TVViewPage'
import FamilyPage from './pages/FamilyPage'
import JoinPage from './pages/JoinPage'
import MapPage from './pages/MapPage'
import FilmPage from './pages/FilmPage'
import SpacePage from './pages/SpacePage'
import PrivacyPage from './pages/PrivacyPage'
import TrustPage from './pages/TrustPage'
import ExportPage from './pages/ExportPage'

function App() {
  return (
    // 기억을 남기는 사람이 누구인지가 모든 화면에 필요하다 (기획안 08장 귀속·동의)
    <CurrentUserProvider>
      <Routes>
        {/* TV View uses its own fullscreen layout */}
        <Route path="/tv" element={<TVLayout />}>
          <Route index element={<TVViewPage />} />
        </Route>

        {/* All other pages use the app layout */}
        <Route path="/" element={<AppLayout />}>
          <Route index element={<HomePage />} />
          {/* 사진첩 — 추억이 아니라 사진 자체를 훑는 자리.
              조건은 주소에 남는다 (?year=2025&person_id=P02&type=photo) */}
          <Route path="album" element={<AlbumPage />} />
          {/* 모으기 하나로 합쳤다 (올리기 · 채우기 · 첫 질문).
              예전 두 주소는 문서·초대 화면 링크가 살아 있게 리다이렉트한다. */}
          <Route path="collect" element={<CollectPage />} />
          <Route path="onboarding" element={<Navigate to="/collect" replace />} />
          <Route path="upload" element={<Navigate to="/collect" replace />} />
          <Route path="map" element={<MapPage />} />
          <Route path="graph" element={<GraphPage />} />
          <Route path="chat" element={<ChatPage />} />
          <Route path="film" element={<FilmPage />} />
          <Route path="interview" element={<InterviewPage />} />
          {/* 기억 이어가기 — 예전 "확인 요청"과 "Memory Gap"이 있던 자리.
              둘 다 처리해야 할 과제 목록이었고, 이제는 기억을 더하는 자리 하나다.
              예전 주소는 문서·다른 화면 링크가 살아 있게 리다이렉트한다. */}
          <Route path="continue" element={<ContinuePage />} />
          <Route path="memory/:eventId" element={<MemoryDetailPage />} />
          <Route path="verify" element={<Navigate to="/continue" replace />} />
          <Route path="gaps" element={<Navigate to="/continue" replace />} />
          <Route path="family" element={<FamilyPage />} />
          <Route path="space" element={<SpacePage />} />
          {/* 초대 링크가 도착하는 자리 (backend/services/family.py join) */}
          <Route path="join/:code" element={<JoinPage />} />
          <Route path="privacy" element={<PrivacyPage />} />
          <Route path="export" element={<ExportPage />} />
          <Route path="trust" element={<TrustPage />} />
        </Route>
      </Routes>
    </CurrentUserProvider>
  )
}

export default App
