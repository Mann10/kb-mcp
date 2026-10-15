import { useCallback, useEffect, useState } from 'react'
import { KeyRound, RefreshCw, XCircle } from 'lucide-react'
import { useAuth } from '../AuthContext'
import OneTimeReveal from '../components/OneTimeReveal'
import TokenStatus from '../components/TokenStatus'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Empty, EmptyDescription, EmptyHeader, EmptyTitle } from '@/components/ui/empty'
import { Field, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Separator } from '@/components/ui/separator'
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
import { ErrorNotice, InfoNotice, PageHeader, SectionTitle } from '@/components/feedback'
import { fmtDate } from '../format'

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

type Confirm =
  | { kind: 'revoke'; prefix: string }
  | { kind: 'rotate'; prefix: string }

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
  const [confirm, setConfirm] = useState<Confirm | null>(null)

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

  const runConfirm = async () => {
    if (!confirm) return
    const { kind, prefix } = confirm
    setConfirm(null)
    if (kind === 'revoke') await revoke(prefix)
    else await rotate(prefix)
  }

  const pending = requests.filter((r) => r.status === 'pending')
  const decided = requests.filter((r) => r.status !== 'pending')

  return (
    <>
      <PageHeader
        title="My tokens"
        description="Credentials your tools use to read and write notes."
      />

      {reveal && (
        <OneTimeReveal token={reveal.token} label={reveal.label} onDismiss={() => setReveal(null)} />
      )}

      <ErrorNotice message={error} />
      <InfoNotice message={notice} />

      <section className="mb-9 max-w-md">
        <SectionTitle className="mb-3">Mint a read token</SectionTitle>
        <div className="flex items-end gap-3">
          <Field className="w-44">
            <FieldLabel htmlFor="expiry">Expires</FieldLabel>
            <Input
              id="expiry"
              type="date"
              value={expiryDate}
              onChange={(e) => setExpiryDate(e.target.value)}
            />
          </Field>
          <Button type="button" onClick={mint}>
            <KeyRound data-icon="inline-start" />
            Mint read token
          </Button>
        </div>
      </section>

      <Separator className="mb-7" />

      <section className="mb-9">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <SectionTitle>
            Tokens
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

        {/* include revoked toggle defaults to active-only (D-15) */}
        {tokens.length === 0 ? (
          <Empty className="border border-dashed">
            <EmptyHeader>
              <EmptyTitle>No tokens yet</EmptyTitle>
              <EmptyDescription>
                Mint a read token above to give a script or tool access to the knowledge base.
              </EmptyDescription>
            </EmptyHeader>
          </Empty>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
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
                <TableRow key={`${t.prefix}${t.suffix}${t.created_at}`}>
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

      <Separator className="mb-7" />

      <section className="max-w-2xl">
        <SectionTitle className="mb-3">Write access</SectionTitle>
        <p className="mb-4 text-sm text-muted-foreground">
          Read tokens can only fetch notes. Write access lets you create and edit them.
        </p>

        {pending.length > 0 ? (
          <ul className="flex flex-col gap-2">
            {pending.map((r) => (
              <li
                key={r.id}
                className="flex items-center gap-3 rounded-lg border bg-card px-3 py-2"
              >
                <TokenStatus status={r.status} />
                <span className="tabular text-muted-foreground">
                  requested {fmtDate(r.created_at)}
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  className="ml-auto"
                  onClick={() => void cancelRequest(r.id)}
                >
                  Cancel
                </Button>
              </li>
            ))}
          </ul>
        ) : (
          <Button type="button" variant="outline" onClick={requestUpgrade}>
            Request write access
          </Button>
        )}

        {decided.length > 0 && (
          <div className="mt-6">
            <SectionTitle className="mb-2 text-muted-foreground">Past requests</SectionTitle>
            <ul className="flex flex-col gap-1.5">
              {decided.map((r) => (
                <li key={r.id} className="flex flex-wrap items-center gap-3 text-sm">
                  <TokenStatus status={r.status} />
                  <span className="tabular text-muted-foreground">
                    {r.decided_at ? fmtDate(r.decided_at) : fmtDate(r.created_at)}
                  </span>
                  {r.status === 'denied' && (
                    <Button variant="link" size="sm" onClick={requestUpgrade} className="h-auto p-0">
                      Request again
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          </div>
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