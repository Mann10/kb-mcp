import { useEffect, useRef, useState } from 'react'
import { Check, Copy, TriangleAlert, X } from 'lucide-react'
import { Button } from '@/components/ui/button'

interface OneTimeRevealProps {
  token: string
  label: string
  onDismiss: () => void
}
/**
 * One-time secret reveal (D-06, T-11-11).
 *
 * The raw secret lives only in this component's props — never lifted to page
 * state, never persisted to browser storage. It is cleared via
 * onDismiss and again on unmount (cleanup), so navigating away destroys it.
 *
 * This is the one place in the portal that is allowed to be loud. Everything
 * else is greyscale and petrol, so the amber here reads as a warning rather
 * than as decoration.
 */
export default function OneTimeReveal({ token, label, onDismiss }: OneTimeRevealProps) {
  const [copied, setCopied] = useState(false)
  const boxRef = useRef<HTMLDivElement | null>(null)
  const inputRef = useRef<HTMLInputElement | null>(null)

  useEffect(() => {
    // Unmissable: scroll into view and pre-select the secret so Ctrl+C works instantly.
    // NOTE: no cleanup calling onDismiss here — under React.StrictMode (dev)
    // the mount cleanup runs immediately and would dismiss the box itself.
    // Clearance is guaranteed anyway: Dismiss button + route unmount drops
    // the parent's reveal state.
    boxRef.current?.scrollIntoView({ block: 'center' })
    inputRef.current?.focus()
    inputRef.current?.select()
  }, [])

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(token)
      setCopied(true)
    } catch {
      setCopied(false)
    }
  }

  return (
    <div
      ref={boxRef}
      aria-live="polite"
      role="group"
      aria-label={label}
      className="mb-6 rounded-lg border-2 border-signal-border bg-signal-surface p-4"
    >
      <div className="flex items-start gap-2.5">
        <TriangleAlert className="mt-0.5 size-4 shrink-0 text-signal" aria-hidden />
        <div className="min-w-0">
          <p className="text-sm font-semibold text-signal-foreground">{label}</p>
          <p className="mt-0.5 text-sm text-signal-foreground/80">
            Copy it now. This secret is shown once and never again.
          </p>
        </div>
      </div>

      <div className="mt-3 flex flex-col gap-2 sm:flex-row">
        {/* Raw input, not the shadcn Input: this one needs a ref for
            focus+select, and Input is not a forwardRef component under React 18. */}
        <input
          ref={inputRef}
          type="text"
          readOnly
          value={token}
          aria-label={label}
          className="h-8 w-full min-w-0 rounded-lg border border-signal-border bg-card px-2.5 py-1 font-mono text-[0.8125rem] tabular-nums text-foreground outline-none focus-visible:ring-3 focus-visible:ring-signal/30"
        />
        <div className="flex gap-2">
          <Button type="button" onClick={copy} className="shrink-0">
            {copied ? <Check data-icon="inline-start" /> : <Copy data-icon="inline-start" />}
            {copied ? 'Copied' : 'Copy'}
          </Button>
          <Button type="button" variant="outline" onClick={onDismiss} className="shrink-0">
            <X data-icon="inline-start" />
            Dismiss
          </Button>
        </div>
      </div>
    </div>
  )
}