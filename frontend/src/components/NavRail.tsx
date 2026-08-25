import { Link, useLocation } from 'react-router-dom'
import {
  MessageSquare,
  Sparkles,
  FolderOpen,
  Users,
  Settings,
  LayoutDashboard,
  LogOut,
  ChevronDown,
} from 'lucide-react'
import { cn } from '../lib/utils'
import { useAuth } from '../context/AuthContext'
import { useTeam } from '../context/TeamContext'
import { useState } from 'react'

const navItems = [
  { to: '/chat', icon: MessageSquare, label: 'Chat' },
  { to: '/generate', icon: Sparkles, label: 'Generate' },
  { to: '/docs', icon: FolderOpen, label: 'Documents' },
  { to: '/team', icon: Users, label: 'Team' },
]

const adminItems = [
  { to: '/admin', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/admin/settings', icon: Settings, label: 'Settings' },
]

export default function NavRail() {
  const { pathname } = useLocation()
  const { user, logout, isAdmin } = useAuth()
  const { teams, activeTeam, setActiveTeam } = useTeam()
  const [teamOpen, setTeamOpen] = useState(false)

  return (
    <aside className="fixed left-0 top-0 bottom-0 w-56 bg-bg-surface border-r border-border flex flex-col z-30 dot-grid">
      {/* Logo */}
      <div className="px-4 py-5 border-b border-border">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-brand to-violet-ai flex items-center justify-center shadow-glow">
            <span className="text-white font-bold text-sm">Z</span>
          </div>
          <div>
            <p className="text-sm font-bold text-text-primary leading-tight">ZettaBrain</p>
            <p className="text-[10px] text-text-muted leading-tight uppercase tracking-wide">Platform</p>
          </div>
        </div>
      </div>

      {/* Team Switcher */}
      <div className="px-3 py-3 border-b border-border">
        <p className="section-title">Workspace</p>
        <div className="relative">
          <button
            onClick={() => setTeamOpen(!teamOpen)}
            className="w-full flex items-center justify-between px-3 py-2 rounded-lg bg-bg-elevated border border-border text-sm text-text-primary hover:border-brand/40 transition-colors"
          >
            <span className="truncate">{activeTeam?.name ?? 'No team'}</span>
            <ChevronDown size={14} className={cn('text-text-muted flex-shrink-0 transition-transform', teamOpen && 'rotate-180')} />
          </button>
          {teamOpen && teams.length > 0 && (
            <div className="absolute top-full left-0 right-0 mt-1 bg-bg-surface border border-border rounded-lg shadow-xl z-50 overflow-hidden animate-fade-in">
              {teams.map((t) => (
                <button
                  key={t.id}
                  onClick={() => { setActiveTeam(t); setTeamOpen(false) }}
                  className={cn(
                    'w-full text-left px-3 py-2 text-sm hover:bg-bg-elevated transition-colors',
                    t.id === activeTeam?.id ? 'text-brand' : 'text-text-primary'
                  )}
                >
                  {t.name}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Main Nav */}
      <nav className="flex-1 px-3 py-4 space-y-0.5 overflow-y-auto">
        <p className="section-title">Menu</p>
        {navItems.map(({ to, icon: Icon, label }) => {
          const active = pathname.startsWith(to)
          return (
            <Link
              key={to}
              to={to}
              className={cn('nav-item', active && 'nav-item-active')}
            >
              <Icon size={16} className="flex-shrink-0" />
              {label}
            </Link>
          )
        })}

        {isAdmin && (
          <>
            <div className="pt-4">
              <p className="section-title">Admin</p>
            </div>
            {adminItems.map(({ to, icon: Icon, label }) => {
              const active = pathname === to || (to !== '/admin' && pathname.startsWith(to))
              return (
                <Link
                  key={to}
                  to={to}
                  className={cn('nav-item', active && 'nav-item-active')}
                >
                  <Icon size={16} className="flex-shrink-0" />
                  {label}
                </Link>
              )
            })}
          </>
        )}
      </nav>

      {/* User footer */}
      <div className="px-3 py-4 border-t border-border">
        <div className="flex items-center gap-2.5 px-2 py-1.5 rounded-lg">
          <div className="w-7 h-7 rounded-full bg-gradient-to-br from-brand to-violet-ai flex items-center justify-center flex-shrink-0">
            <span className="text-white text-xs font-bold">
              {user?.username?.[0]?.toUpperCase() ?? 'U'}
            </span>
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-xs font-medium text-text-primary truncate">{user?.username}</p>
            <p className="text-[10px] text-text-muted capitalize">{user?.system_role}</p>
          </div>
          <button
            onClick={logout}
            title="Sign out"
            className="p-1.5 rounded-md text-text-muted hover:text-danger hover:bg-danger/10 transition-colors"
          >
            <LogOut size={14} />
          </button>
        </div>
      </div>
    </aside>
  )
}
