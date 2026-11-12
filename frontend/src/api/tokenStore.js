// Access token: memory only (gone on reload, never persisted).
// Refresh token: sessionStorage (survives reload, cleared when the tab closes).
const REFRESH_KEY = 'bm.refresh'

let accessToken = null
const clearListeners = new Set()

export const tokenStore = {
  getAccess: () => accessToken,
  getRefresh: () => sessionStorage.getItem(REFRESH_KEY),

  set(access, refresh) {
    accessToken = access
    if (refresh) sessionStorage.setItem(REFRESH_KEY, refresh)
  },

  setAccess(access) {
    accessToken = access
  },

  clear() {
    accessToken = null
    sessionStorage.removeItem(REFRESH_KEY)
    clearListeners.forEach((listener) => listener())
  },

  // Lets the AuthContext react when tokens are cleared (logout or a failed refresh).
  onCleared(listener) {
    clearListeners.add(listener)
    return () => clearListeners.delete(listener)
  },
}