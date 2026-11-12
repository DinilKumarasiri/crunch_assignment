import { keepPreviousData, useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './client'

// Query keys in one place: the same key always means the same cached data.
export const queryKeys = {
  policy: ['policy'],
  myBreaks: (params) => ['my-breaks', params],
  queue: (params) => ['queue', params],
  registerList: (params) => ['register', 'list', params],
  registerSummary: (params) => ['register', 'summary', params],
  dailyStats: (params) => ['register', 'daily', params],
  onBreak: (at) => ['register', 'on-break', at],
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


export function useRegisterList(params) {
  return useInfiniteQuery({
    queryKey: queryKeys.registerList(params),
    queryFn: ({ pageParam, signal }) =>
      api('/register/', { params: { ...params, cursor: pageParam, page_size: 25 }, signal }),
    initialPageParam: '',
    // The API gives a full `next` URL; we only need its opaque cursor value.
    getNextPageParam: (lastPage) =>
      lastPage.next ? new URL(lastPage.next).searchParams.get('cursor') : undefined,
    placeholderData: keepPreviousData,
  })
}

export function useRegisterSummary(params) {
  return useQuery({
    queryKey: queryKeys.registerSummary(params),
    queryFn: ({ signal }) => api('/register/summary/', { params, signal }),
    placeholderData: keepPreviousData,
  })
}

export function useDailyStats(params) {
  return useQuery({
    queryKey: queryKeys.dailyStats(params),
    queryFn: ({ signal }) => api('/register/daily-stats/', { params, signal }),
    placeholderData: keepPreviousData,
  })
}

export function useOnBreak(at) {
  return useQuery({
    queryKey: queryKeys.onBreak(at),
    queryFn: ({ signal }) => api('/register/on-break/', { params: { at }, signal }),
    enabled: Boolean(at), // don't call the API until a time is chosen
  })
}