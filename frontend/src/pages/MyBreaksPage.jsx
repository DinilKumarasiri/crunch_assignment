import { useState } from 'react'
import { useSearchParams } from 'react-router'
import { useMyBreaks, usePolicy, useSubmitBreak } from '../api/hooks'
import Pagination from '../components/Pagination'
import { FieldError, StatusBadge } from '../components/ui'
import { formatDate, formatMinutes, formatTime, isoDate } from '../utils/format'

const newRequestId = () => crypto.randomUUID()

export default function MyBreaksPage() {
  const { data: policy } = usePolicy()
  return (
    <div className="stack">
      <h1>My breaks</h1>
      <div className="two-col">
        <RequestBreakForm policy={policy} />
        <PolicySummary policy={policy} />
      </div>
      <BreakHistory />
    </div>
  )
}

// ----------------------------------------------------------------------------- form
function RequestBreakForm({ policy }) {
  const [values, setValues] = useState({ date: isoDate(1), start_time: '10:00', duration_minutes: '15' })
  const [requestId, setRequestId] = useState(newRequestId) // lazy initial value: runs once
  const submit = useSubmitBreak()
  const fieldErrors = submit.error?.fieldErrors ?? {}

  function handleChange(name, value) {
    setValues((current) => ({ ...current, [name]: value }))
    setRequestId(newRequestId()) // different values = a different request = a new key
    if (submit.error || submit.isSuccess) submit.reset()
  }

  function handleSubmit(event) {
    event.preventDefault()
    submit.mutate(
      { ...values, duration_minutes: Number(values.duration_minutes), client_request_id: requestId },
      { onSuccess: () => setRequestId(newRequestId()) }, // next request gets a fresh key
    )
  }

  const generalError =
    submit.error && (fieldErrors.non_field_errors || (!Object.keys(fieldErrors).length && submit.error.message))

  return (
    <form className="card stack" onSubmit={handleSubmit} noValidate>
      <h2>Request a break</h2>
      <div className="inline-fields">
        <label>
          Date
          <input type="date" min={isoDate(0)} value={values.date}
                 onChange={(e) => handleChange('date', e.target.value)} />
          <FieldError message={fieldErrors.date} />
        </label>
        <label>
          Start time
          <input type="time" step={300} value={values.start_time}
                 onChange={(e) => handleChange('start_time', e.target.value)} />
          <FieldError message={fieldErrors.start_time} />
        </label>
        <label>
          Duration (minutes)
          <input type="number" min={policy?.min_duration_minutes} max={policy?.max_duration_minutes}
                 value={values.duration_minutes}
                 onChange={(e) => handleChange('duration_minutes', e.target.value)} />
          <FieldError message={fieldErrors.duration_minutes} />
        </label>
      </div>

      {generalError && <FieldError message={generalError} />}
      {submit.isSuccess && (
        <div className="banner success">
          {submit.data.status === 'APPROVED'
            ? 'Break approved automatically.'
            : 'Request submitted and waiting for approval.'}
        </div>
      )}

      <div className="actions">
        <button type="submit" disabled={submit.isPending}>
          {submit.isPending ? 'Submitting…' : 'Submit request'}
        </button>
      </div>
    </form>
  )
}

function PolicySummary({ policy }) {
  if (!policy) return <div className="card muted">Loading rules…</div>
  return (
    <div className="card stack">
      <h2>Your organisation's rules</h2>
      <ul className="rules">
        <li>Each break: {policy.min_duration_minutes}–{policy.max_duration_minutes} minutes</li>
        <li>Up to {formatMinutes(policy.max_daily_minutes)} and {policy.max_requests_per_day} breaks per day</li>
        <li>Request at least {formatMinutes(policy.min_advance_notice_minutes)} in advance</li>
        <li>{policy.requires_approval ? 'A manager must approve each break' : 'Breaks are approved automatically'}</li>
      </ul>
    </div>
  )
}

// ----------------------------------------------------------------------------- history
const STATUS_TABS = [
  ['', 'All'],
  ['PENDING', 'Pending'],
  ['APPROVED', 'Approved'],
  ['REJECTED', 'Rejected'],
]
const PAGE_SIZE = 10

function BreakHistory() {
  const [searchParams, setSearchParams] = useSearchParams()
  const status = searchParams.get('status') ?? ''
  const page = Number(searchParams.get('page') ?? 1)

  const { data, isLoading, isFetching, error } = useMyBreaks({ status, page, page_size: PAGE_SIZE })

  function updateParams(changes) {
    const next = new URLSearchParams(searchParams)
    Object.entries(changes).forEach(([key, value]) => (value ? next.set(key, value) : next.delete(key)))
    setSearchParams(next)
  }

  const pageCount = data ? Math.ceil(data.count / PAGE_SIZE) : 0

  return (
    <section className="stack">
      <div className="section-head">
        <h2>History</h2>
        {isFetching && !isLoading && <span className="muted small">Updating…</span>}
      </div>

      <div className="tabs">
        {STATUS_TABS.map(([value, label]) => (
          <button key={label} type="button" className={status === value ? 'active' : ''}
                  onClick={() => updateParams({ status: value, page: '' })}>  {/* filter change → page 1 */}
            {label}
          </button>
        ))}
      </div>

      {error && <p className="error">{error.message}</p>}
      {isLoading ? (
        <p className="muted">Loading…</p>
      ) : data.results.length === 0 ? (
        <p className="muted">No break requests here yet.</p>
      ) : (
        <table className={isFetching ? 'is-fetching' : ''}>
          <thead>
            <tr><th>Date</th><th>Time</th><th>Duration</th><th>Status</th><th>Manager note</th></tr>
          </thead>
          <tbody>
            {data.results.map((item) => (
              <tr key={item.id}>
                <td>{formatDate(item.break_date)}</td>
                <td>{formatTime(item.start_at)}–{formatTime(item.end_at)}</td>
                <td>{formatMinutes(item.duration_minutes)}</td>
                <td><StatusBadge status={item.status} /></td>
                <td className="muted">{item.review_note || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <Pagination page={page} pageCount={pageCount} isFetching={isFetching}
                  onPageChange={(p) => updateParams({ page: p > 1 ? String(p) : '' })} />
    </section>
  )
}