import { Outlet, Navigate } from 'react-router-dom'
import NavRail from './NavRail'
import { useAuth } from '../context/AuthContext'
import Spinner from './Spinner'
import { TeamProvider } from '../context/TeamContext'

export default function AppShell() {
  const { user, isLoading } = useAuth()

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-bg-base">
        <div className="flex flex-col items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-brand to-violet-ai flex items-center justify-center shadow-glow">
            <span className="text-white font-bold text-lg">Z</span>
          </div>
          <Spinner size="md" />
        </div>
      </div>
    )
  }

  if (!user) {
    return <Navigate to="/login" replace />
  }

  return (
    <TeamProvider>
      <div className="flex min-h-screen bg-bg-base">
        <NavRail />
        <main className="flex-1 ml-56 flex flex-col min-h-screen">
          <Outlet />
        </main>
      </div>
    </TeamProvider>
  )
}
