import { useEffect, useState } from 'react'
import type { CSSProperties } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useAuth } from '../AuthContext'

interface Template {
  name: string
  body_skeleton: string
  default_tags: string[]
}

const section: CSSProperties = { marginBottom: '1.5rem' }
const field: CSSProperties = { display: 'block', marginBottom: '0.75rem' }

// BFF contracts (Plans 01/02): authFetch("/api/notes/templates"),
// authFetch("/api/notes/create"), authFetch("/api/notes/create-from-template"),
// authFetch("/api/notes/get?stem="), authFetch("/api/notes/update").

export default function NoteEditorPage({ mode }: { mode: 'create' | 'edit' }) {
  const { authFetch } = useAuth()
  const { stem } = useParams<{ stem: string }>()
  const navigate = useNavigate()
  const [templates, setTemplates] = useState<Template[]>([])
  const [template, setTemplate] = useState('blank')
  const [title, setTitle] = useState('')
  const [tags, setTags] = useState('')
  const [created, setCreated] = useState('')
  const [body, setBody] = useState('')
  const [error, setError] = useState<string | null>(null)

  const fail = (res: Response, respBody: { message?: string } | null, fallback: string) => {
    setError(respBody?.message ?? `${fallback} (HTTP ${res.status})`)
  }

  useEffect(() => {
    if (mode !== 'create') return
    let cancelled = false
    authFetch('/api/notes/templates')
      .then(async (res) => {
        if (!res.ok || cancelled) return
        const data = (await res.json().catch(() => null)) as { templates?: Template[] } | null
        if (!cancelled) setTemplates(data?.templates ?? [])
      })
      .catch(() => {
        if (!cancelled) setError('Could not load templates.')
      })
    return () => {
      cancelled = true
    }
  }, [authFetch, mode])

  useEffect(() => {
    if (mode !== 'edit' || !stem) return
    let cancelled = false
    authFetch(`/api/notes/get?stem=${encodeURIComponent(stem)}`)
      .then(async (res) => {
        const data = (await res.json().catch(() => null)) as {
          note?: { title: string; tags: string[]; created: string; body: string }
          message?: string
        } | null
        if (cancelled) return
        if (!res.ok || !data?.note) {
          fail(res, data, 'Load failed.')
          return
        }
        setTitle(data.note.title)
        setTags(data.note.tags.join(', '))
        setCreated(data.note.created)
        setBody(data.note.body)
      })
      .catch(() => {
        if (!cancelled) setError('Could not load note.')
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, stem])

  const applyTemplate = (name: string) => {
    setTemplate(name)
    if (name === 'blank') return
    const spec = templates.find((t) => t.name === name)
    if (!spec) return
    // D-09 override-merge pre-fill: user edits before save.
    setBody(spec.body_skeleton)
    setTags(spec.default_tags.join(', '))
  }

  const tagList = () =>
    tags
      .split(',')
      .map((t) => t.trim())
      .filter(Boolean)

  const save = async () => {
    setError(null)
    if (mode === 'create') {
      const payload = {
        title,
        body,
        tags: tagList(),
        ...(created.trim() ? { created: created.trim() } : {}),
      }
      const path = template === 'blank' ? '/api/notes/create' : '/api/notes/create-from-template'
      const reqBody =
        template === 'blank' ? payload : { template, ...payload }
      const res = await authFetch(path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(reqBody),
      })
      const data = (await res.json().catch(() => null)) as {
        note?: { stem: string }
        message?: string
      } | null
      if (!res.ok || !data?.note) {
        // D-16: render verbatim, inputs preserved.
        fail(res, data, 'Save failed.')
        return
      }
      navigate(`/browse/${encodeURIComponent(data.note.stem)}`)
      return
    }
    if (!stem) {
      setError('Missing note stem.')
      return
    }
    const res = await authFetch('/api/notes/update', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        stem,
        new_title: title,
        body,
        tags: tagList(),
        ...(created.trim() ? { created: created.trim() } : {}),
      }),
    })
    const data = (await res.json().catch(() => null)) as {
      new_stem?: string
      message?: string
    } | null
    if (!res.ok || !data?.new_stem) {
      // D-16: rename-collision and 403 render verbatim, inputs preserved.
      fail(res, data, 'Save failed.')
      return
    }
    // D-11: title-rename navigates to the new stem.
    navigate(`/browse/${encodeURIComponent(data.new_stem)}`)
  }

  return (
    <main style={{ padding: '2rem' }}>
      <h1>{mode === 'create' ? 'New Note' : 'Edit Note'}</h1>
      {error && <p role="alert">{error}</p>}

      {mode === 'create' && (
        <section style={section}>
          <label>
            Template{' '}
            <select value={template} onChange={(e) => applyTemplate(e.target.value)}>
              <option value="blank">Blank</option>
              {templates.map((t) => (
                <option key={t.name} value={t.name}>
                  {t.name}
                </option>
              ))}
            </select>
          </label>
        </section>
      )}

      <section style={section}>
        <label style={field}>
          Title{' '}
          <input type="text" value={title} onChange={(e) => setTitle(e.target.value)} />
        </label>
        <label style={field}>
          Tags (comma-separated){' '}
          <input type="text" value={tags} onChange={(e) => setTags(e.target.value)} />
        </label>
        <label style={field}>
          Created{' '}
          <input type="date" value={created} onChange={(e) => setCreated(e.target.value)} />
        </label>
        <label style={field}>
          Body{' '}
          <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={20} cols={80} />
        </label>
        <button type="button" onClick={save}>
          Save
        </button>{' '}
        <Link to={mode === 'create' ? '/browse' : `/browse/${encodeURIComponent(stem ?? '')}`}>
          Cancel
        </Link>
      </section>
    </main>
  )
}
