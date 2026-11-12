import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './client'

// Query keys in one place: the same key always means the same cached data.
export const queryKeys = {
  policy: ['policy'],
  myBreaks: (params) => ['my-breaks', params],
  queue: (params) => ['queue', params],
}

export function usePolicy() {
  return useQuery({
    queryKey: queryKeys.policy,
    queryFn: ({ signal }) => api('/policy/', { signal }),
  })
}

export function useUpdatePolicy() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (values) => api('/policy/', { method: 'PUT', body: values }),
    // The PUT response IS the new policy: put it in the cache, no refetch needed.
    onSuccess: (saved) => queryClient.setQueryData(queryKeys.policy, saved),
  })
}

export function useMyBreaks(params) {
  return useQuery({
    queryKey: queryKeys.myBreaks(params),
    queryFn: ({ signal }) => api('/my/break-requests/', { params, signal }),
    placeholderData: keepPreviousData, // keep showing the old page while the new one loads
  })
}

export function useSubmitBreak() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body) => api('/my/break-requests/', { method: 'POST', body }),
    // Prefix match: invalidates EVERY cached history page and filter.
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['my-breaks'] }),
  })
}


export function useQueue(params) {
  return useQuery({
    queryKey: queryKeys.queue(params),
    queryFn: ({ signal }) => api('/break-requests/', { params, signal }),
    placeholderData: keepPreviousData,
  })
}

// A review changes the queue AND the register/analytics (Step 17), so refresh both.
function useRefreshAfterReview() {
  const queryClient = useQueryClient()
  return () => {
    queryClient.invalidateQueries({ queryKey: ['queue'] })
    queryClient.invalidateQueries({ queryKey: ['register'] })
  }
}

export function useReviewBreak() {
  const refresh = useRefreshAfterReview()
  return useMutation({
    mutationFn: ({ id, action, note }) =>
      api(`/break-requests/${id}/${action}/`, { method: 'POST', body: { note } }),
    onSettled: refresh, // success OR error: a 409 means our view was stale
  })
}

export function useBulkReview() {
  const refresh = useRefreshAfterReview()
  return useMutation({
    mutationFn: ({ ids, action, note }) =>
      api('/break-requests/bulk-review/', { method: 'POST', body: { ids, action, note } }),
    onSettled: refresh,
  })
}