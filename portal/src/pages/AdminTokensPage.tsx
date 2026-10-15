import { useEffect, useState } from 'react'
import { Navigate } from 'react-router-dom'
import { Check, RefreshCw, X, XCircle } from 'lucide-react'
import { useAuth } from '../AuthContext'
import OneTimeReveal from '../components/OneTimeReveal'
import TokenStatus from '../components/TokenStatus'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Empty, EmptyDescription, EmptyHeader, EmptyTitle } from '@/components/ui/empty'
import { Field, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { ErrorNotice, PageHeader, SectionTitle } from '@/components/feedback'
import { fmtDate } from '../format'

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

type Confirm =
  | { kind: 'revoke'; prefix: string }
  | { kind: 'rotate'; prefix: string }

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
  const [confirm, setConfirm] = useState<Confirm | null>(null)

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
    return (
      <div className="flex flex-col gap-3">
        <Skeleton className="h-7 w-40" />
        <Skeleton className="h-4 w-64" />
      </div>
    )
  }

  if (state.status === 'denied') {
    return (
      <div className="max-w-md">
        <PageHeader title="Token admin" />
        <ErrorNotice message={`${state.message} (HTTP ${state.httpStatus})`} />
      </div>
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

  const runConfirm = async () => {
    if (!confirm) return
    const { kind, prefix } = confirm
    setConfirm(null)
    if (kind === 'revoke') await revoke(prefix)
    else await rotate(prefix)
  }

  return (
    <>
      <PageHeader
        title="Token admin"
        description={`Approve write-access requests and manage every issued token. Signed in as ${state.email}.`}
      />

      {reveal && (
        <OneTimeReveal token={reveal.token} label={reveal.label} onDismiss={() => setReveal(null)} />
      )}

      <ErrorNotice message={error} />

      <section className="mb-9">
        <SectionTitle className="mb-3">
          Approval queue
          {pending.length > 0 && (
            <span className="ml-2 font-normal text-muted-foreground">{pending.length}</span>
          )}
        </SectionTitle>

        {pending.length === 0 ? (
          <Empty className="border border-dashed">
            <EmptyHeader>
              <EmptyTitle>No pending requests</EmptyTitle>
              <EmptyDescription>Write-access requests will appear here for approval.</EmptyDescription>
            </EmptyHeader>
          </Empty>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Requester</TableHead>
                <TableHead>Requested</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {pending.map((r) => (
                <TableRow key={r.id}>
                  <TableCell>{r.user_email}</TableCell>
                  <TableCell className="tabular whitespace-nowrap text-muted-foreground">
                    {fmtDate(r.created_at)}
                  </TableCell>
                  <TableCell>
                    <TokenStatus status={r.status} />
                  </TableCell>
                  <TableCell className="text-right whitespace-nowrap">
                    <Button size="sm" onClick={() => decide(r.id, 'approve')}>
                      <Check data-icon="inline-start" />
                      Approve
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => decide(r.id, 'deny')}
                    >
                      <X data-icon="inline-start" />
                      Deny
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}

        {history.length > 0 && (
          <div className="mt-7">
            <SectionTitle className="mb-2 text-muted-foreground">Decision history</SectionTitle>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Requester</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Decided</TableHead>
                  <TableHead>By</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {history.map((r) => (
                  <TableRow key={r.id}>
                    <TableCell>{r.user_email}</TableCell>
                    <TableCell>
                      <TokenStatus status={r.status} />
                    </TableCell>
                    <TableCell className="tabular whitespace-nowrap text-muted-foreground">
                      {r.decided_at ? fmtDate(r.decided_at) : '—'}
                    </TableCell>
                    <TableCell className="text-muted-foreground">{r.decided_by ?? '—'}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </section>

      <Separator className="mb-7" />

      <section className="mb-9 max-w-2xl">
        <SectionTitle className="mb-3">Mint a token directly</SectionTitle>
        <p className="mb-4 text-sm text-muted-foreground">
          Issues a token without a request. Use this for service accounts and CI.
        </p>
        <FieldGroup>
          <div className="grid gap-4 sm:grid-cols-3">
            <Field>
              <FieldLabel htmlFor="mint-email">Email</FieldLabel>
              <Input
                id="mint-email"
                type="email"
                value={mintEmail}
                onChange={(e) => setMintEmail(e.target.value)}
                placeholder="service@example.com"
              />
            </Field>
            <Field>
              <FieldLabel htmlFor="mint-type">Type</FieldLabel>
              <Select value={mintType} onValueChange={setMintType}>
                <SelectTrigger id="mint-type" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    <SelectItem value="read">Read</SelectItem>
                    <SelectItem value="read_write">Read and write</SelectItem>
                  </SelectGroup>
                </SelectContent>
              </Select>
            </Field>
            <Field>
              <FieldLabel htmlFor="mint-expiry">Expiry override</FieldLabel>
              <Input
                id="mint-expiry"
                type="date"
                value={mintExpiry}
                onChange={(e) => setMintExpiry(e.target.value)}
              />
            </Field>
          </div>
          <div>
            <Button type="button" onClick={directMint} disabled={!mintEmail.trim()}>
              Mint token
            </Button>
          </div>
        </FieldGroup>
      </section>

      <Separator className="mb-7" />

      <section>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <SectionTitle>
            All tokens
            {tokens.length > 0 && (
              <span className="ml-2 font-normal text-muted-foreground">{tokens.length}</span>
            )}
          </SectionTitle>
          <label className="flex cursor-pointer items-center gap-2 text-sm text-muted-foreground">
            <Checkbox
              checked={includeRevoked}
              onCheckedChange={(v) => setIncludeRevoked(v === true)}
            />
            Include revoked and expired
          </label>
        </div>

        {tokens.length === 0 ? (
          <Empty className="border border-dashed">
            <EmptyHeader>
              <EmptyTitle>No tokens issued</EmptyTitle>
              <EmptyDescription>Minted tokens for every user appear in this table.</EmptyDescription>
            </EmptyHeader>
          </Empty>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Owner</TableHead>
                <TableHead>Token</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Created</TableHead>
                <TableHead>Expires</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {tokens.map((t) => (
                <TableRow key={`${t.username}${t.prefix}${t.created_at}`}>
                  <TableCell>{t.username}</TableCell>
                  <TableCell className="font-mono text-[0.8125rem] tabular-nums">
                    {t.display}
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">{t.token_type}</TableCell>
                  <TableCell className="tabular whitespace-nowrap text-muted-foreground">
                    {fmtDate(t.created_at)}
                  </TableCell>
                  <TableCell className="tabular whitespace-nowrap text-muted-foreground">
                    {fmtDate(t.expires_at)}
                  </TableCell>
                  <TableCell>
                    <TokenStatus status={t.status} />
                  </TableCell>
                  <TableCell className="text-right whitespace-nowrap">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setConfirm({ kind: 'rotate', prefix: t.prefix })}
                    >
                      <RefreshCw data-icon="inline-start" />
                      Rotate
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-destructive hover:bg-destructive/10 hover:text-destructive"
                      onClick={() => setConfirm({ kind: 'revoke', prefix: t.prefix })}
                    >
                      <XCircle data-icon="inline-start" />
                      Revoke
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </section>

      <AlertDialog open={confirm !== null} onOpenChange={(o) => !o && setConfirm(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {confirm?.kind === 'rotate' ? 'Rotate this token?' : 'Revoke this token?'}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {confirm?.kind === 'rotate'
                ? `The current secret for ${confirm?.prefix}… stops working immediately and a new one is issued.`
                : `${confirm?.prefix}… will stop working immediately. Anything using it will fail.`}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={() => void runConfirm()}>
              {confirm?.kind === 'rotate' ? 'Rotate token' : 'Revoke token'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}