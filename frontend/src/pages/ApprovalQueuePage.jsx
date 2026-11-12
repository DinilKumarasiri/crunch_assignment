import { memo, useCallback, useEffect, useRef, useState } from 'react'
import { useBulkReview, useQueue, useReviewBreak } from '../api/hooks'
import Pagination from '../components/Pagination'
import { StatusBadge } from '../components/ui'
import { useUrlParams } from '../hooks/useUrlParams'
import { formatDate, formatMinutes, formatTime } from '../utils/format'

const DEFAULTS = {
  status: 'PENDING', search: '', date_from: '', date_to: '',
  ordering: 'start_at', page: '1', page_size: '20',
}
const STATUS_TABS = [['PENDING', 'Pending'], ['APPROVED', 'Approved'], ['REJECTED', 'Rejected'], ['ALL', 'All']]
const SKIP_REASONS = {
  capacity_reached: 'over the on-break limit',
  already_approved: 'already approved',
  already_rejected: 'already rejected',
  not_found: 'not found',
}

function summarizeBulk(action, result) {
  const parts = [`${result.processed.length} ${action === 'approve' ? 'approved' : 'rejected'}`]
  const counts = {}
  result.skipped.forEach(({ reason }) => { counts[reason] = (counts[reason] ?? 0) + 1 })
  Object.entries(counts).forEach(([reason, n]) => parts.push(`${n} skipped (${SKIP_REASONS[reason] ?? reason})`))
  return parts.join(' · ')
}

