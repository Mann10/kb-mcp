import { useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { useAuth } from '../AuthContext'
import { Button } from '@/components/ui/button'
import { Field, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { ErrorNotice } from '@/components/feedback'

export default function LoginPage() {
  const { isLoggedIn, signIn, signUp } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [mode, setMode] = useState<'signin' | 'signup'>('signin')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  if (isLoggedIn) {
    return <Navigate to="/" replace />
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      if (mode === 'signin') {
        await signIn(email, password)
      } else {
        await signUp(email, password)
        // Open signup (D-03/D-04): no verification gate UI — sign in immediately.
        await signIn(email, password)
      }
      navigate('/')
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const creating = mode === 'signup'

  return (
    <div className="flex min-h-[70dvh] items-center justify-center">
      <div className="w-full max-w-sm">
        <h1 className="text-xl font-semibold tracking-tight">Sign in to KB Portal</h1>
        <p className="mt-1 mb-6 text-sm text-muted-foreground">
          Your account also controls which API tokens you can mint.
        </p>

        <ToggleGroup
          type="single"
          value={mode}
          onValueChange={(v) => {
            if (v) {
              setMode(v as 'signin' | 'signup')
              setError(null)
            }
          }}
          variant="outline"
          className="mb-5 w-full"
        >
          <ToggleGroupItem value="signin" className="flex-1">Sign in</ToggleGroupItem>
          <ToggleGroupItem value="signup" className="flex-1">Create account</ToggleGroupItem>
        </ToggleGroup>

        <ErrorNotice message={error} />

        <form onSubmit={handleSubmit}>
          <FieldGroup>
            <Field>
              <FieldLabel htmlFor="email">Email</FieldLabel>
              <Input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoComplete="email"
                autoFocus
                placeholder="you@example.com"
              />
            </Field>
            <Field>
              <FieldLabel htmlFor="password">Password</FieldLabel>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoComplete={creating ? 'new-password' : 'current-password'}
              />
            </Field>
            <Button type="submit" disabled={busy} className="w-full">
              {busy ? 'Please wait…' : creating ? 'Create account' : 'Sign in'}
            </Button>
          </FieldGroup>
        </form>

        <p className="mt-5 text-sm text-muted-foreground">
          {creating ? (
            <>
              Already registered?{' '}
              <button
                type="button"
                className="text-primary underline-offset-4 hover:underline"
                onClick={() => {
                  setMode('signin')
                  setError(null)
                }}
              >
                Sign in instead
              </button>
            </>
          ) : (
            <>
              Need an account?{' '}
              <button
                type="button"
                className="text-primary underline-offset-4 hover:underline"
                onClick={() => {
                  setMode('signup')
                  setError(null)
                }}
              >
                Create one
              </button>
            </>
          )}
        </p>
      </div>
    </div>
  )
}