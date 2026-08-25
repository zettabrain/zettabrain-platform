import { useState, useEffect } from 'react'
import {
  Settings,
  Save,
  Eye,
  EyeOff,
  Cpu,
  Globe,
  Key,
  Users,
  Server,
  RefreshCw,
  Check,
} from 'lucide-react'
import TopBar from '../components/TopBar'
import Spinner from '../components/Spinner'
import { getSystemConfig, updateSystemConfig, type SystemConfig } from '../api/admin'
import { cn } from '../lib/utils'

type SectionKey = 'llm' | 'embeddings' | 'cloud' | 'ldap' | 'system'

const SECTIONS: { key: SectionKey; label: string; icon: React.ElementType; fields: FieldDef[] }[] = [
  {
    key: 'llm',
    label: 'Language Model',
    icon: Cpu,
    fields: [
      { key: 'llm_provider', label: 'LLM Provider', type: 'select', options: ['ollama', 'openai', 'claude', 'groq', 'together', 'cerebras', 'openrouter', 'fireworks'] },
      { key: 'llm_model', label: 'LLM Model', type: 'text', placeholder: 'e.g. qwen2.5:14b' },
      { key: 'ollama_host', label: 'Ollama Host', type: 'text', placeholder: 'http://localhost:11434' },
    ],
  },
  {
    key: 'embeddings',
    label: 'Embeddings',
    icon: Globe,
    fields: [
      { key: 'embed_provider', label: 'Embed Provider', type: 'select', options: ['ollama', 'openai'] },
      { key: 'embed_model', label: 'Embed Model', type: 'text', placeholder: 'e.g. nomic-embed-text' },
    ],
  },
  {
    key: 'cloud',
    label: 'API Keys',
    icon: Key,
    fields: [
      { key: 'openai_api_key', label: 'OpenAI API Key', type: 'secret', placeholder: 'sk-…' },
      { key: 'anthropic_api_key', label: 'Anthropic API Key', type: 'secret', placeholder: 'sk-ant-…' },
      { key: 'groq_api_key', label: 'Groq API Key', type: 'secret' },
      { key: 'together_api_key', label: 'Together AI API Key', type: 'secret' },
      { key: 'cerebras_api_key', label: 'Cerebras API Key', type: 'secret' },
      { key: 'openrouter_api_key', label: 'OpenRouter API Key', type: 'secret' },
      { key: 'fireworks_api_key', label: 'Fireworks API Key', type: 'secret' },
    ],
  },
  {
    key: 'ldap',
    label: 'LDAP / Active Directory',
    icon: Users,
    fields: [
      { key: 'ldap_enabled', label: 'Enable LDAP', type: 'select', options: ['false', 'true'] },
      { key: 'ldap_host', label: 'LDAP Host', type: 'text', placeholder: 'dc01.company.com' },
      { key: 'ldap_port', label: 'LDAP Port', type: 'text', placeholder: '389' },
      { key: 'ldap_use_ssl', label: 'Use SSL/TLS', type: 'select', options: ['false', 'true'] },
      { key: 'ldap_bind_dn', label: 'Bind DN', type: 'text', placeholder: 'CN=svc_zb,OU=Service Accounts,DC=company,DC=com' },
      { key: 'ldap_bind_password', label: 'Bind Password', type: 'secret' },
      { key: 'ldap_base_dn', label: 'Base DN', type: 'text', placeholder: 'DC=company,DC=com' },
      { key: 'ldap_user_filter', label: 'User Filter', type: 'text', placeholder: '(sAMAccountName={username})' },
      { key: 'ldap_group_dn', label: 'Required Group DN', type: 'text', placeholder: 'CN=ZettaBrain Users,OU=Groups,DC=company,DC=com' },
    ],
  },
  {
    key: 'system',
    label: 'System',
    icon: Server,
    fields: [
      { key: 'skills_llm_provider', label: 'Skills LLM Provider Override', type: 'select', options: ['', 'ollama', 'openai', 'claude', 'groq'] },
      { key: 'skills_llm_model', label: 'Skills LLM Model Override', type: 'text', placeholder: 'Leave blank to use default LLM' },
    ],
  },
]

interface FieldDef {
  key: string
  label: string
  type: 'text' | 'secret' | 'select'
  placeholder?: string
  options?: string[]
}

