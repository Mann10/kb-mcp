import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Save } from 'lucide-react'
import { useAuth } from '../AuthContext'
import { Button } from '@/components/ui/button'
import { Field, FieldDescription, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { ErrorNotice, PageHeader } from '@/components/feedback'

interface Template {
  name: string
  body_skeleton: string
  default_tags: string[]
}

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
    <>
      <PageHeader
        title={mode === 'create' ? 'New note' : 'Edit note'}
        description={
          mode === 'create'
            ? 'Notes are stored as Markdown. The title becomes the note’s filename.'
            : 'Changing the title renames the note and its URL.'
        }
      />

      <ErrorNotice message={error} />

      <FieldGroup className="max-w-3xl">
        {mode === 'create' && (
          <Field className="max-w-xs">
            <FieldLabel htmlFor="template">Template</FieldLabel>
            <Select value={template} onValueChange={applyTemplate}>
              <SelectTrigger id="template" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  <SelectItem value="blank">Blank</SelectItem>
                  {templates.map((t) => (
                    <SelectItem key={t.name} value={t.name}>
                      {t.name}
                    </SelectItem>
                  ))}
                </SelectGroup>
              </SelectContent>
            </Select>
          </Field>
        )}

        <Field>
          <FieldLabel htmlFor="title">Title</FieldLabel>
          <Input
            id="title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="What this note is about"
          />
        </Field>

        <div className="grid gap-5 sm:grid-cols-2">
          <Field>
            <FieldLabel htmlFor="tags">Tags</FieldLabel>
            <Input
              id="tags"
              value={tags}
              onChange={(e) => setTags(e.target.value)}
              placeholder="auth, backend"
            />
            <FieldDescription>Comma-separated.</FieldDescription>
          </Field>
          <Field>
            <FieldLabel htmlFor="created">Created</FieldLabel>
            <Input
              id="created"
              type="date"
              value={created}
              onChange={(e) => setCreated(e.target.value)}
            />
            <FieldDescription>Leave blank to use today’s date.</FieldDescription>
          </Field>
        </div>

        <Field>
          <FieldLabel htmlFor="body">Body</FieldLabel>
          <Textarea
            id="body"
            value={body}
            onChange={(e) => setBody(e.target.value)}
            rows={22}
            className="font-mono text-[0.8125rem] leading-relaxed"
          />
        </Field>

        <div className="flex items-center gap-2">
          <Button type="button" onClick={save}>
            <Save data-icon="inline-start" />
            {mode === 'create' ? 'Create note' : 'Save changes'}
          </Button>
          <Button variant="ghost" asChild>
            <Link to={mode === 'create' ? '/browse' : `/browse/${encodeURIComponent(stem ?? '')}`}>
              Cancel
            </Link>
          </Button>
        </div>
      </FieldGroup>
    </>
  )
}