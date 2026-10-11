import { Link, Navigate, Route, Routes } from 'react-router-dom'
import { useAuth } from './AuthContext'
import SessionHeader from './components/SessionHeader'
import AdminPlaceholderPage from './pages/AdminPlaceholderPage'
import AdminTokensPage from './pages/AdminTokensPage'
import LoginPage from './pages/LoginPage'
import TokensPage from './pages/TokensPage'

function Home() {
  return (
    <main style={{ padding: '2rem' }}>
      <h1>KB Portal</h1>
      <p>
        <Link to="/tokens">My Tokens</Link>
      </p>
      <p>
        <Link to="/admin/tokens">Token Admin</Link>
      </p>
      <p>
        <Link to="/admin">Admin</Link>
      </p>
    </main>
  )
}

function RequireAuth({ children }: { children: JSX.Element }) {
  const { isLoggedIn, isInitialized } = useAuth()
  if (!isInitialized) {
    return <main style={{ padding: '2rem' }}>Checking session…</main>
  }
  if (!isLoggedIn) {
    return <Navigate to="/login" replace />
  }
  return children
}

export default function App() {
  return (
    <>
      <SessionHeader />
      <Routes>
        <Route path="/" element={<RequireAuth><Home /></RequireAuth>} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/tokens" element={<RequireAuth><TokensPage /></RequireAuth>} />
        <Route path="/admin" element={<AdminPlaceholderPage />} />
        <Route path="/admin/tokens" element={<AdminTokensPage />} />
      </Routes>
    </>
  )
}
