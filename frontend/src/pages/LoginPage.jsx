import { useState } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router'
import { useAuth } from '../auth/AuthContext'

export default function LoginPage() {
  const { login, status } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  if (status === 'authenticated') return <Navigate to="/" replace />

  async function handleSubmit(event) {
    event.preventDefault() // stop the browser's default full-page form submit
    setSubmitting(true)
    setError(null)
    try {
      await login(username, password)
      navigate(location.state?.from?.pathname || '/', { replace: true })
    } catch (err) {
      setError(err.status === 401 ? 'Invalid username or password.' : err.message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="login">
      <form className="card" onSubmit={handleSubmit}>
        <h1>Break Management</h1>
        <label>
          Username
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoFocus required />
        </label>
        <label>
          Password
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </label>
        {error && <p className="error">{error}</p>}
        <button type="submit" disabled={submitting}>
          {submitting ? 'Signing in…' : 'Sign in'}
        </button>
        {import.meta.env.DEV && (
          <p className="muted small">
            Demo: acme_manager / acme_emp1 · password: password123
          </p>
        )}
      </form>
    </div>
  )
}