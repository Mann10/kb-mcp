import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { NavLink } from 'react-router-dom'
import { BookText, KeyRound, LogOut, ShieldCheck } from 'lucide-react'
import { useAuth } from '../AuthContext'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'

interface MeResponse {
  id: string
  email: string
  is_admin: boolean
}

const navLink = 'flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-sm transition-colors'

/**
 * Application shell: a fixed navigation rail plus the page column.
 *
 * The rail carries the session identity (moved off the old top bar) and the
 * admin link, which only renders once /api/me confirms the caller is an
 * admin. Active section is marked with a petrol bar in the gutter, not a
 * colour change on the label.
 */
export default function AppShell({ children }: { children: ReactNode }) {
  const { isLoggedIn, session, signOut, authFetch } = useAuth()
  const [me, setMe] = useState<MeResponse | null>(null)

  useEffect(() => {
    if (!isLoggedIn) {
      setMe(null)
      return
    }
    let cancelled = false
    authFetch('/api/me')
      .then(async (res) => (res.ok ? ((await res.json()) as MeResponse) : null))
      .then((data) => {
        if (!cancelled) setMe(data)
      })
      .catch(() => {
        if (!cancelled) setMe(null)
      })
    return () => {
      cancelled = true
    }
  }, [isLoggedIn, session, authFetch])

  const identity = me?.email ?? session?.user?.email ?? 'Signed in'

  return (
    <div className="flex min-h-dvh flex-col lg:flex-row">
      <aside className="flex shrink-0 flex-col border-b bg-sidebar lg:h-dvh lg:w-60 lg:border-r lg:border-b-0 lg:sticky lg:top-0">
        <div className="flex items-baseline gap-2 px-4 pt-4 pb-3 lg:pt-5">
          <span className="text-[0.9375rem] font-semibold tracking-tight">KB Portal</span>
          <span className="tabular text-[0.6875rem] text-muted-foreground">uif</span>
        </div>

        <nav className="flex gap-1 overflow-x-auto px-2 pb-3 lg:flex-col lg:overflow-visible">
          {(
            [
              { to: '/browse', label: 'Browse notes', icon: BookText },
              { to: '/tokens', label: 'My tokens', icon: KeyRound },
            ] as const
          ).map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                cn(
                  navLink,
                  'relative shrink-0 whitespace-nowrap',
                  isActive
                    ? 'bg-accent font-medium text-accent-foreground before:absolute before:inset-y-1.5 before:left-0 before:w-0.5 before:rounded-full before:bg-primary'
                    : 'text-muted-foreground hover:bg-accent/60 hover:text-foreground',
                )
              }
            >
              <Icon className="size-4 shrink-0" aria-hidden />
              {label}
            </NavLink>
          ))}

          {me?.is_admin && (
            <>
              <Separator className="my-2 hidden lg:block" />
              <NavLink
                to="/admin/tokens"
                className={({ isActive }) =>
                  cn(
                    navLink,
                    'relative shrink-0 whitespace-nowrap',
                    isActive
                      ? 'bg-accent font-medium text-accent-foreground before:absolute before:inset-y-1.5 before:left-0 before:w-0.5 before:rounded-full before:bg-primary'
                      : 'text-muted-foreground hover:bg-accent/60 hover:text-foreground',
                  )
                }
              >
                <ShieldCheck className="size-4 shrink-0" aria-hidden />
                Token admin
              </NavLink>
            </>
          )}
        </nav>

        <div className="mt-auto hidden flex-col gap-2 px-4 py-4 lg:flex">
          <div className="min-w-0">
            <p className="truncate text-sm" title={identity}>
              {identity}
            </p>
            {me?.is_admin && (
              <p className="tabular text-[0.6875rem] text-muted-foreground">admin</p>
            )}
          </div>
          {isLoggedIn ? (
            <Button variant="ghost" size="sm" onClick={() => void signOut()} className="justify-start">
              <LogOut data-icon="inline-start" />
              Sign out
            </Button>
          ) : (
            <Button size="sm" asChild className="justify-start">
              <NavLink to="/login">Sign in</NavLink>
            </Button>
          )}
        </div>
      </aside>

      {isLoggedIn && (
        <div className="flex items-center justify-between gap-3 border-b px-4 py-2 lg:hidden">
          <span className="min-w-0 truncate text-sm">{identity}</span>
          <Button variant="ghost" size="sm" onClick={() => void signOut()}>
            <LogOut data-icon="inline-start" />
            Sign out
          </Button>
        </div>
      )}

      <main className="min-w-0 flex-1 px-5 py-6 sm:px-8 sm:py-8">{children}</main>
    </div>
  )
}