export default function ApprovalQueuePage() {
  const [params, setParams] = useUrlParams(DEFAULTS)
  const [selected, setSelected] = useState(() => new Set())
  const [note, setNote] = useState('')
  const noteRef = useRef('') // read at click time, so typing a note doesn't re-render every row
  const [notice, setNotice] = useState(null)

  const page = Number(params.page)
  const pageSize = Number(params.page_size)
  const { data, isLoading, isFetching, error } = useQueue({
    ...params,
    status: params.status === 'ALL' ? '' : params.status,
  })
  const review = useReviewBreak()
  const bulk = useBulkReview()
  const { mutate: reviewMutate } = review // `mutate` is a stable function

  // Any change of filters / sort / page clears the selection.
  const changeParams = useCallback((changes) => {
    setSelected(new Set())
    setParams(changes)
  }, [setParams])

  // Stable callbacks (same function every render) so memoised rows don't re-render.
  const toggle = useCallback((id) => {
    setSelected((previous) => {
      const next = new Set(previous)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

  const handleReview = useCallback((id, action) => {
    setNotice(null)
    reviewMutate({ id, action, note: noteRef.current }, {
      onSuccess: () => {
        setNotice({ type: 'success', text: `Request ${action === 'approve' ? 'approved' : 'rejected'}.` })
        setSelected((previous) => {
          const next = new Set(previous)
          next.delete(id)
          return next
        })
      },
      onError: (err) => setNotice({ type: 'warning', text: err.message }),
    })
  }, [reviewMutate])

  const results = data?.results ?? []
  const pendingIds = results.filter((r) => r.status === 'PENDING').map((r) => r.id)
  const selectedIds = pendingIds.filter((id) => selected.has(id)) // only what's visible and still pending
  const allSelected = pendingIds.length > 0 && selectedIds.length === pendingIds.length
  const busyId = review.isPending ? review.variables?.id : null
  const pageCount = data ? Math.ceil(data.count / pageSize) : 0

  function handleBulk(action) {
    setNotice(null)
    bulk.mutate({ ids: selectedIds, action, note }, {
      onSuccess: (result) => {
        setSelected(new Set())
        setNotice({ type: result.skipped.length ? 'warning' : 'success', text: summarizeBulk(action, result) })
      },
      onError: (err) => setNotice({ type: 'warning', text: err.message }),
    })
  }

  return (
    <div className="stack">
      <div className="section-head">
        <h1>Approval queue</h1>
        <span className="muted small">
          {data && `${data.count.toLocaleString()} requests`} {isFetching && !isLoading && '· updating…'}
        </span>
      </div>

      <div className="tabs">
        {STATUS_TABS.map(([value, label]) => (
          <button key={value} type="button" className={params.status === value ? 'active' : ''}
                  onClick={() => changeParams({ status: value, page: '' })}>
            {label}
          </button>
        ))}
      </div>

      <div className="toolbar">
        <SearchBox initial={params.search} onSearch={(value) => changeParams({ search: value, page: '' })} />
        <label>From
          <input type="date" value={params.date_from}
                 onChange={(e) => changeParams({ date_from: e.target.value, page: '' })} />
        </label>
        <label>To
          <input type="date" value={params.date_to}
                 onChange={(e) => changeParams({ date_to: e.target.value, page: '' })} />
        </label>
        <label>Rows
          <select value={params.page_size} onChange={(e) => changeParams({ page_size: e.target.value, page: '' })}>
            {['20', '50', '100'].map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </label>
        <label>Note (optional)
          <input value={note} placeholder="Sent with approve / reject"
                 onChange={(e) => { setNote(e.target.value); noteRef.current = e.target.value }} />
        </label>
      </div>

      {notice && <div className={`banner ${notice.type}`}>{notice.text}</div>}

      {selectedIds.length > 0 && (
        <div className="bulk-bar">
          <strong>{selectedIds.length} selected</strong>
          <button disabled={bulk.isPending} onClick={() => handleBulk('approve')}>Approve selected</button>
          <button className="danger" disabled={bulk.isPending} onClick={() => handleBulk('reject')}>Reject selected</button>
          <button className="secondary" onClick={() => setSelected(new Set())}>Clear</button>
        </div>
      )}

      {error && <p className="error">{error.message}</p>}
      {isLoading ? (
        <p className="muted">Loading…</p>
      ) : results.length === 0 ? (
        <p className="muted">Nothing matches these filters.</p>
      ) : (
        <table className={isFetching ? 'is-fetching' : ''}>
          <thead>
            <tr>
              <th className="col-check">
                <input type="checkbox" aria-label="Select all pending on this page"
                       checked={allSelected} disabled={pendingIds.length === 0}
                       onChange={() => setSelected(allSelected ? new Set() : new Set(pendingIds))} />
              </th>
              <SortHeader field="employee__last_name" label="Employee" ordering={params.ordering} onSort={changeParams} />
              <SortHeader field="start_at" label="Date & time" ordering={params.ordering} onSort={changeParams} />
              <SortHeader field="duration_minutes" label="Duration" ordering={params.ordering} onSort={changeParams} />
              <th>Status</th>
              <SortHeader field="created_at" label="Submitted" ordering={params.ordering} onSort={changeParams} />
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {results.map((item) => (
              <QueueRow key={item.id} item={item} selected={selected.has(item.id)}
                        busy={busyId === item.id} onToggle={toggle} onReview={handleReview} />
            ))}
          </tbody>
        </table>
      )}

      <Pagination page={page} pageCount={pageCount} isFetching={isFetching}
                  onPageChange={(p) => changeParams({ page: String(p) })} />
    </div>
  )
}

// Debounce in the event handler: one URL update (one request) after typing pauses.
function SearchBox({ initial, onSearch }) {
  const [text, setText] = useState(initial)
  const timer = useRef(null)

  useEffect(() => () => clearTimeout(timer.current), []) // cancel a pending timer on unmount

  function handleChange(event) {
    const value = event.target.value
    setText(value)
    clearTimeout(timer.current)
    timer.current = setTimeout(() => onSearch(value.trim()), 300)
  }

  return (
    <label>Search employee
      <input type="search" value={text} onChange={handleChange} placeholder="Name or username" />
    </label>
  )
}

function SortHeader({ field, label, ordering, onSort }) {
  const ascending = ordering === field
  const descending = ordering === `-${field}`
  return (
    <th aria-sort={ascending ? 'ascending' : descending ? 'descending' : 'none'}>
      <button type="button" className="sort"
              onClick={() => onSort({ ordering: ascending ? `-${field}` : field, page: '' })}>
        {label} {ascending ? '▲' : descending ? '▼' : ''}
      </button>
    </th>
  )
}

// memo: re-renders only when THIS row's props change.
const QueueRow = memo(function QueueRow({ item, selected, busy, onToggle, onReview }) {
  const pending = item.status === 'PENDING'
  return (
    <tr className={selected ? 'selected' : ''}>
      <td>
        <input type="checkbox" aria-label={`Select ${item.employee_name}`}
               disabled={!pending} checked={selected} onChange={() => onToggle(item.id)} />
      </td>
      <td>{item.employee_name}</td>
      <td>
        {formatDate(item.break_date)}<br />
        <span className="muted small">{formatTime(item.start_at)}–{formatTime(item.end_at)}</span>
      </td>
      <td>{formatMinutes(item.duration_minutes)}</td>
      <td><StatusBadge status={item.status} /></td>
      <td className="muted small">{formatDate(item.created_at)}</td>
      <td>
        {pending ? (
          <div className="row-actions">
            <button disabled={busy} onClick={() => onReview(item.id, 'approve')}>Approve</button>
            <button className="danger" disabled={busy} onClick={() => onReview(item.id, 'reject')}>Reject</button>
          </div>
        ) : (
          <span className="muted small">{item.review_note || '—'}</span>
        )}
      </td>
    </tr>
  )
})