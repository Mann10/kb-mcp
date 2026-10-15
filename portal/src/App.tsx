import type { ReactNode } from 'react'
import { Link, Navigate, Route, Routes } from 'react-router-dom'
import { BookText, KeyRound, ShieldCheck } from 'lucide-react'
import { useAuth } from './AuthContext'
import AppShell from './components/AppShell'
import AdminPlaceholderPage from './pages/AdminPlaceholderPage'
import AdminTokensPage from './pages/AdminTokensPage'
import BrowsePage from './pages/BrowsePage'
import LoginPage from './pages/LoginPage'
import NoteEditorPage from './pages/NoteEditorPage'
import ReaderPage from './pages/ReaderPage'
import TokensPage from './pages/TokensPage'
import { PageHeader } from '@/components/feedback'

function Home() {
  return (
    <>
      <PageHeader
        title="KB Portal"
        description="Internal engineering notes and the API tokens that read them."
      />
      <div className="grid max-w-2xl gap-3 sm:grid-cols-2">
        <EntryCard
          to="/browse"
          icon={BookText}
          title="Browse notes"
          body="Search the knowledge base by keyword, tag, or date."
        />
        <EntryCard
          to="/tokens"
          icon={KeyRound}
          title="My tokens"
          body="Mint, rotate, and revoke the credentials your tools use."
        />
        <EntryCard
          to="/admin/tokens"
          icon={ShieldCheck}
          title="Token admin"
          body="Approve write-access requests and manage issued tokens."
          className="sm:col-span-2"
        />
      </div>
    </>
  )
}

function EntryCard({
  to,
  icon: Icon,
  title,
  body,
  className,
}: {
  to: string
  icon: typeof BookText
  title: string
  body: string
  className?: string
}) {
  return (
    <Link
      to={to}
      className={`group flex flex-col gap-1.5 rounded-lg border bg-card p-4 transition-colors hover:border-primary/40 hover:bg-accent/40 ${className ?? ''}`}
    >
      <span className="flex items-center gap-2 text-sm font-medium">
        <Icon className="size-4 text-primary" aria-hidden />
        {title}
      </span>
      <span className="text-sm text-muted-foreground">{body}</span>
    </Link>
  )
}

function RequireAuth({ children }: { children: ReactNode }) {
  const { isLoggedIn, isInitialized } = useAuth()
  if (!isInitialized) {
    return (
      <p className="py-16 text-center text-sm text-muted-foreground">Checking your session…</p>
    )
  }
  if (!isLoggedIn) {
    return <Navigate to="/login" replace />
  }
  return children
}

export default function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<RequireAuth><Home /></RequireAuth>} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/tokens" element={<RequireAuth><TokensPage /></RequireAuth>} />
        <Route path="/browse" element={<RequireAuth><BrowsePage /></RequireAuth>} />
        <Route path="/browse/new" element={<RequireAuth><NoteEditorPage mode="create" /></RequireAuth>} />
        <Route path="/browse/:stem" element={<RequireAuth><ReaderPage /></RequireAuth>} />
        <Route path="/browse/:stem/edit" element={<RequireAuth><NoteEditorPage mode="edit" /></RequireAuth>} />
        <Route path="/admin" element={<AdminPlaceholderPage />} />
        <Route path="/admin/tokens" element={<AdminTokensPage />} />
      </Routes>
    </AppShell>
  )
}