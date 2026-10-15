import { useEffect, useState } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuth } from '../AuthContext'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorNotice, InfoNotice, PageHeader } from '@/components/feedback'

type AdminState =
  | { status: 'loading' }
  | { status: 'denied'; message: string; httpStatus: number }
  | { status: 'granted'; email: string }

export default function AdminPlaceholderPage() {
  const { isLoggedIn, session, authFetch } = useAuth()
  const [state, setState] = useState<AdminState>({ status: 'loading' })

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

  if (!isLoggedIn) {
    return <Navigate to="/login" replace />
  }

  if (state.status === 'loading') {
    return (
      <div className="flex flex-col gap-3">
        <Skeleton className="h-7 w-32" />
        <Skeleton className="h-4 w-56" />
      </div>
    )
  }

  if (state.status === 'denied') {
    return (
      <div className="max-w-md">
        <PageHeader title="Admin" />
        <ErrorNotice message={`${state.message} (HTTP ${state.httpStatus})`} />
      </div>
    )
  }

  return (
    <>
      <PageHeader title="Admin" />
      <InfoNotice message="Admin shell — token queue ships in Phase 11." />
      <p className="text-sm text-muted-foreground">{state.email}</p>
    </>
  )
}