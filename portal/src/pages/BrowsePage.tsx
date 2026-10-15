import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { FilePlus2, Search } from 'lucide-react'
import { useAuth } from '../AuthContext'
import { Button } from '@/components/ui/button'
import { Empty, EmptyDescription, EmptyHeader, EmptyTitle } from '@/components/ui/empty'
import { Field, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { ErrorNotice, PageHeader, SectionTitle } from '@/components/feedback'
import { fmtDate } from '../format'

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
  const [loading, setLoading] = useState(true)

  const fail = (res: Response, body: { message?: string } | null, fallback: string) => {
    setError(body?.message ?? `${fallback} (HTTP ${res.status})`)
  }

  const runSearch = useCallback(
    async (opts: { q: string; tag: string; dateFrom: string; dateTo: string }) => {
      setError(null)
      setLoading(true)
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
        setLoading(false)
        return
      }
      // Server order is v1 rank order — never re-sort on the client (D-07).
      setResults(body?.results ?? [])
      setMessage(body?.message ?? null)
      setLoading(false)
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
      if (!cancelled) setLoading(false)
    }
    load().catch(() => {
      if (!cancelled) {
        setError('Could not load notes.')
        setLoading(false)
      }
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
    <>
      <PageHeader
        title="Browse notes"
        description="Search the knowledge base by keyword, tag, or date."
        actions={
          <Button
            onClick={() => navigate('/browse/new')}
            disabled={canWrite === false}
            title={canWrite === false ? 'Write access required' : undefined}
          >
            <FilePlus2 data-icon="inline-start" />
            New note
          </Button>
        }
      />

      {canWrite === false && (
        <p className="mb-5 text-sm text-muted-foreground">
          You have read-only access. Request write access under{' '}
          <Link to="/tokens" className="text-primary underline-offset-4 hover:underline">
            My tokens
          </Link>{' '}
          to create and edit notes.
        </p>
      )}

      <ErrorNotice message={error} />

      <form
        onSubmit={(e) => {
          e.preventDefault()
          onSearch()
        }}
        className="mb-7"
      >
        <FieldGroup>
          <Field>
            <FieldLabel htmlFor="q">Search</FieldLabel>
            <Input
              id="q"
              type="search"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="keyword"
            />
          </Field>
          <div className="grid gap-4 sm:grid-cols-3">
            <Field>
              <FieldLabel htmlFor="tag">Tag</FieldLabel>
              <Select value={tag} onValueChange={setTag}>
                <SelectTrigger id="tag" className="w-full">
                  <SelectValue placeholder="Any tag" />
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    <SelectItem value="">Any tag</SelectItem>
                    {tags.map((t) => (
                      <SelectItem key={t.tag} value={t.tag}>
                        {t.tag} ({t.count})
                      </SelectItem>
                    ))}
                  </SelectGroup>
                </SelectContent>
              </Select>
            </Field>
            <Field>
              <FieldLabel htmlFor="dateFrom">From</FieldLabel>
              <Input
                id="dateFrom"
                type="date"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
              />
            </Field>
            <Field>
              <FieldLabel htmlFor="dateTo">To</FieldLabel>
              <Input
                id="dateTo"
                type="date"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
              />
            </Field>
          </div>
          <div>
            <Button type="submit" disabled={loading}>
              <Search data-icon="inline-start" />
              Search
            </Button>
          </div>
        </FieldGroup>
      </form>

      <div className="flex flex-col gap-8 lg:flex-row">
        <section className="min-w-0 flex-1">
          <SectionTitle className="mb-3">
            Results
            {!loading && results.length > 0 && (
              <span className="ml-2 font-normal text-muted-foreground">{results.length}</span>
            )}
          </SectionTitle>

          {message && <p className="mb-3 text-sm text-muted-foreground">{message}</p>}

          {loading ? (
            <div className="flex flex-col gap-4">
              {[0, 1, 2].map((i) => (
                <div key={i} className="flex flex-col gap-2">
                  <Skeleton className="h-4 w-1/3" />
                  <Skeleton className="h-3 w-2/3" />
                </div>
              ))}
            </div>
          ) : results.length === 0 ? (
            <Empty className="border border-dashed">
              <EmptyHeader>
                <EmptyTitle>No notes matched</EmptyTitle>
                <EmptyDescription>
                  Try a different keyword, widen the date range, or clear the tag filter.
                </EmptyDescription>
              </EmptyHeader>
            </Empty>
          ) : (
            <ul className="flex flex-col">
              {results.map((r, i) => (
                <li key={r.stem}>
                  {i > 0 && <Separator />}
                  <article className="py-3.5">
                    <Link
                      to={`/browse/${encodeURIComponent(r.stem)}`}
                      className="text-[0.9375rem] font-medium underline-offset-4 hover:text-primary hover:underline"
                    >
                      {r.title}
                    </Link>
                    {r.snippet && (
                      <p className="mt-1 max-w-[70ch] text-sm text-muted-foreground">
                        {r.snippet}
                      </p>
                    )}
                    <div className="mt-2 flex flex-wrap items-center gap-1.5">
                      {r.tags.map((t) => (
                        <Badge key={t} variant="outline" className="font-normal">
                          {t}
                        </Badge>
                      ))}
                      <span className="tabular ml-auto text-muted-foreground">
                        {fmtDate(r.created)}
                      </span>
                    </div>
                  </article>
                </li>
              ))}
            </ul>
          )}
        </section>

        <aside className="w-full shrink-0 lg:w-52">
          <SectionTitle className="mb-3">Tags</SectionTitle>
          {tags.length === 0 ? (
            <p className="text-sm text-muted-foreground">No tags yet.</p>
          ) : (
            <ul className="flex flex-wrap gap-1.5 lg:flex-col lg:items-start">
              {tags.map((t) => (
                <li key={t.tag}>
                  <button
                    type="button"
                    onClick={() => onTagClick(t.tag)}
                    aria-pressed={tag === t.tag}
                    className={
                      tag === t.tag
                        ? 'rounded-md border border-primary/40 bg-accent px-2 py-0.5 text-sm text-accent-foreground'
                        : 'rounded-md px-2 py-0.5 text-sm text-muted-foreground transition-colors hover:bg-accent/60 hover:text-foreground'
                    }
                  >
                    {t.tag}{' '}
                    <span className="tabular text-muted-foreground">{t.count}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </aside>
      </div>
    </>
  )
}