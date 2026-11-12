import { useCallback } from 'react'
import { useSearchParams } from 'react-router'

/**
 * URL query string as state, with defaults.
 *   const [params, setParams] = useUrlParams({ status: 'PENDING', page: '1' })
 *   setParams({ status: 'APPROVED', page: '' })   // '' or a default value removes the key
 * `defaults` must be a constant defined outside the component, so it stays the same object.
 */
export function useUrlParams(defaults) {
  const [searchParams, setSearchParams] = useSearchParams()

  const params = { ...defaults }
  for (const key of Object.keys(defaults)) {
    const value = searchParams.get(key)
    if (value !== null) params[key] = value
  }

  const setParams = useCallback(
    (changes) =>
      // Functional update: always starts from the LATEST URL, never a stale copy.
      setSearchParams((previous) => {
        const next = new URLSearchParams(previous)
        Object.entries(changes).forEach(([key, value]) => {
          if (value === '' || value == null || value === defaults[key]) next.delete(key)
          else next.set(key, String(value))
        })
        return next
      }),
    [setSearchParams, defaults],
  )

  return [params, setParams]
}