export default function AdminSettingsPage() {
  const [config, setConfig] = useState<SystemConfig>({})
  const [dirty, setDirty] = useState<SystemConfig>({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState('')
  const [activeSection, setActiveSection] = useState<SectionKey>('llm')
  const [revealedKeys, setRevealedKeys] = useState<Set<string>>(new Set())

  useEffect(() => {
    setLoading(true)
    getSystemConfig()
      .then((c) => { setConfig(c); setDirty({}) })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const getValue = (key: string) => dirty[key] ?? config[key] ?? ''
  const isDirty = Object.keys(dirty).length > 0

  const handleChange = (key: string, value: string) => {
    setDirty((prev) => ({ ...prev, [key]: value }))
    setSaved(false)
  }

  const handleSave = async () => {
    if (!isDirty) return
    setSaving(true)
    setError('')
    try {
      const updated = await updateSystemConfig(dirty)
      setConfig(updated)
      setDirty({})
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch (err: unknown) {
      setError(
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Failed to save settings'
      )
    } finally {
      setSaving(false)
    }
  }

  const toggleReveal = (key: string) => {
    setRevealedKeys((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  const section = SECTIONS.find((s) => s.key === activeSection)!

  return (
    <div className="flex flex-col h-screen">
      <TopBar
        title="Settings"
        subtitle="System configuration"
        actions={
          <div className="flex items-center gap-2">
            {error && (
              <span className="text-xs text-danger">{error}</span>
            )}
            {saved && (
              <span className="flex items-center gap-1 text-xs text-success animate-fade-in">
                <Check size={13} />Saved
              </span>
            )}
            <button
              onClick={handleSave}
              disabled={!isDirty || saving}
              className={cn('btn-primary text-xs py-2', !isDirty && 'opacity-50')}
            >
              {saving ? <><Spinner size="sm" />Saving…</> : <><Save size={13} />Save Changes</>}
            </button>
          </div>
        }
      />

      {loading ? (
        <div className="flex justify-center py-24"><Spinner size="lg" /></div>
      ) : (
        <div className="flex flex-1 overflow-hidden">
          {/* Section nav */}
          <aside className="w-52 border-r border-border bg-bg-surface flex-shrink-0 py-4 px-3 space-y-0.5">
            {SECTIONS.map(({ key, label, icon: Icon }) => (
              <button
                key={key}
                onClick={() => setActiveSection(key)}
                className={cn(
                  'nav-item w-full',
                  activeSection === key && 'nav-item-active'
                )}
              >
                <Icon size={15} className="flex-shrink-0" />
                {label}
              </button>
            ))}
          </aside>

          {/* Fields */}
          <div className="flex-1 overflow-y-auto px-8 py-6">
            <div className="max-w-2xl space-y-6">
              <div className="flex items-center gap-3 mb-2">
                <div className="w-9 h-9 rounded-xl bg-brand/10 border border-brand/20 flex items-center justify-center">
                  <section.icon size={17} className="text-brand" />
                </div>
                <div>
                  <h2 className="text-sm font-semibold text-text-primary">{section.label}</h2>
                  <p className="text-xs text-text-muted">Configure {section.label.toLowerCase()} settings</p>
                </div>
              </div>

              <div className="card space-y-5">
                {section.fields.map((field) => (
                  <SettingField
                    key={field.key}
                    field={field}
                    value={getValue(field.key)}
                    onChange={(v) => handleChange(field.key, v)}
                    isDirty={field.key in dirty}
                    revealed={revealedKeys.has(field.key)}
                    onToggleReveal={() => toggleReveal(field.key)}
                  />
                ))}
              </div>

              {isDirty && (
                <div className="flex items-center justify-between px-4 py-3 rounded-lg bg-brand/5 border border-brand/20 animate-fade-in">
                  <div className="flex items-center gap-2 text-sm text-brand">
                    <Settings size={14} />
                    {Object.keys(dirty).length} unsaved change{Object.keys(dirty).length !== 1 ? 's' : ''}
                  </div>
                  <div className="flex gap-2">
                    <button
                      className="btn-ghost text-xs"
                      onClick={() => setDirty({})}
                    >
                      <RefreshCw size={12} />Discard
                    </button>
                    <button
                      className="btn-primary text-xs py-1.5"
                      onClick={handleSave}
                      disabled={saving}
                    >
                      {saving ? <><Spinner size="sm" />Saving…</> : <><Save size={12} />Save</>}
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function SettingField({
  field,
  value,
  onChange,
  isDirty,
  revealed,
  onToggleReveal,
}: {
  field: FieldDef
  value: string
  onChange: (v: string) => void
  isDirty: boolean
  revealed: boolean
  onToggleReveal: () => void
}) {
  const isSecret = field.type === 'secret'
  const isMasked = isSecret && value === '********'

  return (
    <div className={cn('space-y-1.5', isDirty && 'relative')}>
      <div className="flex items-center justify-between">
        <label className="label mb-0">{field.label}</label>
        {isDirty && (
          <span className="text-[10px] font-medium text-warning bg-warning/10 px-1.5 py-0.5 rounded">
            Modified
          </span>
        )}
      </div>

      {field.type === 'select' ? (
        <select
          className="input"
          value={value}
          onChange={(e) => onChange(e.target.value)}
        >
          {field.options!.map((o) => (
            <option key={o} value={o}>{o || '— inherit default —'}</option>
          ))}
        </select>
      ) : isSecret ? (
        <div className="relative">
          <input
            type={revealed ? 'text' : 'password'}
            className="input pr-10 font-mono text-xs"
            value={isMasked && !revealed ? '••••••••' : value}
            placeholder={field.placeholder}
            onChange={(e) => onChange(e.target.value)}
            onFocus={() => { if (isMasked) onChange('') }}
          />
          <button
            type="button"
            onClick={onToggleReveal}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-secondary transition-colors"
            tabIndex={-1}
          >
            {revealed ? <EyeOff size={14} /> : <Eye size={14} />}
          </button>
        </div>
      ) : (
        <input
          type="text"
          className="input"
          value={value}
          placeholder={field.placeholder}
          onChange={(e) => onChange(e.target.value)}
        />
      )}
    </div>
  )
}
