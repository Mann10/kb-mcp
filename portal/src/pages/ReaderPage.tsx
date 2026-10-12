import { useCallback, useEffect, useState } from 'react'
import type { CSSProperties } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useAuth } from '../AuthContext'

interface Note {
  stem: string
  title: string
  tags: string[]
  created: string
  body: string
}

const section: CSSProperties = { marginBottom: '1.5rem' }

// BFF contracts (Plans 01/02): authFetch("/api/notes/get?stem="),
// authFetch("/api/notes/delete"), authFetch("/api/notes/add-tags"),
// authFetch("/api/notes/remove-tags"), authFetch("/api/notes/can_write").

export default function ReaderPage() {
  const { authFetch } = useAuth()
  const { stem } = useParams<{ stem: string }>()
  const navigate = useNavigate()
  const [note, setNote] = useState<Note | null>(null)
  const [canWrite, setCanWrite] = useState<boolean | null>(null)
  const [tagInput, setTagInput] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const fail = (res: Response, body: { message?: string } | null, fallback: string) => {
    setError(body?.message ?? `${fallback} (HTTP ${res.status})`)
  }

  const load = useCallback(async () => {
    if (!stem) return
    setError(null)
    const [getRes, writeRes] = await Promise.all([
      authFetch(`/api/notes/get?stem=${encodeURIComponent(stem)}`),
      authFetch('/api/notes/can_write'),
    ])
    const body = (await getRes.json().catch(() => null)) as {
      note?: Note
      message?: string
    } | null
    if (!getRes.ok || !body?.note) {
      fail(getRes, body, 'Load failed.')
      setNote(null)
      return
    }
    setNote(body.note)
    if (writeRes.ok) {
      const wbody = (await writeRes.json().catch(() => null)) as { can_write?: boolean } | null
      setCanWrite(wbody?.can_write ?? false)
    }
  }, [authFetch, stem])

  useEffect(() => {
    load().catch(() => setError('Could not load note.'))
  }, [load])

  const remove = async () => {
    if (!note) return
    if (!window.confirm(`Delete ${note.title}? This cannot be undone.`)) return
    setError(null)
    const res = await authFetch('/api/notes/delete', {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ stem: note.stem }),
    })
    if (!res.ok) {
      const body = (await res.json().catch(() => null)) as { message?: string } | null
      fail(res, body, 'Delete failed.')
      return
    }
    navigate('/browse')
  }

  const addTag = async () => {
    if (!note || !tagInput.trim()) return
    setError(null)
    setNotice(null)
    const res = await authFetch('/api/notes/add-tags', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ stem: note.stem, tags: [tagInput.trim()] }),
    })
    const body = (await res.json().catch(() => null)) as {
      note?: Note
      message?: string
    } | null
    if (!res.ok) {
      fail(res, body, 'Add tag failed.')
      return
    }
    if (body?.note) setNote(body.note)
    if (body?.message) setNotice(body.message)
    setTagInput('')
  }

  const removeTag = async (t: string) => {
    if (!note) return
    setError(null)
    setNotice(null)
    const res = await authFetch('/api/notes/remove-tags', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ stem: note.stem, tags: [t] }),
    })
    const body = (await res.json().catch(() => null)) as {
      note?: Note
      message?: string
    } | null
    if (!res.ok) {
      fail(res, body, 'Remove tag failed.')
      return
    }
    if (body?.note) setNote(body.note)
    if (body?.message) setNotice(body.message)
  }

  if (!note && error) {
    return (
      <main style={{ padding: '2rem' }}>
        <p role="alert">{error}</p>
        <p>
          <Link to="/browse">Back to Browse</Link>
        </p>
      </main>
    )
  }

  if (!note) {
    return (
      <main style={{ padding: '2rem' }}>
        <p>Loading…</p>
      </main>
    )
  }

  const readOnly = canWrite === false

  return (
    <main style={{ padding: '2rem' }}>
      <p>
        <Link to="/browse">Back to Browse</Link>
      </p>
      <h1>{note.title}</h1>
      {error && <p role="alert">{error}</p>}
      {notice && <p>{notice}</p>}
      <p>
        {note.tags.join(', ')} — {note.created}
      </p>
      <section style={section}>
        <pre style={{ whiteSpace: 'pre-wrap' }}>{note.body}</pre>
      </section>

      <section style={section}>
        <button
          type="button"
          disabled={readOnly}
          onClick={() => navigate(`/browse/${encodeURIComponent(note.stem)}/edit`)}
        >
          Edit
        </button>{' '}
        <button type="button" disabled={readOnly} onClick={remove}>
          Delete
        </button>
        {readOnly && <p>Write access required — request it under My Tokens</p>}
      </section>

      <section style={section}>
        <h2>Tags</h2>
        <ul>
          {note.tags.map((t) => (
            <li key={t}>
              {t}{' '}
              <button type="button" disabled={readOnly} onClick={() => removeTag(t)}>
                Remove
              </button>
            </li>
          ))}
        </ul>
        <label>
          Add tag{' '}
          <input
            type="text"
            value={tagInput}
            onChange={(e) => setTagInput(e.target.value)}
            disabled={readOnly}
          />
        </label>{' '}
        <button type="button" disabled={readOnly} onClick={addTag}>
          Add
        </button>
      </section>
    </main>
  )
}
