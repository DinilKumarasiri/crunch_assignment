import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api, ApiError } from './client'
import { tokenStore } from './tokenStore'

const reply = (status, body) =>
  Promise.resolve(new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }))

describe('ApiError', () => {
  it('uses DRF "detail" as the message', () => {
    expect(new ApiError(409, { detail: 'Overlaps' }).message).toBe('Overlaps')
  })

  it('exposes DRF field errors for forms', () => {
    const error = new ApiError(400, { duration_minutes: ['Too long'] })
    expect(error.message).toBe('Too long')
    expect(error.fieldErrors.duration_minutes).toEqual(['Too long'])
  })
})

describe('api() token refresh', () => {
  beforeEach(() => tokenStore.set('expired-token', 'refresh-token'))
  afterEach(() => {
    vi.unstubAllGlobals()
    sessionStorage.clear()
  })

  it('refreshes ONCE for concurrent 401s and retries every request', async () => {
    const fetchMock = vi.fn((url, options) => {
      if (url.endsWith('/auth/refresh/')) return reply(200, { access: 'fresh-token' })
      return options.headers.Authorization === 'Bearer fresh-token'
        ? reply(200, { ok: true })
        : reply(401, { detail: 'Token expired' })
    })
    vi.stubGlobal('fetch', fetchMock)

    const results = await Promise.all([api('/a/'), api('/b/'), api('/c/')])

    expect(results).toEqual([{ ok: true }, { ok: true }, { ok: true }])
    const refreshCalls = fetchMock.mock.calls.filter(([url]) => url.endsWith('/auth/refresh/'))
    expect(refreshCalls).toHaveLength(1) // single-flight
  })

  it('logs out when the refresh token is rejected', async () => {
    vi.stubGlobal('fetch', vi.fn(() => reply(401, { detail: 'Invalid' })))
    await expect(api('/a/')).rejects.toMatchObject({ status: 401 })
    expect(tokenStore.getRefresh()).toBeNull()
  })
})

