import { useState, useEffect } from 'react'
import { FolderOpen, Upload, RefreshCw, BarChart2, AlertTriangle, Check } from 'lucide-react'
import TopBar from '../components/TopBar'
import Spinner from '../components/Spinner'
import EmptyState from '../components/EmptyState'
import { useTeam } from '../context/TeamContext'
import { getTeamStats, ingestTeamDocs, type TeamStats } from '../api/teams'

export default function DocsPage() {
  const { activeTeam } = useTeam()
  const [stats, setStats] = useState<TeamStats | null>(null)
  const [loading, setLoading] = useState(false)
  const [ingesting, setIngesting] = useState(false)
  const [ingestMsg, setIngestMsg] = useState<string | null>(null)
  const [ingestError, setIngestError] = useState('')

  useEffect(() => {
    if (!activeTeam) return
    setLoading(true)
    getTeamStats(activeTeam.id)
      .then(setStats)
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [activeTeam?.id])

  const handleIngest = async () => {
    if (!activeTeam) return
    setIngesting(true)
    setIngestMsg(null)
    setIngestError('')
    try {
      const res = await ingestTeamDocs(activeTeam.id)
      setIngestMsg(res.message)
      // refresh stats
      const s = await getTeamStats(activeTeam.id)
      setStats(s)
    } catch (err: unknown) {
      setIngestError(
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Ingestion failed'
      )
    } finally {
      setIngesting(false)
    }
  }

  if (!activeTeam) {
    return (
      <div className="flex flex-col h-screen">
        <TopBar title="Documents" subtitle="Team document management" />
        <EmptyState
          icon={FolderOpen}
          title="No team selected"
          description="Select a team from the sidebar"
          className="flex-1"
        />
      </div>
    )
  }

  return (
    <div className="flex flex-col h-screen">
      <TopBar
        title="Documents"
        subtitle={`${activeTeam.name} knowledge base`}
        actions={
          <button
            onClick={handleIngest}
            disabled={ingesting}
            className="btn-primary text-xs py-2"
          >
            {ingesting ? <><Spinner size="sm" />Ingesting…</> : <><RefreshCw size={13} />Re-index</>}
          </button>
        }
      />
      <div className="flex-1 overflow-y-auto px-6 py-6">
        <div className="max-w-3xl mx-auto space-y-6">
          {/* Status messages */}
          {ingestMsg && (
            <div className="flex items-center gap-2 px-4 py-3 rounded-lg bg-success/10 border border-success/30 text-success text-sm animate-fade-in">
              <Check size={15} />{ingestMsg}
            </div>
          )}
          {ingestError && (
            <div className="flex items-center gap-2 px-4 py-3 rounded-lg bg-danger/10 border border-danger/30 text-danger text-sm">
              <AlertTriangle size={15} />{ingestError}
            </div>
          )}

          {/* Stats card */}
          {loading ? (
            <div className="flex justify-center py-16"><Spinner size="lg" /></div>
          ) : (
            <div className="grid grid-cols-2 gap-4">
              <div className="card flex items-center gap-4">
                <div className="w-10 h-10 rounded-xl bg-brand/10 flex items-center justify-center">
                  <BarChart2 size={18} className="text-brand" />
                </div>
                <div>
                  <p className="text-2xl font-bold text-text-primary">{stats?.doc_count ?? 0}</p>
                  <p className="text-xs text-text-secondary">Indexed Chunks</p>
                </div>
              </div>
              <div className="card flex items-center gap-4">
                <div className="w-10 h-10 rounded-xl bg-violet-ai/10 flex items-center justify-center">
                  <FolderOpen size={18} className="text-violet-ai" />
                </div>
                <div>
                  <p className="text-sm font-mono font-medium text-text-primary truncate max-w-[140px]" title={stats?.collection_name}>
                    {stats?.collection_name ?? '—'}
                  </p>
                  <p className="text-xs text-text-secondary">Collection</p>
                </div>
              </div>
            </div>
          )}

          {/* Info card */}
          <div className="card space-y-4">
            <div className="flex items-center gap-3">
              <Upload size={16} className="text-brand" />
              <h2 className="text-sm font-semibold text-text-primary">How to add documents</h2>
            </div>
            <ol className="space-y-3 text-sm text-text-secondary">
              {[
                { step: 1, text: 'Place your documents (PDF, DOCX, TXT, MD) in the team\'s configured docs folder on the server.' },
                { step: 2, text: 'Click Re-index above to process new and changed files.' },
                { step: 3, text: 'ZettaBrain will chunk, embed, and index the documents for semantic and keyword search.' },
                { step: 4, text: 'Switch to Chat to start asking questions against your indexed content.' },
              ].map(({ step, text }) => (
                <li key={step} className="flex items-start gap-3">
                  <span className="w-5 h-5 rounded-full bg-brand/20 text-brand text-xs font-bold flex items-center justify-center flex-shrink-0 mt-0.5">
                    {step}
                  </span>
                  {text}
                </li>
              ))}
            </ol>

            <div className="bg-bg-elevated rounded-lg px-4 py-3 border border-border text-xs text-text-secondary">
              <span className="text-text-muted font-medium">Docs folder: </span>
              <code className="font-mono text-brand">{activeTeam.docs_folder || '/opt/zettabrain-platform/docs/' + activeTeam.slug}</code>
            </div>
          </div>

          {/* No docs warning */}
          {!loading && stats && stats.doc_count === 0 && (
            <div className="card border-warning/30 bg-warning/5 flex items-start gap-3 text-sm text-warning">
              <AlertTriangle size={16} className="flex-shrink-0 mt-0.5" />
              <div>
                <p className="font-medium">No documents indexed</p>
                <p className="text-xs text-warning/80 mt-0.5">
                  Add documents to the docs folder and click Re-index to enable Chat and Generate features.
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
