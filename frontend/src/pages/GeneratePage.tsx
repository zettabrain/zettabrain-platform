import { useState, useEffect, useRef } from 'react'
import {
  Sparkles,
  FileText,
  Download,
  Upload,
  Trash2,
  Clock,
  ChevronRight,
  Tag,
  Database,
  Plus,
  X,
  Check,
  BookOpen,
  History,
} from 'lucide-react'
import TopBar from '../components/TopBar'
import Spinner from '../components/Spinner'
import EmptyState from '../components/EmptyState'
import Modal from '../components/Modal'
import { useTeam } from '../context/TeamContext'
import {
  getSkills,
  generate,
  getGenerationHistory,
  getPdfDownloadUrl,
  uploadSkill,
  deleteSkill,
  type Skill,
  type GenerationResult,
  type GenerationHistoryItem,
} from '../api/generate'
import { cn, formatDateTime } from '../lib/utils'

type Tab = 'generate' | 'history'

export default function GeneratePage() {
  const { activeTeam } = useTeam()
  const [tab, setTab] = useState<Tab>('generate')
  const [skills, setSkills] = useState<Skill[]>([])
  const [skillsLoading, setSkillsLoading] = useState(false)
  const [selectedSkill, setSelectedSkill] = useState<Skill | null>(null)
  const [request, setRequest] = useState('')
  const [temperature, setTemperature] = useState(0.7)
  const [maxTokens, setMaxTokens] = useState(2000)
  const [generating, setGenerating] = useState(false)
  const [result, setResult] = useState<GenerationResult | null>(null)
  const [error, setError] = useState('')
  const [history, setHistory] = useState<GenerationHistoryItem[]>([])
  const [historyLoading, setHistoryLoading] = useState(false)
  const [showUpload, setShowUpload] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<Skill | null>(null)
  const outputRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!activeTeam) return
    loadSkills()
  }, [activeTeam?.id])

  useEffect(() => {
    if (tab === 'history') loadHistory()
  }, [tab, activeTeam?.id])

  useEffect(() => {
    if (result) outputRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [result])

  const loadSkills = async () => {
    if (!activeTeam) return
    setSkillsLoading(true)
    try {
      const data = await getSkills(activeTeam.id)
      setSkills(data)
      if (!selectedSkill && data.length > 0) setSelectedSkill(data[0])
    } catch { /* ignore */ }
    finally { setSkillsLoading(false) }
  }

  const loadHistory = async () => {
    if (!activeTeam) return
    setHistoryLoading(true)
    try {
      const data = await getGenerationHistory(activeTeam.id)
      setHistory(data)
    } catch { /* ignore */ }
    finally { setHistoryLoading(false) }
  }

  const handleGenerate = async () => {
    if (!activeTeam || !selectedSkill || !request.trim()) return
    setGenerating(true)
    setError('')
    setResult(null)
    try {
      const res = await generate(
        activeTeam.id,
        selectedSkill.name,
        request.trim(),
        {},
        { temperature, max_tokens: maxTokens }
      )
      setResult(res)
    } catch (err: unknown) {
      setError(
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        'Generation failed. Please try again.'
      )
    } finally {
      setGenerating(false)
    }
  }

  const handleDeleteSkill = async () => {
    if (!activeTeam || !deleteTarget) return
    try {
      await deleteSkill(activeTeam.id, deleteTarget.name)
      setDeleteTarget(null)
      if (selectedSkill?.name === deleteTarget.name) setSelectedSkill(null)
      loadSkills()
    } catch { /* ignore */ }
  }

  return (
    <div className="flex flex-col h-screen">
      <TopBar
        title="Generate"
        subtitle="AI-powered document generation"
        actions={
          <div className="flex gap-1">
            {(['generate', 'history'] as Tab[]).map((t) => (
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
                {t === 'generate' ? <span className="flex items-center gap-1.5"><Sparkles size={12} />Generate</span>
                  : <span className="flex items-center gap-1.5"><History size={12} />History</span>}
              </button>
            ))}
          </div>
        }
      />

      {tab === 'generate' ? (
        <div className="flex flex-1 overflow-hidden">
          {/* ── Left: Skill list ── */}
          <aside className="w-64 border-r border-border bg-bg-surface flex flex-col flex-shrink-0 overflow-hidden">
            <div className="px-4 py-3 border-b border-border flex items-center justify-between">
              <p className="text-xs font-semibold text-text-muted uppercase tracking-widest">Skills</p>
              <button
                onClick={() => setShowUpload(true)}
                title="Upload skill"
                className="p-1.5 rounded-md text-text-muted hover:text-brand hover:bg-brand/10 transition-colors"
              >
                <Plus size={14} />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto py-2">
              {skillsLoading ? (
                <div className="flex justify-center py-8"><Spinner /></div>
              ) : skills.length === 0 ? (
                <EmptyState icon={BookOpen} title="No skills" description="Upload a .md skill file to get started" />
              ) : (
                skills.map((skill) => (
                  <SkillItem
                    key={skill.name}
                    skill={skill}
                    active={selectedSkill?.name === skill.name}
                    onSelect={() => { setSelectedSkill(skill); setResult(null); setError('') }}
                    onDelete={() => setDeleteTarget(skill)}
                  />
                ))
              )}
            </div>
          </aside>

          {/* ── Right: Form + Output ── */}
          <div className="flex-1 overflow-y-auto">
            {!activeTeam ? (
              <EmptyState icon={Sparkles} title="No team selected" description="Select a team from the sidebar to use skills" className="h-full" />
            ) : !selectedSkill ? (
              <EmptyState icon={Sparkles} title="Select a skill" description="Choose a skill from the list to begin" className="h-full" />
            ) : (
              <div className="max-w-3xl mx-auto px-6 py-6 space-y-6">
                {/* Skill header */}
                <SkillHeader skill={selectedSkill} />

                {/* Request form */}
                <div className="card space-y-5">
                  <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
                    <FileText size={15} className="text-brand" />
                    Request Details
                  </h3>

                  <div>
                    <label className="label">What should this document cover?</label>
                    <textarea
                      value={request}
                      onChange={(e) => setRequest(e.target.value)}
                      placeholder={`e.g. "Q3 engineering results focusing on infrastructure reliability improvements…"`}
                      rows={4}
                      className="input resize-none leading-relaxed"
                    />
                  </div>

                  {/* Options */}
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="label flex items-center justify-between">
                        Temperature
                        <span className="font-mono text-brand normal-case">{temperature.toFixed(1)}</span>
                      </label>
                      <input
                        type="range"
                        min={0}
                        max={1}
                        step={0.1}
                        value={temperature}
                        onChange={(e) => setTemperature(Number(e.target.value))}
                        className="w-full accent-blue-500 cursor-pointer"
                      />
                      <div className="flex justify-between text-[10px] text-text-muted mt-0.5">
                        <span>Precise</span><span>Creative</span>
                      </div>
                    </div>
                    <div>
                      <label className="label flex items-center justify-between">
                        Max Tokens
                        <span className="font-mono text-brand normal-case">{maxTokens.toLocaleString()}</span>
                      </label>
                      <input
                        type="range"
                        min={500}
                        max={4000}
                        step={100}
                        value={maxTokens}
                        onChange={(e) => setMaxTokens(Number(e.target.value))}
                        className="w-full accent-blue-500 cursor-pointer"
                      />
                      <div className="flex justify-between text-[10px] text-text-muted mt-0.5">
                        <span>500</span><span>4,000</span>
                      </div>
                    </div>
                  </div>

                  {error && (
                    <div className="px-3 py-2.5 rounded-lg bg-danger/10 border border-danger/30 text-danger text-sm">
                      ⚠ {error}
                    </div>
                  )}

                  <button
                    onClick={handleGenerate}
                    disabled={generating || !request.trim()}
                    className="btn-primary w-full justify-center py-2.5"
                  >
                    {generating ? (
                      <><Spinner size="sm" /><span>Generating…</span></>
                    ) : (
                      <><Sparkles size={15} /><span>Generate Document</span></>
                    )}
                  </button>
                </div>

                {/* Output */}
                {generating && (
                  <div className="card flex items-center gap-4 py-8 justify-center" ref={outputRef}>
                    <Spinner />
                    <p className="text-sm text-text-secondary animate-pulse">
                      Analysing corpus and generating document…
                    </p>
                  </div>
                )}

                {result && !generating && (
                  <GenerationOutput result={result} teamId={activeTeam.id} ref={outputRef} />
                )}
              </div>
            )}
          </div>
        </div>
      ) : (
        /* ── History tab ── */
        <div className="flex-1 overflow-y-auto px-6 py-6">
          {historyLoading ? (
            <div className="flex justify-center py-20"><Spinner size="lg" /></div>
          ) : history.length === 0 ? (
            <EmptyState
              icon={History}
              title="No generations yet"
              description="Your generated documents will appear here"
              className="h-full"
            />
          ) : (
            <div className="max-w-4xl mx-auto space-y-3">
              <p className="text-xs text-text-muted uppercase tracking-widest font-semibold mb-4">
                {history.length} document{history.length !== 1 ? 's' : ''} generated
              </p>
              {history.map((item) => (
                <HistoryCard key={item.id} item={item} teamId={activeTeam?.id ?? 0} />
              ))}
            </div>
          )}
        </div>
      )}

      {/* Upload modal */}
      <UploadSkillModal
        open={showUpload}
        onClose={() => setShowUpload(false)}
        teamId={activeTeam?.id ?? 0}
        onUploaded={loadSkills}
      />

      {/* Delete confirm modal */}
      <Modal
        open={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        title="Delete skill"
      >
        <p className="text-sm text-text-secondary mb-5">
          Are you sure you want to delete the <span className="text-text-primary font-medium">{deleteTarget?.name}</span> skill?
          This cannot be undone.
        </p>
        <div className="flex justify-end gap-2">
          <button className="btn-secondary" onClick={() => setDeleteTarget(null)}>Cancel</button>
          <button className="btn-danger" onClick={handleDeleteSkill}>Delete</button>
        </div>
      </Modal>
    </div>
  )
}

/* ── Skill list item ── */
function SkillItem({
  skill, active, onSelect, onDelete,
}: {
  skill: Skill
  active: boolean
  onSelect: () => void
  onDelete: () => void
}) {
  const sourceColors: Record<string, string> = {
    builtin: 'text-violet-ai',
    global: 'text-brand',
    team: 'text-success',
  }

  return (
    <div
      onClick={onSelect}
      className={cn(
        'group flex items-start gap-2.5 px-4 py-3 cursor-pointer hover:bg-bg-elevated transition-colors',
        active && 'bg-brand/5 border-r-2 border-brand'
      )}
    >
      <div className={cn(
        'w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 mt-0.5',
        active ? 'bg-brand/20' : 'bg-bg-elevated'
      )}>
        <Sparkles size={13} className={active ? 'text-brand' : 'text-text-muted'} />
      </div>
      <div className="flex-1 min-w-0">
        <p className={cn('text-sm font-medium truncate', active ? 'text-brand' : 'text-text-primary')}>
          {skill.name}
        </p>
        <p className="text-xs text-text-muted truncate">{skill.description}</p>
        <div className="flex items-center gap-1 mt-1">
          <span className={cn('text-[10px] font-medium capitalize', sourceColors[skill.source] ?? 'text-text-muted')}>
            {skill.source}
          </span>
          {skill.requires_corpus && (
            <span className="flex items-center gap-0.5 text-[10px] text-text-muted ml-1">
              <Database size={9} />corpus
            </span>
          )}
        </div>
      </div>
      {skill.source === 'team' && (
        <button
          onClick={(e) => { e.stopPropagation(); onDelete() }}
          className="opacity-0 group-hover:opacity-100 p-1 rounded text-text-muted hover:text-danger transition-all"
        >
          <Trash2 size={12} />
        </button>
      )}
    </div>
  )
}

/* ── Skill header card ── */
function SkillHeader({ skill }: { skill: Skill }) {
  return (
    <div className="flex items-start gap-4">
      <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-brand/20 to-violet-ai/20 border border-brand/20 flex items-center justify-center flex-shrink-0">
        <Sparkles size={20} className="text-brand" />
      </div>
      <div className="flex-1">
        <h2 className="text-lg font-bold text-text-primary capitalize">{skill.name}</h2>
        <p className="text-sm text-text-secondary mt-0.5">{skill.description}</p>
        <div className="flex flex-wrap gap-1.5 mt-2">
          {skill.tags.map((tag) => (
            <span key={tag} className="badge bg-bg-elevated border border-border text-text-muted">
              <Tag size={9} />{tag}
            </span>
          ))}
          {skill.requires_corpus && (
            <span className="badge bg-success/10 border border-success/20 text-success">
              <Database size={9} />corpus-grounded
            </span>
          )}
          <span className="badge bg-bg-elevated border border-border text-text-muted font-mono">
            v{skill.version}
          </span>
        </div>
      </div>
    </div>
  )
}

/* ── Generation output ── */
const GenerationOutput = function GenerationOutput({
  result,
  teamId,
  ref,
}: {
  result: GenerationResult
  teamId: number
  ref: React.RefObject<HTMLDivElement>
}) {
  const [copied, setCopied] = useState(false)

  const handleCopy = () => {
    navigator.clipboard.writeText(result.content)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="card space-y-4 animate-slide-up" ref={ref}>
      {/* Output header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Check size={16} className="text-success" />
          <h3 className="text-sm font-semibold text-text-primary">Generated Document</h3>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-text-muted flex items-center gap-1">
            <Clock size={11} />
            {(result.duration_ms / 1000).toFixed(1)}s
          </span>
          <button onClick={handleCopy} className="btn-ghost text-xs py-1.5">
            {copied ? <><Check size={13} className="text-success" />Copied</> : 'Copy'}
          </button>
          <a
            href={getPdfDownloadUrl(teamId, parseInt(result.id))}
            target="_blank"
            rel="noopener noreferrer"
            className="btn-secondary text-xs py-1.5"
          >
            <Download size={13} />PDF
          </a>
        </div>
      </div>

      {/* Content */}
      <div className="bg-bg-elevated rounded-lg p-5 border border-border">
        <pre className="text-sm text-text-primary font-sans leading-relaxed whitespace-pre-wrap">
          {result.content}
        </pre>
      </div>

      {/* Citations */}
      {result.citations.length > 0 && (
        <div>
          <p className="text-xs font-medium text-text-muted uppercase tracking-wide mb-2">Citations</p>
          <div className="space-y-1">
            {result.citations.map((c, i) => (
              <div key={i} className="flex items-center gap-2 text-xs text-text-secondary">
                <FileText size={11} className="text-brand flex-shrink-0" />
                {c}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

/* ── History card ── */
function HistoryCard({ item, teamId }: { item: GenerationHistoryItem; teamId: number }) {
  return (
    <div className="card flex items-start gap-4 hover:border-border-subtle transition-colors">
      <div className="w-9 h-9 rounded-lg bg-violet-ai/10 border border-violet-ai/20 flex items-center justify-center flex-shrink-0">
        <Sparkles size={16} className="text-violet-ai" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-sm font-medium text-text-primary capitalize">{item.skill_name}</p>
            <p className="text-xs text-text-secondary mt-0.5 line-clamp-2">{item.request_summary}</p>
          </div>
          <a
            href={getPdfDownloadUrl(teamId, item.id)}
            target="_blank"
            rel="noopener noreferrer"
            className="btn-ghost text-xs py-1 flex-shrink-0"
          >
            <Download size={13} />PDF
          </a>
        </div>
        <div className="flex items-center gap-3 mt-2">
          <span className="text-xs text-text-muted flex items-center gap-1">
            <Clock size={11} />{formatDateTime(item.created_at)}
          </span>
          <span className="text-xs text-text-muted font-mono">{item.model}</span>
          <span className="text-xs text-text-muted">{(item.duration_ms / 1000).toFixed(1)}s</span>
        </div>
      </div>
    </div>
  )
}

/* ── Upload skill modal ── */
function UploadSkillModal({
  open,
  onClose,
  teamId,
  onUploaded,
}: {
  open: boolean
  onClose: () => void
  teamId: number
  onUploaded: () => void
}) {
  const [file, setFile] = useState<File | null>(null)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  const handleUpload = async () => {
    if (!file) return
    setUploading(true)
    setError('')
    setSuccess('')
    try {
      const res = await uploadSkill(teamId, file)
      setSuccess(res.message ?? 'Skill uploaded successfully')
      setFile(null)
      onUploaded()
      setTimeout(onClose, 1500)
    } catch (err: unknown) {
      setError(
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        'Upload failed'
      )
    } finally {
      setUploading(false)
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="Upload Custom Skill">
      <div className="space-y-4">
        <p className="text-sm text-text-secondary">
          Upload a <code className="font-mono text-brand text-xs">.md</code> file with YAML frontmatter to add a custom skill to this team.
        </p>

        {/* Drop zone */}
        <div
          onClick={() => inputRef.current?.click()}
          className={cn(
            'border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors',
            file ? 'border-success/50 bg-success/5' : 'border-border hover:border-brand/50 hover:bg-brand/5'
          )}
        >
          <input
            ref={inputRef}
            type="file"
            accept=".md"
            className="hidden"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
          {file ? (
            <div className="flex items-center justify-center gap-2 text-success">
              <Check size={18} />
              <span className="text-sm font-medium">{file.name}</span>
              <button
                onClick={(e) => { e.stopPropagation(); setFile(null) }}
                className="p-0.5 rounded hover:bg-bg-elevated"
              >
                <X size={14} />
              </button>
            </div>
          ) : (
            <>
              <Upload size={24} className="mx-auto text-text-muted mb-2" />
              <p className="text-sm text-text-secondary">Click to select a <code className="font-mono text-xs">.md</code> skill file</p>
            </>
          )}
        </div>

        {error && (
          <p className="text-sm text-danger bg-danger/10 border border-danger/30 px-3 py-2 rounded-lg">⚠ {error}</p>
        )}
        {success && (
          <p className="text-sm text-success bg-success/10 border border-success/30 px-3 py-2 rounded-lg flex items-center gap-2">
            <Check size={14} />{success}
          </p>
        )}

        <div className="flex justify-end gap-2 pt-1">
          <button className="btn-secondary" onClick={onClose}>Cancel</button>
          <button
            className="btn-primary"
            onClick={handleUpload}
            disabled={!file || uploading}
          >
            {uploading ? <><Spinner size="sm" />Uploading…</> : <><Upload size={14} />Upload Skill</>}
          </button>
        </div>
      </div>
    </Modal>
  )
}
