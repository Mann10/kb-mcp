import type { ReactNode } from 'react'
import { AlertCircle, CircleCheck } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Alert, AlertDescription } from '@/components/ui/alert'

/**
 * Error surface.
 *
 * D-16 requires server messages to render verbatim so a rename collision or a
 * 403 stays diagnosable, so the message is never rewritten or truncated here —
 * only given a container.
 */
export function ErrorNotice({ message }: { message: string | null }) {
  if (!message) return null
  return (
    <Alert variant="destructive" role="alert" className="mb-5">
      <AlertCircle />
      <AlertDescription className="break-words">{message}</AlertDescription>
    </Alert>
  )
}

/** Non-error confirmation, e.g. "Write-upgrade requested." */
export function InfoNotice({ message }: { message: string | null }) {
  if (!message) return null
  return (
    <Alert role="status" className="mb-5 border-primary/25 bg-accent/50">
      <CircleCheck className="text-primary" />
      <AlertDescription>{message}</AlertDescription>
    </Alert>
  )
}

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string
  description?: string
  actions?: ReactNode
}) {
  return (
    <header className="mb-7 flex flex-wrap items-start justify-between gap-x-6 gap-y-3 border-b pb-4">
      <div className="min-w-0">
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        {description && (
          <p className="mt-1 text-sm text-muted-foreground">{description}</p>
        )}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </header>
  )
}

/** Section heading used between hairline-separated blocks. */
export function SectionTitle({
  children,
  className,
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <h2 className={cn('text-sm font-semibold tracking-tight', className)}>{children}</h2>
  )
}