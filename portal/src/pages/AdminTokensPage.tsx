import { useEffect, useState } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuth } from '../AuthContext'
import OneTimeReveal from '../components/OneTimeReveal'

// BFF contracts (Plan 02): authFetch("/api/admin/requests"), authFetch("/api/admin/mint"),
// authFetch("/api/admin/tokens"), authFetch("/api/admin/revoke"), authFetch("/api/admin/rotate").

type AdminState =
  | { status: 'loading' }
  | { status: 'denied'; message: string; httpStatus: number }
  | { status: 'granted'; email: string }

interface QueueRow {
  id: number
  user_email: string
  status: string
  created_at: string
  decided_at: string | null
  decided_by: string | null
}

interface MaskedToken {
  prefix: string
  suffix: string
  display: string
  token_type: string
  username: string
  created_at: string
  expires_at: string | null
  status: string
}

export default function AdminTokensPage() {
  const { isLoggedIn, session, authFetch } = useAuth()
  const [state, setState] = useState<AdminState>({ status: 'loading' })
  const [pending, setPending] = useState<QueueRow[]>([])
  const [history, setHistory] = useState<QueueRow[]>([])
  const [tokens, setTokens] = useState<MaskedToken[]>([])
  const [includeRevoked, setIncludeRevoked] = useState(false)
  const [mintEmail, setMintEmail] = useState('')
  const [mintType, setMintType] = useState('read')
  const [mintExpiry, setMintExpiry] = useState('')
  const [reveal, setReveal] = useState<{ token: string; label: string } | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!isLoggedIn) return
    let cancelled = false
    setState({ status: 'loading' })
    authFetch('/api/admin/ping')
      .then(async (res) => {
        if (cancelled) return
        if (res.ok) {
          const body = (await res.json()) as { email?: string }
          setState({ status: 'granted', email: body.email ?? '' })
        } else {
          const body = (await res.json().catch(() => null)) as { message?: string } | null
          setState({
            status: 'denied',
            message: body?.message ?? 'Access denied.',
            httpStatus: res.status,
          })
        }
      })
      .catch(() => {
        if (!cancelled) setState({ status: 'denied', message: 'Access denied.', httpStatus: 0 })
      })
    return () => {
      cancelled = true
    }
  }, [isLoggedIn, session, authFetch])

  useEffect(() => {
    if (state.status !== 'granted') return
    let cancelled = false
    const queuePath = '/api/admin/requests'
    const listPath = includeRevoked ? '/api/admin/tokens?include_revoked=1' : '/api/admin/tokens'
    Promise.all([authFetch(queuePath), authFetch(listPath)])
      .then(async ([queueRes, listRes]) => {
        if (cancelled) return
        if (queueRes.ok) {
          const body = (await queueRes.json()) as { pending?: QueueRow[]; history?: QueueRow[] }
          setPending(body.pending ?? [])
          setHistory(body.history ?? [])
        }
        if (listRes.ok) {
          const body = (await listRes.json()) as { tokens?: MaskedToken[] }
          setTokens(body.tokens ?? [])
        }
      })
      .catch(() => {
        if (!cancelled) setError('Could not load admin data.')
      })
    return () => {
      cancelled = true
    }
  }, [state.status, includeRevoked, authFetch])

  if (!isLoggedIn) {
    return <Navigate to="/login" replace />
  }

  if (state.status === 'loading') {
    return <main style={{ padding: '2rem' }}>Checking admin access…</main>
  }

  if (state.status === 'denied') {
    return (
      <main style={{ padding: '2rem' }}>
        <h1>Token Admin</h1>
        <p role="alert">
          {state.message} (HTTP {state.httpStatus})
        </p>
      </main>
    )
  }

  const refreshQueue = async () => {
    const [queueRes, listRes] = await Promise.all([
      authFetch('/api/admin/requests'),
      authFetch(includeRevoked ? '/api/admin/tokens?include_revoked=1' : '/api/admin/tokens'),
    ])
    if (queueRes.ok) {
      const body = (await queueRes.json()) as { pending?: QueueRow[]; history?: QueueRow[] }
      setPending(body.pending ?? [])
      setHistory(body.history ?? [])
    }
    if (listRes.ok) {
      const body = (await listRes.json()) as { tokens?: MaskedToken[] }
      setTokens(body.tokens ?? [])
    }
  }

  const decide = async (id: number, action: 'approve' | 'deny') => {
    setError(null)
    const res = await authFetch(`/api/admin/requests/${id}/${action}`, { method: 'POST' })
    const body = (await res.json().catch(() => null)) as {
      token?: string
      message?: string
    } | null
    if (!res.ok) {
      setError(body?.message ?? `${action} failed (HTTP ${res.status}).`)
      return
    }
    if (action === 'approve' && body?.token) {
      setReveal({ token: body.token, label: `Approved write token (request #${id})` })
    }
    await refreshQueue()
  }

  const directMint = async () => {
    setError(null)
    const payload: Record<string, string> = { email: mintEmail, token_type: mintType }
    if (mintExpiry) payload.expires_at = new Date(`${mintExpiry}T00:00:00Z`).toISOString()
    const res = await authFetch('/api/admin/mint', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    const body = (await res.json().catch(() => null)) as {
      token?: string
      message?: string
    } | null
    if (!res.ok || !body?.token) {
      setError(body?.message ?? `Direct mint failed (HTTP ${res.status}).`)
      return
    }
    setReveal({ token: body.token, label: `Token for ${mintEmail}` })
    await refreshQueue()
  }

  const revoke = async (prefix: string) => {
    if (!window.confirm(`Revoke token ${prefix}…? It will stop working immediately.`)) return
    setError(null)
    const res = await authFetch('/api/admin/revoke', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id_or_prefix: prefix }),
    })
    if (!res.ok) {
      const body = (await res.json().catch(() => null)) as { message?: string } | null
      setError(body?.message ?? `Revoke failed (HTTP ${res.status}).`)
      return
    }
    await refreshQueue()
  }

  const rotate = async (prefix: string) => {
    if (!window.confirm(`Rotate token ${prefix}…? The old secret stops working.`)) return
    setError(null)
    const res = await authFetch('/api/admin/rotate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id_or_prefix: prefix }),
    })
    const body = (await res.json().catch(() => null)) as {
      token?: string
      message?: string
    } | null
    if (!res.ok || !body?.token) {
      setError(body?.message ?? `Rotate failed (HTTP ${res.status}).`)
      return
    }
    setReveal({ token: body.token, label: 'Rotated token (new secret)' })
    await refreshQueue()
  }

  return (
    <main style={{ padding: '2rem' }}>
      <h1>Token Admin</h1>
      <p>Signed in as {state.email}</p>
      {error && <p role="alert">{error}</p>}
      {reveal && (
        <OneTimeReveal token={reveal.token} label={reveal.label} onDismiss={() => setReveal(null)} />
      )}

      <section>
        <h2>Approval queue</h2>
        {pending.length === 0 ? (
          <p>No pending requests.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Requester</th>
                <th>Date</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {pending.map((r) => (
                <tr key={r.id}>
                  <td>{r.user_email}</td>
                  <td>{r.created_at}</td>
                  <td>{r.status}</td>
                  <td>
                    <button type="button" onClick={() => decide(r.id, 'approve')}>
                      Approve
                    </button>{' '}
                    <button type="button" onClick={() => decide(r.id, 'deny')}>
                      Deny
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {history.length > 0 && (
          <>
            <h3>History</h3>
            <table>
              <thead>
                <tr>
                  <th>Requester</th>
                  <th>Status</th>
                  <th>Decided at</th>
                  <th>Decided by</th>
                </tr>
              </thead>
              <tbody>
                {history.map((r) => (
                  <tr key={r.id}>
                    <td>{r.user_email}</td>
                    <td>{r.status}</td>
                    <td>{r.decided_at ?? '—'}</td>
                    <td>{r.decided_by ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </section>

      <section>
        <h2>Direct mint</h2>
        <label>
          Email <input type="email" value={mintEmail} onChange={(e) => setMintEmail(e.target.value)} />
        </label>{' '}
        <label>
          Type{' '}
          <select value={mintType} onChange={(e) => setMintType(e.target.value)}>
            <option value="read">read</option>
            <option value="read_write">read-write</option>
          </select>
        </label>{' '}
        <label>
          Expiry override (optional){' '}
          <input type="date" value={mintExpiry} onChange={(e) => setMintExpiry(e.target.value)} />
        </label>{' '}
        <button type="button" onClick={directMint}>
          Mint token
        </button>
      </section>

      <section>
        <h2>All tokens</h2>
        <label>
          <input
            type="checkbox"
            aria-label="include revoked/expired"
            checked={includeRevoked}
            onChange={(e) => setIncludeRevoked(e.target.checked)}
          />{' '}
          Include revoked/expired
        </label>
        {tokens.length === 0 ? (
          <p>No tokens yet.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Owner</th>
                <th>Token</th>
                <th>Type</th>
                <th>Created</th>
                <th>Expires</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {tokens.map((t) => (
                <tr key={`${t.username}${t.prefix}${t.created_at}`}>
                  <td>{t.username}</td>
                  <td>{t.display}</td>
                  <td>{t.token_type}</td>
                  <td>{t.created_at}</td>
                  <td>{t.expires_at ?? 'never'}</td>
                  <td>{t.status}</td>
                  <td>
                    <button type="button" onClick={() => revoke(t.prefix)}>
                      Revoke
                    </button>{' '}
                    <button type="button" onClick={() => rotate(t.prefix)}>
                      Rotate
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </main>
  )
}
