import { useState, useEffect } from 'react'
import {
  Users,
  UserPlus,
  UserMinus,
  Crown,
  Eye,
  RefreshCw,
  Upload,
  BarChart2,
  Settings2,
  ChevronDown,
  Check,
} from 'lucide-react'
import TopBar from '../components/TopBar'
import Spinner from '../components/Spinner'
import Modal from '../components/Modal'
import EmptyState from '../components/EmptyState'
import { useTeam } from '../context/TeamContext'
import {
  getTeamMembers,
  getTeamStats,
  addTeamMember,
  removeTeamMember,
  ingestTeamDocs,
  type TeamMember,
  type TeamStats,
} from '../api/teams'
import { getAdminUsers, type AdminUser } from '../api/admin'
import { cn, formatDate } from '../lib/utils'

type Tab = 'members' | 'ingest' | 'stats'

export default function TeamPage() {
  const { activeTeam, refresh: refreshTeams } = useTeam()
  const [tab, setTab] = useState<Tab>('members')

  if (!activeTeam) {
    return (
      <div className="flex flex-col h-screen">
        <TopBar title="Team" subtitle="Team management" />
        <EmptyState
          icon={Users}
          title="No team selected"
          description="Select a team from the sidebar to manage it"
          className="flex-1"
        />
      </div>
    )
  }

  return (
    <div className="flex flex-col h-screen">
      <TopBar
        title={activeTeam.name}
        subtitle="Team management"
        actions={
          <div className="flex gap-1">
            {(['members', 'ingest', 'stats'] as Tab[]).map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={cn(
                  'px-3 py-1.5 rounded-md text-xs font-medium capitalize transition-colors',
                  tab === t
                    ? 'bg-brand/10 text-brand border border-brand/20'
                    : 'text-text-muted hover:text-text-primary hover:bg-bg-elevated'
                )}
              >
                {t}
              </button>
            ))}
          </div>
        }
      />
      <div className="flex-1 overflow-y-auto">
        {tab === 'members' && <MembersTab teamId={activeTeam.id} />}
        {tab === 'ingest' && <IngestTab teamId={activeTeam.id} teamName={activeTeam.name} />}
        {tab === 'stats' && <StatsTab teamId={activeTeam.id} />}
      </div>
    </div>
  )
}

