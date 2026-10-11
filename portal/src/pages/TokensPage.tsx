import { useCallback, useEffect, useState } from 'react'
import { useAuth } from '../AuthContext'
import OneTimeReveal from '../components/OneTimeReveal'

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

interface UpgradeRequest {
  id: number
  status: string
  created_at: string
  decided_at: string | null
}

function defaultExpiryDate(): string {
  return new Date(Date.now() + 90 * 86400 * 1000).toISOString().slice(0, 10)
}

// BFF contracts (Plan 01): authFetch("/api/tokens/mine"), authFetch("/api/tokens/mint-read"),
// authFetch("/api/tokens/request"), authFetch("/api/tokens/my-request"),
// authFetch("/api/tokens/revoke"), authFetch("/api/tokens/rotate").

export default function TokensPage() {
  const { authFetch } = useAuth()
  const [tokens, setTokens] = useState<MaskedToken[]>([])
  const [requests, setRequests] = useState<UpgradeRequest[]>([])
  const [expiryDate, setExpiryDate] = useState(defaultExpiryDate)
  const [includeRevoked, setIncludeRevoked] = useState(false)
  const [reveal, setReveal] = useState<{ token: string; label: string } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const fail = (res: Response, body: { message?: string } | null, fallback: string) => {
    setError(body?.message ?? `${fallback} (HTTP ${res.status})`)
  }

  const refresh = useCallback(async () => {
    const minePath = includeRevoked ? '/api/tokens/mine?include_revoked=1' : '/api/tokens/mine'
    const [mineRes, reqRes] = await Promise.all([
      authFetch(minePath),
      authFetch('/api/tokens/my-request'),
    ])
    if (mineRes.ok) {
      const body = (await mineRes.json()) as { tokens?: MaskedToken[] }
      setTokens(body.tokens ?? [])
    }
    if (reqRes.ok) {
      const body = (await reqRes.json()) as { requests?: UpgradeRequest[] }
      setRequests(body.requests ?? [])
    }
  }, [authFetch, includeRevoked])

  useEffect(() => {
    refresh().catch(() => setError('Could not load tokens.'))
  }, [refresh])

  const mint = async () => {
    setError(null)
    setNotice(null)
    const expires_at = new Date(`${expiryDate}T00:00:00Z`).toISOString()
    const res = await authFetch('/api/tokens/mint-read', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ expires_at }),
    })
    const body = (await res.json().catch(() => null)) as {
      token?: string
      message?: string
    } | null
    if (!res.ok || !body?.token) {
      if (res.status === 409) {
        setError(`${body?.message ?? 'Token limit reached.'} Revoke or rotate an old token first.`)
      } else {
        fail(res, body, 'Mint failed.')
      }
      return
    }
    setReveal({ token: body.token, label: 'New read token' })
    await refresh()
  }

  const requestUpgrade = async () => {
    setError(null)
    setNotice(null)
    const res = await authFetch('/api/tokens/request', { method: 'POST' })
    const body = (await res.json().catch(() => null)) as { message?: string } | null
    if (res.status === 409) {
      setNotice('A request is already pending — cancel it before requesting again.')
      return
    }
    if (!res.ok) {
      fail(res, body, 'Request failed.')
      return
    }
    setNotice('Write-upgrade requested.')
    await refresh()
  }

  const cancelRequest = async (id: number) => {
    setError(null)
    const res = await authFetch('/api/tokens/my-request', {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id }),
    })
    if (!res.ok) {
      const body = (await res.json().catch(() => null)) as { message?: string } | null
      fail(res, body, 'Cancel failed.')
      return
    }
    await refresh()
  }

  const revoke = async (prefix: string) => {
    if (!window.confirm(`Revoke token ${prefix}…? It will stop working immediately.`)) return
    setError(null)
    const res = await authFetch('/api/tokens/revoke', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id_or_prefix: prefix }),
    })
    if (!res.ok) {
      const body = (await res.json().catch(() => null)) as { message?: string } | null
      fail(res, body, 'Revoke failed.')
      return
    }
    await refresh()
  }

  const rotate = async (prefix: string) => {
    if (!window.confirm(`Rotate token ${prefix}…? The old secret stops working.`)) return
    setError(null)
    const res = await authFetch('/api/tokens/rotate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id_or_prefix: prefix }),
    })
    const body = (await res.json().catch(() => null)) as {
      token?: string
      message?: string
    } | null
    if (!res.ok || !body?.token) {
      fail(res, body, 'Rotate failed.')
      return
    }
    setReveal({ token: body.token, label: 'Rotated token (new secret)' })
    await refresh()
  }

  const pending = requests.filter((r) => r.status === 'pending')
  const decided = requests.filter((r) => r.status !== 'pending')

  return (
    <main style={{ padding: '2rem' }}>
      <h1>My Tokens</h1>
      {error && <p role="alert">{error}</p>}
      {notice && <p>{notice}</p>}
      {reveal && (
        <OneTimeReveal token={reveal.token} label={reveal.label} onDismiss={() => setReveal(null)} />
      )}

      <section>
        <h2>Mint read token</h2>
        <label>
          Expiry date{' '}
          <input type="date" value={expiryDate} onChange={(e) => setExpiryDate(e.target.value)} />
        </label>{' '}
        <button type="button" onClick={mint}>
          Mint read token
        </button>
      </section>

      <section>
        <h2>My tokens</h2>
        <label>
          <input
            type="checkbox"
            aria-label="include revoked/expired"
            checked={includeRevoked}
            onChange={(e) => setIncludeRevoked(e.target.checked)}
          />{' '}
          Include revoked/expired
        </label>
        {/* include revoked toggle defaults to active-only (D-15) */}
        {tokens.length === 0 ? (
          <p>No tokens yet.</p>
        ) : (
          <table>
            <thead>
              <tr>
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
                <tr key={`${t.prefix}${t.suffix}${t.created_at}`}>
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

      <section>
        <h2>Write upgrade</h2>
        {pending.length > 0 ? (
          <ul>
            {pending.map((r) => (
              <li key={r.id}>
                Request #{r.id} — pending since {r.created_at}{' '}
                <button type="button" onClick={() => cancelRequest(r.id)}>
                  Cancel
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p>
            <button type="button" onClick={requestUpgrade}>
              Request write access
            </button>
          </p>
        )}
        {decided.length > 0 && (
          <>
            <h3>Past requests</h3>
            <ul>
              {decided.map((r) => (
                <li key={r.id}>
                  Request #{r.id} — {r.status}
                  {r.decided_at ? ` at ${r.decided_at}` : ''}
                  {r.status === 'denied' && (
                    <>
                      {' '}
                      <button type="button" onClick={requestUpgrade}>
                        Request again
                      </button>
                    </>
                  )}
                </li>
              ))}
            </ul>
          </>
        )}
      </section>
    </main>
  )
}
