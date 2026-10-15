import { cn } from '@/lib/utils'

const TONE = {
  active: 'bg-primary',
  pending: 'bg-signal',
  revoked: 'bg-muted-foreground/50',
  expired: 'bg-muted-foreground/30',
  denied: 'bg-destructive',
  granted: 'bg-primary',
} as const

/**
 * Token and request status.
 *
 * Status is the thing an engineer scans a token table for, so it gets a colour
 * dot as well as the word — the dot is redundant with the text, never a
 * replacement for it.
 */
export default function TokenStatus({
  status,
  className,
}: {
  status: string
  className?: string
}) {
  const tone = TONE[status.toLowerCase() as keyof typeof TONE] ?? TONE.expired
  return (
    <span className={cn('inline-flex items-center gap-2', className)}>
      <span className={cn('size-1.5 shrink-0 rounded-full', tone)} aria-hidden />
      <span className="tabular">{status}</span>
    </span>
  )
}