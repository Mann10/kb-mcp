import { Link, Route, Routes } from 'react-router-dom'
import SessionHeader from './components/SessionHeader'
import AdminPlaceholderPage from './pages/AdminPlaceholderPage'
import LoginPage from './pages/LoginPage'

function Home() {
  return (
    <main style={{ padding: '2rem' }}>
      <h1>KB Portal</h1>
      <p>
        <Link to="/admin">Admin</Link>
      </p>
    </main>
  )
}

export default function App() {
  return (
    <>
      <SessionHeader />
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/admin" element={<AdminPlaceholderPage />} />
      </Routes>
    </>
  )
}
