import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, Pencil, Tag as TagIcon, Trash2, X } from 'lucide-react'
import { useAuth } from '../AuthContext'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { Skeleton } from '@/components/ui/skeleton'
import { Input } from '@/components/ui/input'
import { Field, FieldLabel } from '@/components/ui/field'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import { ErrorNotice, InfoNotice, SectionTitle } from '@/components/feedback'
import { fmtDate } from '../format'

interface Note {
  stem: string
  title: string
  tags: string[]
  created: string
  body: string
}

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
      <div className="max-w-md">
        <ErrorNotice message={error} />
        <Button variant="outline" asChild>
          <Link to="/browse">
            <ArrowLeft data-icon="inline-start" />
            Back to browse
          </Link>
        </Button>
      </div>
    )
  }

  if (!note) {
    return (
      <div className="flex flex-col gap-3">
        <Skeleton className="h-7 w-1/2" />
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-40 w-full" />
      </div>
    )
  }

  const readOnly = canWrite === false

  return (
    <>
      <Button variant="ghost" size="sm" asChild className="-ml-2 mb-4">
        <Link to="/browse">
          <ArrowLeft data-icon="inline-start" />
          Browse
        </Link>
      </Button>

      <ErrorNotice message={error} />
      <InfoNotice message={notice} />

      <header className="mb-5 border-b pb-4">
        <h1 className="text-xl font-semibold tracking-tight">{note.title}</h1>
        <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
          {note.tags.map((t) => (
            <Badge key={t} variant="outline" className="font-normal">
              {t}
            </Badge>
          ))}
          <span className="tabular ml-auto text-muted-foreground">{fmtDate(note.created)}</span>
        </div>
      </header>

      <div className="mb-7 flex flex-wrap items-center gap-2">
        <Button
          disabled={readOnly}
          onClick={() => navigate(`/browse/${encodeURIComponent(note.stem)}/edit`)}
        >
          <Pencil data-icon="inline-start" />
          Edit
        </Button>

        {!readOnly && (
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button variant="destructive">
                <Trash2 data-icon="inline-start" />
                Delete
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Delete this note?</AlertDialogTitle>
                <AlertDialogDescription>
                  {note.title} will be removed. This cannot be undone.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction onClick={() => void remove()}>Delete note</AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        )}

        {readOnly && (
          <p className="text-sm text-muted-foreground">
            Read-only. Request write access under{' '}
            <Link to="/tokens" className="text-primary underline-offset-4 hover:underline">
              My tokens
            </Link>
            .
          </p>
        )}
      </div>

      <article className="mb-9">
        <pre className="note-body whitespace-pre-wrap">{note.body}</pre>
      </article>

      <Separator className="mb-6" />

      <section>
        <SectionTitle className="mb-3 flex items-center gap-2">
          <TagIcon className="size-3.5 text-muted-foreground" aria-hidden />
          Tags
        </SectionTitle>

        {note.tags.length > 0 && (
          <ul className="mb-4 flex flex-wrap gap-1.5">
            {note.tags.map((t) => (
              <li key={t}>
                <Badge variant="secondary" className="gap-1 pr-1 font-normal">
                  {t}
                  <button
                    type="button"
                    onClick={() => void removeTag(t)}
                    disabled={readOnly}
                    aria-label={`Remove tag ${t}`}
                    className="rounded-full p-0.5 text-muted-foreground transition-colors hover:text-destructive disabled:pointer-events-none disabled:opacity-40"
                  >
                    <X className="size-3" aria-hidden />
                  </button>
                </Badge>
              </li>
            ))}
          </ul>
        )}

        <div className="flex max-w-sm items-end gap-2">
          <Field className="flex-1">
            <FieldLabel htmlFor="add-tag">Add a tag</FieldLabel>
            <Input
              id="add-tag"
              value={tagInput}
              onChange={(e) => setTagInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault()
                  void addTag()
                }
              }}
              disabled={readOnly}
              placeholder="e.g. auth"
            />
          </Field>
          <Button type="button" onClick={() => void addTag()} disabled={readOnly || !tagInput.trim()}>
            Add
          </Button>
        </div>
      </section>
    </>
  )
}