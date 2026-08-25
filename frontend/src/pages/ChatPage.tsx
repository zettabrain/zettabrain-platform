import { useState, useRef, useEffect, FormEvent } from 'react'
import {
  Send,
  MessageSquare,
  FileText,
  Clock,
  ChevronRight,
  Cpu,
  RotateCcw,
  History,
  X,
} from 'lucide-react'
import TopBar from '../components/TopBar'
import ConfidenceMeter from '../components/ConfidenceMeter'
import ProvenanceBadge from '../components/ProvenanceBadge'
import Spinner from '../components/Spinner'
import EmptyState from '../components/EmptyState'
import { useTeam } from '../context/TeamContext'
import { sendChat, getChatHistory, type ChatResponse, type ChatHistoryItem } from '../api/chat'
import { cn, formatDateTime, truncate } from '../lib/utils'

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  response?: ChatResponse
  loading?: boolean
  error?: string
  timestamp: Date
}

export default function ChatPage() {
  const { activeTeam } = useTeam()
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [showHistory, setShowHistory] = useState(false)
  const [history, setHistory] = useState<ChatHistoryItem[]>([])
  const [historyLoading, setHistoryLoading] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  useEffect(() => {
    if (activeTeam) setMessages([])
  }, [activeTeam?.id])

  const loadHistory = async () => {
    if (!activeTeam) return
    setHistoryLoading(true)
    try {
      const data = await getChatHistory(activeTeam.id)
      setHistory(data)
    } catch {
      // ignore
    } finally {
      setHistoryLoading(false)
    }
  }

  const handleHistoryOpen = () => {
    setShowHistory(true)
    loadHistory()
  }

  const handleSubmit = async (e?: FormEvent) => {
    e?.preventDefault()
    const query = input.trim()
    if (!query || sending || !activeTeam) return

    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: 'user',
      content: query,
      timestamp: new Date(),
    }
    const aiMsg: Message = {
      id: crypto.randomUUID(),
      role: 'assistant',
      content: '',
      loading: true,
      timestamp: new Date(),
    }

    setMessages((prev) => [...prev, userMsg, aiMsg])
    setInput('')
    setSending(true)

    try {
      const res = await sendChat(activeTeam.id, query)
      setMessages((prev) =>
        prev.map((m) =>
          m.id === aiMsg.id
            ? { ...m, content: res.answer, response: res, loading: false }
            : m
        )
      )
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        'Something went wrong. Please try again.'
      setMessages((prev) =>
        prev.map((m) =>
          m.id === aiMsg.id
            ? { ...m, content: '', error: detail, loading: false }
            : m
        )
      )
    } finally {
      setSending(false)
      inputRef.current?.focus()
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  const handleHistoryItem = (item: ChatHistoryItem) => {
    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: 'user',
      content: item.query,
      timestamp: new Date(item.created_at),
    }
    const aiMsg: Message = {
      id: crypto.randomUUID(),
      role: 'assistant',
      content: item.answer,
      response: {
        answer: item.answer,
        confidence: item.confidence,
        sources: [],
        chunks: [],
        provenance_sig: null,
        model: item.model,
        duration_ms: 0,
      },
      timestamp: new Date(item.created_at),
    }
    setMessages([userMsg, aiMsg])
    setShowHistory(false)
  }

  return (
    <div className="flex flex-col h-screen">
      <TopBar
        title="Chat"
        subtitle="Ask questions about your documents"
        actions={
          <button
            onClick={handleHistoryOpen}
            className="btn-ghost text-xs"
          >
            <History size={14} />
            History
          </button>
        }
      />

      <div className="flex flex-1 overflow-hidden relative">
        {/* Main chat area */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Messages */}
          <div className="flex-1 overflow-y-auto px-6 py-6 space-y-6">
            {messages.length === 0 && (
              <EmptyStatChat teamName={activeTeam?.name} />
            )}

            {messages.map((msg) => (
              <ChatMessage key={msg.id} message={msg} />
            ))}
            <div ref={bottomRef} />
          </div>

          {/* Input bar */}
          <div className="border-t border-border bg-bg-surface px-6 py-4">
            {!activeTeam && (
              <p className="text-center text-sm text-text-muted mb-3">
                Select a team to start chatting
              </p>
            )}
            <form onSubmit={handleSubmit} className="flex items-end gap-3">
              <div className="flex-1 relative">
                <textarea
                  ref={inputRef}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  disabled={!activeTeam || sending}
                  placeholder={
                    activeTeam
                      ? `Ask anything about ${activeTeam.name}'s documents…`
                      : 'Select a team first…'
                  }
                  rows={1}
                  className={cn(
                    'input resize-none max-h-32 py-3 pr-4 leading-relaxed',
                    'min-h-[48px] overflow-y-auto'
                  )}
                  style={{ height: 'auto' }}
                  onInput={(e) => {
                    const t = e.currentTarget
                    t.style.height = 'auto'
                    t.style.height = Math.min(t.scrollHeight, 128) + 'px'
                  }}
                />
              </div>
              <button
                type="submit"
                disabled={!input.trim() || sending || !activeTeam}
                className="btn-primary h-12 w-12 justify-center p-0 flex-shrink-0"
              >
                {sending ? <Spinner size="sm" /> : <Send size={16} />}
              </button>
            </form>
            <p className="text-xs text-text-muted mt-2">
              Press <kbd className="px-1 py-0.5 rounded bg-bg-elevated border border-border font-mono text-[10px]">Enter</kbd> to send,{' '}
              <kbd className="px-1 py-0.5 rounded bg-bg-elevated border border-border font-mono text-[10px]">Shift+Enter</kbd> for new line
            </p>
          </div>
        </div>

        {/* History Sidebar */}
        {showHistory && (
          <aside className="w-80 border-l border-border bg-bg-surface flex flex-col animate-slide-up overflow-hidden">
            <div className="flex items-center justify-between px-4 py-3 border-b border-border flex-shrink-0">
              <h3 className="text-sm font-semibold text-text-primary">Chat History</h3>
              <button
                onClick={() => setShowHistory(false)}
                className="p-1 rounded-md text-text-muted hover:text-text-primary hover:bg-bg-elevated transition-colors"
              >
                <X size={15} />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto">
              {historyLoading ? (
                <div className="flex justify-center py-10">
                  <Spinner />
                </div>
              ) : history.length === 0 ? (
                <EmptyState
                  icon={MessageSquare}
                  title="No history yet"
                  description="Your past conversations will appear here"
                />
              ) : (
                <div className="divide-y divide-border">
                  {history.map((item) => (
                    <button
                      key={item.id}
                      onClick={() => handleHistoryItem(item)}
                      className="w-full text-left px-4 py-3 hover:bg-bg-elevated transition-colors group"
                    >
                      <p className="text-sm text-text-primary truncate group-hover:text-brand transition-colors">
                        {truncate(item.query, 60)}
                      </p>
                      <div className="flex items-center gap-2 mt-1">
                        <Clock size={11} className="text-text-muted" />
                        <span className="text-xs text-text-muted">{formatDateTime(item.created_at)}</span>
                        <span className={cn(
                          'text-xs font-mono ml-auto',
                          item.confidence >= 0.7 ? 'text-success' : item.confidence >= 0.5 ? 'text-warning' : 'text-danger'
                        )}>
                          {Math.round(item.confidence * 100)}%
                        </span>
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </aside>
        )}
      </div>
    </div>
  )
}

/* ── Empty state ── */
function EmptyStatChat({ teamName }: { teamName?: string }) {
  return (
    <div className="flex flex-col items-center justify-center h-full min-h-[40vh] text-center">
      <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-brand/20 to-violet-ai/20 border border-brand/20 flex items-center justify-center mb-5">
        <MessageSquare size={28} className="text-brand" />
      </div>
      <h2 className="text-lg font-semibold text-text-primary mb-2">
        {teamName ? `Chat with ${teamName}` : 'Start a conversation'}
      </h2>
      <p className="text-sm text-text-secondary max-w-sm">
        Ask questions about your team's documents. ZettaBrain retrieves the most relevant sources and generates an answer with a confidence score.
      </p>
      <div className="mt-6 grid grid-cols-1 sm:grid-cols-2 gap-2 max-w-md w-full">
        {[
          'What is the incident escalation process?',
          'Summarise the Q3 budget report',
          'What are the security policies for remote access?',
          'Who owns the deployment checklist?',
        ].map((q) => (
          <SuggestionChip key={q} text={q} />
        ))}
      </div>
    </div>
  )
}

function SuggestionChip({ text }: { text: string }) {
  return (
    <div className="px-3 py-2 rounded-lg border border-border bg-bg-surface text-xs text-text-secondary text-left hover:border-brand/30 hover:text-text-primary hover:bg-bg-elevated transition-all cursor-default">
      <ChevronRight size={11} className="inline mr-1 text-brand" />
      {text}
    </div>
  )
}

/* ── Chat message bubble ── */
function ChatMessage({ message }: { message: Message }) {
  const isUser = message.role === 'user'

  if (isUser) {
    return (
      <div className="flex justify-end animate-fade-in">
        <div className="max-w-2xl">
          <div className="px-4 py-3 rounded-2xl rounded-br-sm bg-brand text-white text-sm leading-relaxed">
            {message.content}
          </div>
          <p className="text-xs text-text-muted text-right mt-1">
            {message.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex gap-3 animate-fade-in">
      {/* AI avatar */}
      <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-brand to-violet-ai flex items-center justify-center flex-shrink-0 mt-0.5 shadow-glow-violet">
        <span className="text-white text-xs font-bold">Z</span>
      </div>

      <div className="flex-1 max-w-3xl">
        {/* Bubble */}
        <div className="bg-bg-surface border border-border rounded-2xl rounded-tl-sm overflow-hidden">
          {message.loading ? (
            <div className="px-5 py-4 flex items-center gap-3">
              <Spinner size="sm" />
              <span className="text-sm text-text-muted animate-pulse">Searching documents…</span>
            </div>
          ) : message.error ? (
            <div className="px-5 py-4 text-sm text-danger bg-danger/5 border-l-2 border-danger">
              ⚠ {message.error}
            </div>
          ) : (
            <>
              {/* Answer text */}
              <div className="px-5 py-4">
                <p className="text-sm text-text-primary leading-relaxed whitespace-pre-wrap">
                  {message.content}
                </p>
              </div>

              {/* Sources */}
              {message.response && message.response.sources.length > 0 && (
                <div className="px-5 pb-4 border-t border-border/50 pt-3">
                  <p className="text-xs font-medium text-text-muted uppercase tracking-wide mb-2">
                    Sources used
                  </p>
                  <div className="space-y-1.5">
                    {message.response.sources.map((src, i) => (
                      <div
                        key={i}
                        className="flex items-center gap-2 text-xs text-text-secondary"
                      >
                        <FileText size={12} className="text-brand flex-shrink-0" />
                        <span className="font-medium text-text-primary">{src.filename}</span>
                        {src.page && (
                          <span className="text-text-muted">p. {src.page}</span>
                        )}
                        {src.section && (
                          <span className="text-text-muted">§ {src.section}</span>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Footer: confidence + provenance + model */}
              {message.response && (
                <div className="px-5 py-3 bg-bg-elevated/50 border-t border-border/50 flex flex-wrap items-center gap-3">
                  <div className="flex items-center gap-2 flex-1 min-w-[180px]">
                    <span className="text-xs text-text-muted whitespace-nowrap">Confidence</span>
                    <ConfidenceMeter score={message.response.confidence} />
                  </div>
                  <div className="flex items-center gap-2 flex-wrap">
                    <ProvenanceBadge sig={message.response.provenance_sig} />
                    <span className="flex items-center gap-1 text-xs text-text-muted">
                      <Cpu size={11} />
                      {message.response.model}
                    </span>
                    {message.response.duration_ms > 0 && (
                      <span className="flex items-center gap-1 text-xs text-text-muted">
                        <RotateCcw size={11} />
                        {(message.response.duration_ms / 1000).toFixed(1)}s
                      </span>
                    )}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
