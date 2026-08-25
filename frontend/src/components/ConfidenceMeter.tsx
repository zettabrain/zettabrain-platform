import { cn, confidenceColor, confidenceBg, confidenceLabel } from '../lib/utils'

interface ConfidenceMeterProps {
  score: number
  showLabel?: boolean
  className?: string
}

export default function ConfidenceMeter({ score, showLabel = true, className }: ConfidenceMeterProps) {
  const pct = Math.round(score * 100)
  const color = confidenceColor(score)
  const bg = confidenceBg(score)
  const label = confidenceLabel(score)

  return (
    <div className={cn('flex items-center gap-2', className)}>
      {/* Bar */}
      <div className="flex-1 h-1.5 bg-bg-elevated rounded-full overflow-hidden">
        <div
          className={cn('h-full rounded-full transition-all duration-500', bg)}
          style={{ width: `${pct}%` }}
        />
      </div>
      {/* Pct + label */}
      {showLabel && (
        <span className={cn('text-xs font-mono font-medium tabular-nums', color)}>
          {pct}%
          <span className="ml-1 text-text-muted font-sans">· {label}</span>
        </span>
      )}
    </div>
  )
}
