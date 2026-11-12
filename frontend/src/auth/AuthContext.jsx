import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import { tokenStore } from '../api/tokenStore'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const queryClient = useQueryClient()
  const [user, setUser] = useState(null)
  const [status, setStatus] = useState('loading') // 'loading' | 'authenticated' | 'anonymous'

  // On page load: if a refresh token exists, restore the session.
  // /auth/me/ gets a 401 (no access token in memory yet) → client refreshes → retries.
  useEffect(() => {
    if (!tokenStore.getRefresh()) {
      setStatus('anonymous')
      return
    }
    api('/auth/me/')
      .then((me) => {
        setUser(me)
        setStatus('authenticated')
      })
      .catch(() => tokenStore.clear())
  }, [])

  // Whenever tokens are cleared (logout or failed refresh): reset everything.
  useEffect(
    () =>
      tokenStore.onCleared(() => {
        setUser(null)
        setStatus('anonymous')
        queryClient.clear() // never show one user's cached data to the next user
      }),
    [queryClient],
  )

  const login = useCallback(async (username, password) => {
    const data = await api('/auth/login/', {
      method: 'POST',
      body: { username, password },
      auth: false,
    })
    tokenStore.set(data.access, data.refresh)
    setUser(data.user)
    setStatus('authenticated')
    return data.user
  }, [])

  const logout = useCallback(() => tokenStore.clear(), [])

  // useMemo: consumers only re-render when these values actually change.
  const value = useMemo(() => ({ user, status, login, logout }), [user, status, login, logout])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside <AuthProvider>')
  return context
}