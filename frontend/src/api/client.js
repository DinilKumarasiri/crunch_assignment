import { tokenStore } from './tokenStore'

const BASE = '/api' // relative: the Vite proxy forwards it to Django (Step 3)

export class ApiError extends Error {
  constructor(status, data) {
    super(ApiError.messageFrom(data) || `Request failed (${status})`)
    this.status = status
    this.data = data
    // DRF validation errors look like {"field": ["message"]}: handy for forms.
    this.fieldErrors = data && typeof data === 'object' && !data.detail ? data : {}
  }

  static messageFrom(data) {
    if (!data) return null
    if (typeof data.detail === 'string') return data.detail
    const first = Object.values(data)[0]
    return Array.isArray(first) ? first[0] : typeof first === 'string' ? first : null
  }
}

function buildUrl(path, params) {
  const url = new URL(BASE + path, window.location.origin)
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') url.searchParams.set(key, value)
  })
  return url.pathname + url.search
}

// Single-flight refresh: concurrent 401s share ONE refresh request.
let refreshPromise = null

function refreshAccessToken() {
  if (!refreshPromise) {
    refreshPromise = (async () => {
      const refresh = tokenStore.getRefresh()
      const res = await fetch(`${BASE}/auth/refresh/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh }),
      })
      if (!res.ok) {
        tokenStore.clear() // session is over → AuthContext logs the user out
        throw new ApiError(401, { detail: 'Your session has expired. Please log in again.' })
      }
      const data = await res.json()
      tokenStore.setAccess(data.access)
      return data.access
    })().finally(() => {
      refreshPromise = null
    })
  }
  return refreshPromise
}

/**
 * api('/break-requests/', { params: { status: 'PENDING' } })
 * api('/policy/', { method: 'PUT', body: {...} })
 */
export async function api(path, { method = 'GET', body, params, signal, auth = true, retry = true } = {}) {
  const headers = { Accept: 'application/json' }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (auth && tokenStore.getAccess()) headers.Authorization = `Bearer ${tokenStore.getAccess()}`

  const res = await fetch(buildUrl(path, params), {
    method,
    headers,
    signal, // lets React Query cancel requests that are no longer needed
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })

  // Expired or missing access token: refresh once, then retry the original request.
  if (res.status === 401 && auth && retry && tokenStore.getRefresh()) {
    await refreshAccessToken()
    return api(path, { method, body, params, signal, auth, retry: false })
  }

  const data = res.status === 204 ? null : await res.json().catch(() => null)
  if (!res.ok) throw new ApiError(res.status, data)
  return data
}
