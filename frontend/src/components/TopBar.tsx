import { Bell } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { useTeam } from '../context/TeamContext'

interface TopBarProps {
  title: string
  subtitle?: string
  actions?: React.ReactNode
}

export default function TopBar({ title, subtitle, actions }: TopBarProps) {
  const { user } = useAuth()
  const { activeTeam } = useTeam()

  return (
    <header className="h-14 flex items-center justify-between px-6 border-b border-border bg-bg-surface/80 backdrop-blur-sm sticky top-0 z-20">
      <div className="flex items-center gap-3">
        <div>
          <h1 className="text-sm font-semibold text-text-primary leading-tight">{title}</h1>
          {subtitle && <p className="text-xs text-text-muted leading-tight">{subtitle}</p>}
        </div>
        {activeTeam && (
          <span className="px-2 py-0.5 rounded-md bg-brand/10 border border-brand/20 text-xs text-brand font-medium">
            {activeTeam.name}
          </span>
        )}
      </div>

      <div className="flex items-center gap-2">
        {actions}
        <button className="relative p-2 rounded-lg text-text-muted hover:text-text-primary hover:bg-bg-elevated transition-colors">
          <Bell size={16} />
        </button>
        <div className="w-7 h-7 rounded-full bg-gradient-to-br from-brand to-violet-ai flex items-center justify-center">
          <span className="text-white text-xs font-bold">
            {user?.username?.[0]?.toUpperCase() ?? 'U'}
          </span>
        </div>
      </div>
    </header>
  )
}
