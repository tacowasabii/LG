import { Routes, Route } from 'react-router-dom'
import AppLayout from './layouts/AppLayout'
import TVLayout from './layouts/TVLayout'
import { CurrentUserProvider } from './lib/currentUser'
import HomePage from './pages/HomePage'
import UploadPage from './pages/UploadPage'
import GraphPage from './pages/GraphPage'
import ChatPage from './pages/ChatPage'
import InterviewPage from './pages/InterviewPage'
import GapsPage from './pages/GapsPage'
import VerifyPage from './pages/VerifyPage'
import TVViewPage from './pages/TVViewPage'
import FamilyPage from './pages/FamilyPage'
import JoinPage from './pages/JoinPage'
import OnboardingPage from './pages/OnboardingPage'
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
          <Route path="onboarding" element={<OnboardingPage />} />
          <Route path="upload" element={<UploadPage />} />
          <Route path="map" element={<MapPage />} />
          <Route path="graph" element={<GraphPage />} />
          <Route path="chat" element={<ChatPage />} />
          <Route path="film" element={<FilmPage />} />
          <Route path="interview" element={<InterviewPage />} />
          <Route path="gaps" element={<GapsPage />} />
          <Route path="verify" element={<VerifyPage />} />
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