/* ── Members Tab ── */
function MembersTab({ teamId }: { teamId: number }) {
  const [members, setMembers] = useState<TeamMember[]>([])
  const [loading, setLoading] = useState(true)
  const [showAdd, setShowAdd] = useState(false)
  const [removeTarget, setRemoveTarget] = useState<TeamMember | null>(null)

  const load = () => {
    setLoading(true)
    getTeamMembers(teamId)
      .then(setMembers)
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [teamId])

  const handleRemove = async () => {
    if (!removeTarget) return
    try {
      await removeTeamMember(teamId, removeTarget.id)
      setRemoveTarget(null)
      load()
    } catch { /* ignore */ }
  }

  const roleIcon = (role: string) => {
    if (role === 'manager') return <Crown size={12} className="text-warning" />
    if (role === 'viewer') return <Eye size={12} className="text-text-muted" />
    return <Users size={12} className="text-brand" />
  }

  const roleBadge = (role: string) => cn(
    'badge capitalize',
    role === 'manager'
      ? 'bg-warning/10 border border-warning/20 text-warning'
      : role === 'viewer'
      ? 'bg-bg-elevated border border-border text-text-muted'
      : 'bg-brand/10 border border-brand/20 text-brand'
  )

  return (
    <div className="px-6 py-6 max-w-3xl mx-auto space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-text-primary">Members ({members.length})</h2>
        <button onClick={() => setShowAdd(true)} className="btn-primary text-xs py-2">
          <UserPlus size={13} />Add Member
        </button>
      </div>

      {loading ? (
        <div className="flex justify-center py-16"><Spinner size="lg" /></div>
      ) : members.length === 0 ? (
        <EmptyState
          icon={Users}
          title="No members yet"
          description="Add members to give them access to this team's documents and AI features"
          action={
            <button onClick={() => setShowAdd(true)} className="btn-primary text-xs">
              <UserPlus size={13} />Add First Member
            </button>
          }
        />
      ) : (
        <div className="card p-0 overflow-hidden">
          <div className="divide-y divide-border">
            {members.map((m) => (
              <div key={m.id} className="flex items-center gap-4 px-4 py-3 hover:bg-bg-elevated/40 transition-colors">
                <div className="w-9 h-9 rounded-full bg-gradient-to-br from-brand/60 to-violet-ai/60 flex items-center justify-center flex-shrink-0">
                  <span className="text-white text-sm font-bold">{m.username[0].toUpperCase()}</span>
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-text-primary">{m.username}</p>
                  <p className="text-xs text-text-muted">{m.email}</p>
                </div>
                <span className={roleBadge(m.team_role)}>
                  {roleIcon(m.team_role)}
                  {m.team_role}
                </span>
                <button
                  onClick={() => setRemoveTarget(m)}
                  className="p-1.5 rounded-md text-text-muted hover:text-danger hover:bg-danger/10 transition-colors"
                  title="Remove member"
                >
                  <UserMinus size={14} />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      <AddMemberModal
        open={showAdd}
        onClose={() => setShowAdd(false)}
        teamId={teamId}
        onAdded={load}
      />

      <Modal open={!!removeTarget} onClose={() => setRemoveTarget(null)} title="Remove Member">
        <p className="text-sm text-text-secondary mb-5">
          Remove <span className="text-text-primary font-medium">{removeTarget?.username}</span> from this team?
        </p>
        <div className="flex justify-end gap-2">
          <button className="btn-secondary" onClick={() => setRemoveTarget(null)}>Cancel</button>
          <button className="btn-danger" onClick={handleRemove}>Remove</button>
        </div>
      </Modal>
    </div>
  )
}

function AddMemberModal({
  open, onClose, teamId, onAdded,
}: {
  open: boolean
  onClose: () => void
  teamId: number
  onAdded: () => void
}) {
  const [users, setUsers] = useState<AdminUser[]>([])
  const [selected, setSelected] = useState<AdminUser | null>(null)
  const [role, setRole] = useState('member')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const [search, setSearch] = useState('')

  useEffect(() => {
    if (open) {
      getAdminUsers().then(setUsers).catch(() => {})
    }
  }, [open])

  const filtered = users.filter(
    (u) =>
      u.username.toLowerCase().includes(search.toLowerCase()) ||
      u.email.toLowerCase().includes(search.toLowerCase())
  )

  const handleAdd = async () => {
    if (!selected) return
    setLoading(true)
    setError('')
    try {
      await addTeamMember(teamId, selected.id, role)
      onAdded()
      onClose()
      setSelected(null)
      setSearch('')
    } catch (err: unknown) {
      setError(
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Failed to add member'
      )
    } finally {
      setLoading(false)
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="Add Team Member">
      <div className="space-y-4">
        {/* User picker */}
        <div>
          <label className="label">User</label>
          <div className="relative">
            <button
              onClick={() => setDropdownOpen(!dropdownOpen)}
              className="input flex items-center justify-between"
            >
              <span className={selected ? 'text-text-primary' : 'text-text-muted'}>
                {selected ? `${selected.username} (${selected.email})` : 'Select a user…'}
              </span>
              <ChevronDown size={14} className="text-text-muted flex-shrink-0" />
            </button>
            {dropdownOpen && (
              <div className="absolute top-full left-0 right-0 mt-1 bg-bg-surface border border-border rounded-lg shadow-xl z-50 overflow-hidden">
                <div className="p-2 border-b border-border">
                  <input
                    autoFocus
                    className="input text-xs py-1.5"
                    placeholder="Search users…"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                  />
                </div>
                <div className="max-h-48 overflow-y-auto">
                  {filtered.map((u) => (
                    <button
                      key={u.id}
                      onClick={() => { setSelected(u); setDropdownOpen(false) }}
                      className="w-full flex items-center gap-2 px-3 py-2 hover:bg-bg-elevated text-left text-sm transition-colors"
                    >
                      <div className="w-6 h-6 rounded-full bg-gradient-to-br from-brand to-violet-ai flex items-center justify-center flex-shrink-0">
                        <span className="text-white text-[10px] font-bold">{u.username[0].toUpperCase()}</span>
                      </div>
                      <div>
                        <p className="text-text-primary">{u.username}</p>
                        <p className="text-xs text-text-muted">{u.email}</p>
                      </div>
                      {selected?.id === u.id && <Check size={13} className="text-brand ml-auto" />}
                    </button>
                  ))}
                  {filtered.length === 0 && (
                    <p className="text-xs text-text-muted text-center py-4">No users found</p>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Role picker */}
        <div>
          <label className="label">Role</label>
          <select className="input" value={role} onChange={(e) => setRole(e.target.value)}>
            <option value="manager">Manager — can ingest docs, manage members, request models</option>
            <option value="member">Member — can chat and generate documents</option>
            <option value="viewer">Viewer — can chat only</option>
          </select>
        </div>

        {error && <p className="text-sm text-danger bg-danger/10 border border-danger/30 px-3 py-2 rounded-lg">⚠ {error}</p>}

        <div className="flex justify-end gap-2 pt-1">
          <button className="btn-secondary" onClick={onClose}>Cancel</button>
          <button className="btn-primary" onClick={handleAdd} disabled={!selected || loading}>
            {loading ? <><Spinner size="sm" />Adding…</> : <><UserPlus size={13} />Add Member</>}
          </button>
        </div>
      </div>
    </Modal>
  )
}

/* ── Ingest Tab ── */
function IngestTab({ teamId, teamName }: { teamId: number; teamName: string }) {
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<string | null>(null)
  const [error, setError] = useState('')

  const handleIngest = async () => {
    setLoading(true)
    setResult(null)
    setError('')
    try {
      const res = await ingestTeamDocs(teamId)
      setResult(res.message)
    } catch (err: unknown) {
      setError(
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Ingestion failed'
      )
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="px-6 py-6 max-w-2xl mx-auto space-y-6">
      <div className="card space-y-5">
        <div className="flex items-start gap-4">
          <div className="w-11 h-11 rounded-xl bg-brand/10 border border-brand/20 flex items-center justify-center flex-shrink-0">
            <Upload size={20} className="text-brand" />
          </div>
          <div>
            <h2 className="text-sm font-semibold text-text-primary">Document Ingestion</h2>
            <p className="text-xs text-text-secondary mt-0.5">
              Process all documents in <span className="font-medium text-text-primary">{teamName}</span>'s docs folder.
              Supports PDF, DOCX, TXT, and Markdown. Only new or changed files are re-processed.
            </p>
          </div>
        </div>

        <div className="bg-bg-elevated rounded-lg p-4 border border-border space-y-2 text-xs text-text-secondary">
          <p className="font-medium text-text-primary text-xs uppercase tracking-wide">What happens during ingestion</p>
          {[
            'Documents are split into overlapping 1,000-character chunks',
            'Each chunk is embedded using your configured embedding model',
            'Vectors are stored in ChromaDB for semantic search',
            'A BM25 keyword index is rebuilt for hybrid retrieval',
            'File hashes are cached — unchanged files are skipped',
          ].map((step, i) => (
            <div key={i} className="flex items-start gap-2">
              <span className="w-4 h-4 rounded-full bg-brand/20 text-brand text-[10px] font-bold flex items-center justify-center flex-shrink-0 mt-0.5">
                {i + 1}
              </span>
              {step}
            </div>
          ))}
        </div>

        {result && (
          <div className="flex items-center gap-2 px-3 py-2.5 rounded-lg bg-success/10 border border-success/30 text-success text-sm animate-fade-in">
            <Check size={15} className="flex-shrink-0" />
            {result}
          </div>
        )}
        {error && (
          <div className="px-3 py-2.5 rounded-lg bg-danger/10 border border-danger/30 text-danger text-sm">
            ⚠ {error}
          </div>
        )}

        <button
          onClick={handleIngest}
          disabled={loading}
          className="btn-primary w-full justify-center py-2.5"
        >
          {loading ? (
            <><Spinner size="sm" /><span>Ingesting documents…</span></>
          ) : (
            <><RefreshCw size={15} /><span>Start Ingestion</span></>
          )}
        </button>
      </div>
    </div>
  )
}

/* ── Stats Tab ── */
function StatsTab({ teamId }: { teamId: number }) {
  const [stats, setStats] = useState<TeamStats | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    getTeamStats(teamId)
      .then(setStats)
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [teamId])

  if (loading) {
    return <div className="flex justify-center py-16"><Spinner size="lg" /></div>
  }

  return (
    <div className="px-6 py-6 max-w-2xl mx-auto space-y-4">
      <h2 className="text-sm font-semibold text-text-primary">Vector Store Stats</h2>
      <div className="grid grid-cols-2 gap-4">
        <div className="card flex items-center gap-4">
          <div className="w-10 h-10 rounded-xl bg-brand/10 flex items-center justify-center">
            <BarChart2 size={18} className="text-brand" />
          </div>
          <div>
            <p className="text-2xl font-bold text-text-primary">{stats?.doc_count ?? 0}</p>
            <p className="text-xs text-text-secondary">Vector Documents</p>
          </div>
        </div>
        <div className="card flex items-center gap-4">
          <div className="w-10 h-10 rounded-xl bg-violet-ai/10 flex items-center justify-center">
            <Settings2 size={18} className="text-violet-ai" />
          </div>
          <div>
            <p className="text-sm font-mono font-medium text-text-primary truncate max-w-[140px]" title={stats?.collection_name}>
              {stats?.collection_name ?? '—'}
            </p>
            <p className="text-xs text-text-secondary">Collection Name</p>
          </div>
        </div>
      </div>
      {stats && stats.doc_count === 0 && (
        <div className="card border-warning/30 bg-warning/5 text-sm text-warning flex items-start gap-2">
          <span className="mt-0.5">⚠</span>
          No documents indexed yet. Go to the Ingest tab to process your team's documents.
        </div>
      )}
    </div>
  )
}

// Re-export formatDate to avoid unused import warning
const _unused = formatDate
void _unused
