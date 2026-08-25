import { useState, useEffect } from 'react'
import {
  Users,
  Building2,
  MessageSquare,
  HardDrive,
  CheckCircle,
  XCircle,
  AlertCircle,
  ShieldCheck,
  Clock,
  Cpu,
  BarChart3,
  RefreshCw,
  UserPlus,
  Trash2,
  ToggleLeft,
  ToggleRight,
  Eye,
  EyeOff,
} from 'lucide-react'
import TopBar from '../components/TopBar'
import Spinner from '../components/Spinner'
import Modal from '../components/Modal'
import { cn, formatDateTime, confidenceColor } from '../lib/utils'
import {
  getAdminStats,
  getAuditLog,
  getHealth,
  getAdminUsers,
  createUser,
  updateUser,
  deleteUser,
  verifyProvenance,
  type AdminStats,
  type AuditLogEntry,
  type HealthStatus,
  type AdminUser,
} from '../api/admin'

type Tab = 'overview' | 'audit' | 'users'

export default function AdminDashboard() {
  const [tab, setTab] = useState<Tab>('overview')

  return (
    <div className="flex flex-col h-screen">
      <TopBar
        title="Admin Dashboard"
        subtitle="Platform management"
        actions={
          <div className="flex gap-1">
            {(['overview', 'audit', 'users'] as Tab[]).map((t) => (
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
        {tab === 'overview' && <OverviewTab />}
        {tab === 'audit' && <AuditTab />}
        {tab === 'users' && <UsersTab />}
      </div>
    </div>
  )
}

/* ═══════════════════════════════════════════
   OVERVIEW TAB
═══════════════════════════════════════════ */
function OverviewTab() {
  const [stats, setStats] = useState<AdminStats | null>(null)
  const [health, setHealth] = useState<HealthStatus | null>(null)
  const [loading, setLoading] = useState(true)

  const load = async () => {
    setLoading(true)
    try {
      const [s, h] = await Promise.all([getAdminStats(), getHealth()])
      setStats(s)
      setHealth(h)
    } catch { /* ignore */ }
    finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  if (loading) {
    return (
      <div className="flex justify-center py-24"><Spinner size="lg" /></div>
    )
  }

  const licensePercent = stats?.license?.days_remaining != null && stats.license.expires_at
    ? Math.min(100, Math.round((stats.license.days_remaining / 365) * 100))
    : null

  return (
    <div className="px-6 py-6 space-y-6 max-w-6xl mx-auto">
      {/* Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          icon={Users}
          label="Users"
          value={stats?.total_users ?? 0}
          sub={stats?.license ? `of ${stats.license.max_users} seats` : undefined}
          iconClass="text-brand"
          iconBg="bg-brand/10"
        />
        <StatCard
          icon={Building2}
          label="Teams"
          value={stats?.total_teams ?? 0}
          sub={stats?.license ? `of ${stats.license.max_teams} allowed` : undefined}
          iconClass="text-violet-ai"
          iconBg="bg-violet-ai/10"
        />
        <StatCard
          icon={MessageSquare}
          label="Queries This Month"
          value={stats?.queries_this_month ?? 0}
          sub={`${stats?.total_queries ?? 0} total`}
          iconClass="text-success"
          iconBg="bg-success/10"
        />
        <StatCard
          icon={HardDrive}
          label="Disk Usage"
          value={health ? `${health.disk_usage_gb.toFixed(1)} GB` : '—'}
          sub={health ? `${health.disk_free_gb.toFixed(1)} GB free` : undefined}
          iconClass="text-warning"
          iconBg="bg-warning/10"
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Model Health */}
        <div className="card space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-text-primary flex items-center gap-2">
              <Cpu size={15} className="text-brand" />
              Model Health
            </h2>
            <button onClick={load} className="p-1.5 rounded-md text-text-muted hover:text-brand hover:bg-brand/10 transition-colors">
              <RefreshCw size={13} />
            </button>
          </div>
          {health ? (
            <div className="space-y-3">
              {[
                { name: 'Ollama', status: health.ollama },
                { name: 'OpenAI', status: health.openai },
                { name: 'Claude', status: health.claude },
              ].map(({ name, status }) => (
                <HealthRow key={name} name={name} status={status} />
              ))}
            </div>
          ) : (
            <p className="text-sm text-text-muted">Unable to load health status</p>
          )}

          {/* Team doc counts */}
          {health && Object.keys(health.team_doc_counts).length > 0 && (
            <div className="pt-3 border-t border-border">
              <p className="text-xs font-semibold text-text-muted uppercase tracking-wide mb-2">Vector Docs per Team</p>
              <div className="space-y-1.5">
                {Object.entries(health.team_doc_counts).map(([team, count]) => (
                  <div key={team} className="flex items-center justify-between text-xs">
                    <span className="text-text-secondary">{team}</span>
                    <span className="font-mono text-brand">{count.toLocaleString()}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* License */}
        <div className="card space-y-4">
          <h2 className="text-sm font-semibold text-text-primary flex items-center gap-2">
            <ShieldCheck size={15} className="text-success" />
            License
          </h2>
          {stats?.license ? (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <InfoPill label="Plan" value={stats.license.plan} />
                <InfoPill label="State" value={stats.license.state} highlight />
                <InfoPill label="Max Users" value={String(stats.license.max_users)} />
                <InfoPill label="Max Teams" value={String(stats.license.max_teams)} />
              </div>
              {stats.license.expires_at && (
                <div>
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="text-xs text-text-muted">Expires</span>
                    <span className="text-xs font-medium text-text-primary">
                      {new Date(stats.license.expires_at).toLocaleDateString('en-US', {
                        month: 'short', day: 'numeric', year: 'numeric',
                      })}
                      {stats.license.days_remaining != null && (
                        <span className="ml-1.5 text-text-muted">· {stats.license.days_remaining}d remaining</span>
                      )}
                    </span>
                  </div>
                  {licensePercent != null && (
                    <div className="h-2 bg-bg-elevated rounded-full overflow-hidden">
                      <div
                        className={cn(
                          'h-full rounded-full transition-all',
                          licensePercent > 30 ? 'bg-success' : licensePercent > 10 ? 'bg-warning' : 'bg-danger'
                        )}
                        style={{ width: `${licensePercent}%` }}
                      />
                    </div>
                  )}
                </div>
              )}
            </div>
          ) : (
            <p className="text-sm text-text-muted">No license information available</p>
          )}
        </div>
      </div>

      {/* Seat usage bar */}
      {stats && (
        <div className="card">
          <h2 className="text-sm font-semibold text-text-primary mb-4 flex items-center gap-2">
            <BarChart3 size={15} className="text-brand" />
            Seat Utilisation
          </h2>
          <div className="flex items-center gap-4">
            <div className="flex-1">
              <div className="h-3 bg-bg-elevated rounded-full overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-brand to-violet-ai rounded-full transition-all"
                  style={{
                    width: `${Math.min(100, (stats.total_users / (stats.license?.max_users || 1)) * 100)}%`,
                  }}
                />
              </div>
            </div>
            <span className="text-sm font-mono text-text-primary whitespace-nowrap">
              {stats.total_users} / {stats.license?.max_users ?? '∞'}
            </span>
          </div>
          <div className="flex gap-6 mt-3">
            <Metric label="Active Users" value={stats.active_users} />
            <Metric label="Inactive" value={stats.total_users - stats.active_users} />
          </div>
        </div>
      )}
    </div>
  )
}

function StatCard({
  icon: Icon, label, value, sub, iconClass, iconBg,
}: {
  icon: React.ElementType
  label: string
  value: string | number
  sub?: string
  iconClass: string
  iconBg: string
}) {
  return (
    <div className="card flex items-start gap-4">
      <div className={cn('w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0', iconBg)}>
        <Icon size={18} className={iconClass} />
      </div>
      <div>
        <p className="text-2xl font-bold text-text-primary leading-none">{value}</p>
        <p className="text-xs font-medium text-text-secondary mt-0.5">{label}</p>
        {sub && <p className="text-[11px] text-text-muted mt-0.5">{sub}</p>}
      </div>
    </div>
  )
}

function HealthRow({ name, status }: { name: string; status: { status: string; message: string } }) {
  const icon =
    status.status === 'ok' ? <CheckCircle size={14} className="text-success" /> :
    status.status === 'unconfigured' ? <AlertCircle size={14} className="text-warning" /> :
    <XCircle size={14} className="text-danger" />

  const dotColor =
    status.status === 'ok' ? 'bg-success' :
    status.status === 'unconfigured' ? 'bg-warning' : 'bg-danger'

  return (
    <div className="flex items-center gap-3">
      <span className={cn('w-2 h-2 rounded-full flex-shrink-0', dotColor)} />
      <span className="text-sm font-medium text-text-primary w-20">{name}</span>
      {icon}
      <span className="text-xs text-text-muted truncate">{status.message}</span>
    </div>
  )
}

function InfoPill({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div className="bg-bg-elevated rounded-lg px-3 py-2 border border-border">
      <p className="text-[10px] text-text-muted uppercase tracking-wide">{label}</p>
      <p className={cn('text-sm font-semibold capitalize mt-0.5', highlight ? 'text-brand' : 'text-text-primary')}>
        {value}
      </p>
    </div>
  )
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <p className="text-lg font-bold text-text-primary">{value}</p>
      <p className="text-xs text-text-muted">{label}</p>
    </div>
  )
}

/* ═══════════════════════════════════════════
   AUDIT LOG TAB
═══════════════════════════════════════════ */
function AuditTab() {
  const [logs, setLogs] = useState<AuditLogEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [verifying, setVerifying] = useState<number | null>(null)
  const [verifyResult, setVerifyResult] = useState<{ id: number; valid: boolean; message: string } | null>(null)

  useEffect(() => {
    setLoading(true)
    getAuditLog({ limit: 100 })
      .then(setLogs)
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const handleVerify = async (logId: number) => {
    setVerifying(logId)
    try {
      const res = await verifyProvenance(logId)
      setVerifyResult({ id: logId, ...res })
    } catch {
      setVerifyResult({ id: logId, valid: false, message: 'Verification failed' })
    } finally {
      setVerifying(null)
    }
  }

  return (
    <div className="px-6 py-6 max-w-6xl mx-auto space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-text-primary">Audit Log</h2>
        <p className="text-xs text-text-muted">{logs.length} entries</p>
      </div>

      {loading ? (
        <div className="flex justify-center py-24"><Spinner size="lg" /></div>
      ) : (
        <div className="card p-0 overflow-hidden">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-border bg-bg-elevated">
                {['Time', 'User', 'Team', 'Query', 'Confidence', 'Model', 'Verified'].map((h) => (
                  <th key={h} className="text-left px-4 py-3 text-text-muted font-medium uppercase tracking-wide">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {logs.map((log) => (
                <tr key={log.id} className="hover:bg-bg-elevated/50 transition-colors">
                  <td className="px-4 py-3 text-text-muted whitespace-nowrap">
                    <span className="flex items-center gap-1">
                      <Clock size={11} />
                      {formatDateTime(log.created_at)}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-text-secondary font-medium">{log.username}</td>
                  <td className="px-4 py-3 text-text-secondary">{log.team_name}</td>
                  <td className="px-4 py-3 text-text-primary max-w-xs">
                    <p className="truncate" title={log.query}>{log.query}</p>
                    <p className="text-text-muted truncate">{log.answer_snippet}</p>
                  </td>
                  <td className="px-4 py-3">
                    <span className={cn('font-mono font-medium', confidenceColor(log.confidence))}>
                      {Math.round(log.confidence * 100)}%
                    </span>
                  </td>
                  <td className="px-4 py-3 text-text-muted font-mono">{log.model}</td>
                  <td className="px-4 py-3">
                    {log.provenance_sig ? (
                      <div className="flex items-center gap-2">
                        {verifyResult?.id === log.id ? (
                          <span className={cn(
                            'flex items-center gap-1 text-xs font-medium',
                            verifyResult.valid ? 'text-success' : 'text-danger'
                          )}>
                            {verifyResult.valid
                              ? <><CheckCircle size={12} />Valid</>
                              : <><XCircle size={12} />Invalid</>}
                          </span>
                        ) : (
                          <button
                            onClick={() => handleVerify(log.id)}
                            disabled={verifying === log.id}
                            className="flex items-center gap-1 text-text-muted hover:text-brand transition-colors"
                            title="Verify provenance signature"
                          >
                            {verifying === log.id
                              ? <Spinner size="sm" />
                              : <ShieldCheck size={13} />}
                          </button>
                        )}
                      </div>
                    ) : (
                      <span className="text-text-muted">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {logs.length === 0 && (
            <p className="text-center text-sm text-text-muted py-12">No audit entries yet</p>
          )}
        </div>
      )}
    </div>
  )
}

/* ═══════════════════════════════════════════
   USERS TAB
═══════════════════════════════════════════ */
function UsersTab() {
  const [users, setUsers] = useState<AdminUser[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<AdminUser | null>(null)

  const load = () => {
    setLoading(true)
    getAdminUsers()
      .then(setUsers)
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const handleToggleActive = async (user: AdminUser) => {
    try {
      await updateUser(user.id, { is_active: !user.is_active })
      load()
    } catch { /* ignore */ }
  }

  const handleDelete = async () => {
    if (!deleteTarget) return
    try {
      await deleteUser(deleteTarget.id)
      setDeleteTarget(null)
      load()
    } catch { /* ignore */ }
  }

  return (
    <div className="px-6 py-6 max-w-5xl mx-auto space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-text-primary">Users ({users.length})</h2>
        <button onClick={() => setShowCreate(true)} className="btn-primary text-xs py-2">
          <UserPlus size={13} />Add User
        </button>
      </div>

      {loading ? (
        <div className="flex justify-center py-24"><Spinner size="lg" /></div>
      ) : (
        <div className="card p-0 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-bg-elevated">
                {['User', 'Role', 'Status', 'Joined', ''].map((h) => (
                  <th key={h} className="text-left px-4 py-3 text-xs text-text-muted font-medium uppercase tracking-wide">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {users.map((user) => (
                <tr key={user.id} className="hover:bg-bg-elevated/40 transition-colors">
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-3">
                      <div className="w-7 h-7 rounded-full bg-gradient-to-br from-brand to-violet-ai flex items-center justify-center flex-shrink-0">
                        <span className="text-white text-xs font-bold">
                          {user.username[0].toUpperCase()}
                        </span>
                      </div>
                      <div>
                        <p className="text-text-primary font-medium">{user.username}</p>
                        <p className="text-xs text-text-muted">{user.email}</p>
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <span className={cn(
                      'badge capitalize',
                      user.system_role === 'admin'
                        ? 'bg-brand/10 border border-brand/20 text-brand'
                        : 'bg-bg-elevated border border-border text-text-secondary'
                    )}>
                      {user.system_role}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <button
                      onClick={() => handleToggleActive(user)}
                      className={cn(
                        'flex items-center gap-1.5 text-xs font-medium transition-colors',
                        user.is_active ? 'text-success hover:text-warning' : 'text-text-muted hover:text-success'
                      )}
                      title={user.is_active ? 'Deactivate user' : 'Activate user'}
                    >
                      {user.is_active
                        ? <><ToggleRight size={16} />Active</>
                        : <><ToggleLeft size={16} />Inactive</>}
                    </button>
                  </td>
                  <td className="px-4 py-3 text-xs text-text-muted">
                    {formatDateTime(user.created_at)}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      onClick={() => setDeleteTarget(user)}
                      className="p-1.5 rounded-md text-text-muted hover:text-danger hover:bg-danger/10 transition-colors"
                    >
                      <Trash2 size={14} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <CreateUserModal
        open={showCreate}
        onClose={() => setShowCreate(false)}
        onCreated={load}
      />

      <Modal open={!!deleteTarget} onClose={() => setDeleteTarget(null)} title="Delete User">
        <p className="text-sm text-text-secondary mb-5">
          Delete <span className="text-text-primary font-medium">{deleteTarget?.username}</span>? This cannot be undone.
        </p>
        <div className="flex justify-end gap-2">
          <button className="btn-secondary" onClick={() => setDeleteTarget(null)}>Cancel</button>
          <button className="btn-danger" onClick={handleDelete}>Delete User</button>
        </div>
      </Modal>
    </div>
  )
}

function CreateUserModal({
  open, onClose, onCreated,
}: {
  open: boolean
  onClose: () => void
  onCreated: () => void
}) {
  const [form, setForm] = useState({ username: '', email: '', password: '', system_role: 'user' })
  const [showPw, setShowPw] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async () => {
    setLoading(true)
    setError('')
    try {
      await createUser(form)
      setForm({ username: '', email: '', password: '', system_role: 'user' })
      onCreated()
      onClose()
    } catch (err: unknown) {
      setError(
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Failed to create user'
      )
    } finally {
      setLoading(false)
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="Add User">
      <div className="space-y-4">
        <div>
          <label className="label">Username</label>
          <input className="input" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} placeholder="jsmith" />
        </div>
        <div>
          <label className="label">Email</label>
          <input className="input" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} placeholder="j.smith@company.com" />
        </div>
        <div>
          <label className="label">Password</label>
          <div className="relative">
            <input
              className="input pr-10"
              type={showPw ? 'text' : 'password'}
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              placeholder="••••••••"
            />
            <button
              type="button"
              onClick={() => setShowPw(!showPw)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-secondary"
            >
              {showPw ? <EyeOff size={14} /> : <Eye size={14} />}
            </button>
          </div>
        </div>
        <div>
          <label className="label">Role</label>
          <select
            className="input"
            value={form.system_role}
            onChange={(e) => setForm({ ...form, system_role: e.target.value })}
          >
            <option value="user">User</option>
            <option value="admin">Admin</option>
          </select>
        </div>
        {error && <p className="text-sm text-danger bg-danger/10 border border-danger/30 px-3 py-2 rounded-lg">⚠ {error}</p>}
        <div className="flex justify-end gap-2 pt-1">
          <button className="btn-secondary" onClick={onClose}>Cancel</button>
          <button
            className="btn-primary"
            onClick={handleSubmit}
            disabled={loading || !form.username || !form.password}
          >
            {loading ? <><Spinner size="sm" />Creating…</> : <><UserPlus size={14} />Create User</>}
          </button>
        </div>
      </div>
    </Modal>
  )
}
