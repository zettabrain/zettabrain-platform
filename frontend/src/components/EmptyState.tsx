import { cn } from '../lib/utils'
import type { LucideIcon } from 'lucide-react'

interface EmptyStateProps {
  icon: LucideIcon
  title: string
  description?: string
  action?: React.ReactNode
  className?: string
}

export default function EmptyState({ icon: Icon, title, description, action, className }: EmptyStateProps) {
  return (
    <div className={cn('flex flex-col items-center justify-center text-center py-16 px-6', className)}>
      <div className="w-14 h-14 rounded-2xl bg-bg-elevated border border-border flex items-center justify-center mb-4">
        <Icon size={24} className="text-text-muted" />
      </div>
      <p className="text-base font-semibold text-text-primary mb-1">{title}</p>
      {description && <p className="text-sm text-text-secondary max-w-xs">{description}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  )
}
