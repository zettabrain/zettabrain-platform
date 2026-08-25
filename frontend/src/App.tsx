import { Routes, Route, Navigate } from 'react-router-dom'
import AppShell from './components/AppShell'
import LoginPage from './pages/LoginPage'
import ChatPage from './pages/ChatPage'
import GeneratePage from './pages/GeneratePage'
import DocsPage from './pages/DocsPage'
import TeamPage from './pages/TeamPage'
import AdminDashboard from './pages/AdminDashboard'
import AdminSettingsPage from './pages/AdminSettingsPage'
import { useAuth } from './context/AuthContext'

function RequireAdmin({ children }: { children: React.ReactNode }) {
  const { isAdmin, isLoading } = useAuth()
  if (isLoading) return null
  if (!isAdmin) return <Navigate to="/chat" replace />
  return <>{children}</>
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<AppShell />}>
        <Route index element={<Navigate to="/chat" replace />} />
        <Route path="/chat" element={<ChatPage />} />
        <Route path="/generate" element={<GeneratePage />} />
        <Route path="/docs" element={<DocsPage />} />
        <Route path="/team" element={<TeamPage />} />
        <Route
          path="/admin"
          element={
            <RequireAdmin>
              <AdminDashboard />
            </RequireAdmin>
          }
        />
        <Route
          path="/admin/settings"
          element={
            <RequireAdmin>
              <AdminSettingsPage />
            </RequireAdmin>
          }
        />
      </Route>
      <Route path="*" element={<Navigate to="/chat" replace />} />
    </Routes>
  )
}
