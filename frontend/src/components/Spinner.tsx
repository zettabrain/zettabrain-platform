import { cn } from '../lib/utils'

interface SpinnerProps {
  size?: 'sm' | 'md' | 'lg'
  className?: string
}

export default function Spinner({ size = 'md', className }: SpinnerProps) {
  const s = { sm: 'w-4 h-4', md: 'w-6 h-6', lg: 'w-10 h-10' }[size]
  return (
    <div
      className={cn(
        'animate-spin rounded-full border-2 border-border border-t-brand',
        s,
        className
      )}
    />
  )
}
