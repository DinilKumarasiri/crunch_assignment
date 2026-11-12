import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes } from 'react-router'
import { HomeRedirect, RequireAuth } from './auth/RequireAuth'
import Layout from './components/Layout'
import LoginPage from './pages/LoginPage'

// Code splitting: each page is downloaded only when first visited.
// Employees never download the manager screens at all.
const PolicyPage = lazy(() => import('./pages/PolicyPage'))
const MyBreaksPage = lazy(() => import('./pages/MyBreaksPage'))
const ApprovalQueuePage = lazy(() => import('./pages/ApprovalQueuePage'))
const RegisterPage = lazy(() => import('./pages/RegisterPage'))

export default function App() {
  return (
    <Suspense fallback={<p className="muted">Loading…</p>}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          element={
            <RequireAuth>
              <Layout />
            </RequireAuth>
          }
        >
          <Route index element={<HomeRedirect />} />
          <Route path="my-breaks" element={<RequireAuth role="EMPLOYEE"><MyBreaksPage /></RequireAuth>} />
          <Route path="policy" element={<RequireAuth role="MANAGER"><PolicyPage /></RequireAuth>} />
          <Route path="queue" element={<RequireAuth role="MANAGER"><ApprovalQueuePage /></RequireAuth>} />
          <Route path="register" element={<RequireAuth role="MANAGER"><RegisterPage /></RequireAuth>} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  )
}