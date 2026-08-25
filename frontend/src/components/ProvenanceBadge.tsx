import { ShieldCheck } from 'lucide-react'
import { cn } from '../lib/utils'

interface ProvenanceBadgeProps {
  sig: string | null
  className?: string
}

export default function ProvenanceBadge({ sig, className }: ProvenanceBadgeProps) {
  if (!sig) return null

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-xs font-medium',
        'bg-success/10 border border-success/30 text-success',
        'cursor-default select-none',
        className
      )}
      title={`Ed25519 Signature: ${sig}`}
    >
      {/* Pulse dot */}
      <span className="relative flex h-2 w-2">
        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-success opacity-60" />
        <span className="relative inline-flex rounded-full h-2 w-2 bg-success" />
      </span>
      <ShieldCheck size={12} />
      ZettaBrain Verified
    </span>
  )
}
