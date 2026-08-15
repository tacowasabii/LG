import { Routes, Route } from 'react-router-dom'
import AppLayout from './layouts/AppLayout'
import TVLayout from './layouts/TVLayout'
import HomePage from './pages/HomePage'
import UploadPage from './pages/UploadPage'
import GraphPage from './pages/GraphPage'
import ChatPage from './pages/ChatPage'
import InterviewPage from './pages/InterviewPage'
import GapsPage from './pages/GapsPage'
import TVViewPage from './pages/TVViewPage'
import FamilyPage from './pages/FamilyPage'

function App() {
  return (
    <Routes>
      {/* TV View uses its own fullscreen layout */}
      <Route path="/tv" element={<TVLayout />}>
        <Route index element={<TVViewPage />} />
      </Route>

      {/* All other pages use the app layout */}
      <Route path="/" element={<AppLayout />}>
        <Route index element={<HomePage />} />
        <Route path="upload" element={<UploadPage />} />
        <Route path="graph" element={<GraphPage />} />
        <Route path="chat" element={<ChatPage />} />
        <Route path="interview" element={<InterviewPage />} />
        <Route path="gaps" element={<GapsPage />} />
        <Route path="family" element={<FamilyPage />} />
      </Route>
    </Routes>
  )
}

export default App
