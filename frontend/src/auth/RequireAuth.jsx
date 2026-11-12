import { Navigate, useLocation } from 'react-router'
import { useAuth } from './AuthContext'

// UX guard only. Real protection is the backend returning 401/403/404.
export function RequireAuth({ role, children }) {
  const { user, status } = useAuth()
  const location = useLocation()

  if (status === 'loading') return <p className="muted">Loading…</p>
  if (status !== 'authenticated') {
    // Remember where the user was going, so login can send them back there.
    return <Navigate to="/login" replace state={{ from: location }} />
  }
  if (role && user.role !== role) return <Navigate to="/" replace />
  return children
}

export function HomeRedirect() {
  const { user } = useAuth()
  return <Navigate to={user.role === 'MANAGER' ? '/queue' : '/my-breaks'} replace />
}