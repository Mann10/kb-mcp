import { useEffect, useRef, useState } from 'react'

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
 */
export default function OneTimeReveal({ token, label, onDismiss }: OneTimeRevealProps) {
  const [copied, setCopied] = useState(false)
  const boxRef = useRef<HTMLElement | null>(null)
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
    <section ref={boxRef} aria-live="polite" style={{ border: '2px solid #b45309', padding: '1rem', margin: '1rem 0', background: '#fffbeb' }}>
      <p>
        <strong>{label}</strong>
      </p>
      <p>Copy now — this secret is shown once and never again.</p>
      <input ref={inputRef} type="text" readOnly value={token} aria-label={label} style={{ width: '100%' }} />
      <p>
        <button type="button" onClick={copy}>
          {copied ? 'Copied' : 'Copy'}
        </button>{' '}
        <button type="button" onClick={onDismiss}>
          Dismiss
        </button>
      </p>
    </section>
  )
}
