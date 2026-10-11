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
  const dismissRef = useRef(onDismiss)
  dismissRef.current = onDismiss

  useEffect(() => {
    return () => {
      dismissRef.current()
    }
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
    <section aria-live="polite" style={{ border: '1px solid #b45309', padding: '1rem', margin: '1rem 0' }}>
      <p>
        <strong>{label}</strong>
      </p>
      <p>Copy now — this secret is shown once and never again.</p>
      <input type="text" readOnly value={token} aria-label={label} style={{ width: '100%' }} />
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
