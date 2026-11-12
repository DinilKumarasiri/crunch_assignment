import { NavLink, Outlet } from 'react-router'
import { useAuth } from '../auth/AuthContext'

const LINKS = {
  MANAGER: [
    { to: '/queue', label: 'Approval queue' },
    { to: '/register', label: 'Break register' },
    { to: '/policy', label: 'Break policy' },
  ],
  EMPLOYEE: [{ to: '/my-breaks', label: 'My breaks' }],
}

export default function Layout() {
  const { user, logout } = useAuth()

  return (
    <div className="app">
      <header className="header">
        <strong>Break Management</strong>
        <nav>
          {LINKS[user.role].map((link) => (
            <NavLink key={link.to} to={link.to}>
              {link.label}
            </NavLink>
          ))}
        </nav>
        <div className="user">
          <span>
            {user.first_name || user.username} · {user.organisation_name}
          </span>
          <button className="secondary" onClick={logout}>
            Log out
          </button>
        </div>
      </header>
      <main className="content">
        <Outlet /> {/* the current page renders here */}
      </main>
    </div>
  )
}

