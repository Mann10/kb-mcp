import { useCallback, useEffect, useState } from 'react'
import type { CSSProperties } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../AuthContext'

interface SearchRow {
  stem: string
  title: string
  snippet: string
  tags: string[]
  created: string
}

interface TagCount {
  tag: string
  count: number
}

const section: CSSProperties = { marginBottom: '1.5rem' }
const row: CSSProperties = { marginBottom: '1rem' }

// BFF contracts (Plans 01/02): authFetch("/api/notes/search?q=&tag=&date_from=&date_to=&limit="),
// authFetch("/api/notes/list"), authFetch("/api/notes/tags"),
// authFetch("/api/notes/can_write").

export default function BrowsePage() {
  const { authFetch } = useAuth()
  const navigate = useNavigate()
  const [q, setQ] = useState('')
  const [tag, setTag] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [results, setResults] = useState<SearchRow[]>([])
  const [message, setMessage] = useState<string | null>(null)
  const [tags, setTags] = useState<TagCount[]>([])
  const [canWrite, setCanWrite] = useState<boolean | null>(null)
  const [error, setError] = useState<string | null>(null)

  const fail = (res: Response, body: { message?: string } | null, fallback: string) => {
    setError(body?.message ?? `${fallback} (HTTP ${res.status})`)
  }

  const runSearch = useCallback(
    async (opts: { q: string; tag: string; dateFrom: string; dateTo: string }) => {
      setError(null)
      const params = new URLSearchParams()
      params.set('q', opts.q)
      if (opts.tag.trim()) params.set('tag', opts.tag.trim())
      if (opts.dateFrom.trim()) params.set('date_from', opts.dateFrom.trim())
      if (opts.dateTo.trim()) params.set('date_to', opts.dateTo.trim())
      const res = await authFetch(`/api/notes/search?${params.toString()}`)
      const body = (await res.json().catch(() => null)) as {
        results?: SearchRow[]
        message?: string
      } | null
      if (!res.ok) {
        fail(res, body, 'Search failed.')
        return
      }
      // Server order is v1 rank order — never re-sort on the client (D-07).
      setResults(body?.results ?? [])
      setMessage(body?.message ?? null)
    },
    [authFetch],
  )

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      const [listRes, tagsRes, writeRes] = await Promise.all([
        authFetch('/api/notes/list'),
        authFetch('/api/notes/tags'),
        authFetch('/api/notes/can_write'),
      ])
      if (cancelled) return
      if (listRes.ok) {
        const body = (await listRes.json().catch(() => null)) as {
          notes?: { stem: string; title: string; tags: string[]; created: string }[]
          message?: string
        } | null
        setResults((body?.notes ?? []).map((n) => ({ ...n, snippet: '' })))
        setMessage(body?.message ?? null)
      }
      if (tagsRes.ok) {
        const body = (await tagsRes.json().catch(() => null)) as { tags?: TagCount[] } | null
        setTags(body?.tags ?? [])
      }
      if (writeRes.ok) {
        const body = (await writeRes.json().catch(() => null)) as { can_write?: boolean } | null
        setCanWrite(body?.can_write ?? false)
      }
    }
    load().catch(() => {
      if (!cancelled) setError('Could not load notes.')
    })
    return () => {
      cancelled = true
    }
  }, [authFetch])

  const onSearch = () => {
    void runSearch({ q, tag, dateFrom, dateTo })
  }

  const onTagClick = (t: string) => {
    setTag(t)
    void runSearch({ q, tag: t, dateFrom, dateTo })
  }

  return (
    <main style={{ padding: '2rem' }}>
      <h1>Browse Notes</h1>
      {error && <p role="alert">{error}</p>}

      <section style={section}>
        <form
          onSubmit={(e) => {
            e.preventDefault()
            onSearch()
          }}
        >
          <label>
            Search{' '}
            <input
              type="text"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="keyword"
            />
          </label>{' '}
          <label>
            Tag{' '}
            <select value={tag} onChange={(e) => setTag(e.target.value)}>
              <option value="">(any)</option>
              {tags.map((t) => (
                <option key={t.tag} value={t.tag}>
                  {t.tag} ({t.count})
                </option>
              ))}
            </select>
          </label>{' '}
          <label>
            From <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
          </label>{' '}
          <label>
            To <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
          </label>{' '}
          <button type="submit">Search</button>
        </form>
      </section>

      <section style={section}>
        <button type="button" disabled={canWrite === false} onClick={() => navigate('/browse/new')}>
          New Note
        </button>
        {canWrite === false && (
          <p>Write access required — request it under My Tokens</p>
        )}
      </section>

      <div style={{ display: 'flex', gap: '2rem' }}>
        <section style={{ flex: 3 }}>
          <h2>Results</h2>
          {message && <p>{message}</p>}
          {results.map((r) => (
            <article key={r.stem} style={row}>
              <Link to={`/browse/${encodeURIComponent(r.stem)}`}>{r.title}</Link>
              {r.snippet && <p>{r.snippet}</p>}
              <p>
                {r.tags.join(', ')} — {r.created}
              </p>
            </article>
          ))}
        </section>

        <aside style={{ flex: 1 }}>
          <h2>Tags</h2>
          {tags.length === 0 ? (
            <p>No tags yet.</p>
          ) : (
            <ul>
              {tags.map((t) => (
                <li key={t.tag}>
                  <button type="button" onClick={() => onTagClick(t.tag)}>
                    {t.tag} ({t.count})
                  </button>
                </li>
              ))}
            </ul>
          )}
        </aside>
      </div>
    </main>
  )
}
