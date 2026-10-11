import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../AuthContext'

interface MeResponse {
  id: string
  email: string
  is_admin: boolean
}

export default function SessionHeader() {
  const { isLoggedIn, session, signOut, authFetch } = useAuth()
  const [me, setMe] = useState<MeResponse | null>(null)
  const [checking, setChecking] = useState(false)

  useEffect(() => {
    if (!isLoggedIn) {
      setMe(null)
      return
    }
    let cancelled = false
    setChecking(true)
    authFetch('/api/me')
      .then(async (res) => {
        if (!res.ok) return null
        return (await res.json()) as MeResponse
      })
      .then((data) => {
        if (!cancelled) setMe(data)
      })
      .catch(() => {
        if (!cancelled) setMe(null)
      })
      .finally(() => {
        if (!cancelled) setChecking(false)
      })
    return () => {
      cancelled = true
    }
  }, [isLoggedIn, session, authFetch])

  if (!isLoggedIn) {
    return (
      <header style={{ display: 'flex', gap: '1rem', padding: '0.75rem 1rem', borderBottom: '1px solid #ddd' }}>
        <span>KB Portal</span>
        <span style={{ marginLeft: 'auto' }}>
          <Link to="/login">Login</Link>
        </span>
      </header>
    )
  }

  return (
    <header style={{ display: 'flex', gap: '1rem', padding: '0.75rem 1rem', borderBottom: '1px solid #ddd' }}>
      <span>KB Portal</span>
      <span style={{ marginLeft: 'auto' }}>
        {checking ? (
          'Checking session…'
        ) : me ? (
          <>
            {me.email}{' '}
            {me.is_admin && (
              <strong style={{ marginLeft: '0.5rem' }}>Admin</strong>
            )}
          </>
        ) : (
          (session?.user?.email ?? 'Signed in')
        )}{' '}
        <button type="button" onClick={() => void signOut()} style={{ marginLeft: '0.75rem' }}>
          Sign out
        </button>
      </span>
    </header>
  )
}
