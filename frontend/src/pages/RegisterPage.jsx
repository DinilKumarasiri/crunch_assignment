import { useState } from 'react'
import { useDailyStats, useOnBreak, useRegisterList, useRegisterSummary } from '../api/hooks'
import DailyStatsChart from '../components/DailyStatsChart'
import SearchBox from '../components/SearchBox'
import { Stat } from '../components/ui'
import { useUrlParams } from '../hooks/useUrlParams'
import {
  formatDate, formatDateTime, formatMinutes, formatTime, isoDate, nowLocalInput,
} from '../utils/format'

// Default view: the last 30 days (computed once when the module loads).
const DEFAULTS = { search: '', date_from: isoDate(-29), date_to: isoDate(0) }

export default function RegisterPage() {
  const [params, setParams] = useUrlParams(DEFAULTS)
  const filters = { search: params.search, date_from: params.date_from, date_to: params.date_to }
  const range = { date_from: params.date_from, date_to: params.date_to }

  return (
    <div className="stack">
      <h1>Break register</h1>

      <div className="toolbar">
        <SearchBox initial={params.search} onSearch={(value) => setParams({ search: value })} />
        <label>From
          <input type="date" value={params.date_from} onChange={(e) => setParams({ date_from: e.target.value })} />
        </label>
        <label>To
          <input type="date" value={params.date_to} onChange={(e) => setParams({ date_to: e.target.value })} />
        </label>
      </div>

      <SummaryTiles filters={filters} />
      <DailyStatsCard range={range} />
      <OnBreakPanel />
      <RegisterTable filters={filters} />
    </div>
  )
}

function SummaryTiles({ filters }) {
  const { data, error } = useRegisterSummary(filters)
  if (error) return <p className="error">{error.message}</p>
  return (
    <div className="stat-grid">
      <Stat label="Approved breaks" value={data?.total_breaks.toLocaleString()} />
      <Stat label="Total break time" value={data && `${data.total_hours.toLocaleString()} h`} />
      <Stat label="Unique employees" value={data?.unique_employees.toLocaleString()} />
    </div>
  )
}

function DailyStatsCard({ range }) {
  const { data, error, isFetching } = useDailyStats(range)
  const [showTable, setShowTable] = useState(false)

  return (
    <section className="card stack">
      <div className="section-head">
        <div>
          <h2>Approved breaks per day</h2>
          <p className="muted small">Covers all employees in the selected dates. Hover a day for details.</p>
        </div>
        <button className="secondary" onClick={() => setShowTable((v) => !v)}>
          {showTable ? 'Show chart' : 'Show table'}
        </button>
      </div>

      {error && <p className="error">{error.message}</p>}
      {data && !showTable && (
        <div className={isFetching ? 'is-fetching' : ''}>
          <DailyStatsChart days={data.days} />
        </div>
      )}
      {data && showTable && (
        <table>
          <thead>
            <tr><th>Date</th><th>Breaks</th><th>Total time</th><th>Employees</th></tr>
          </thead>
          <tbody>
            {data.days.map((d) => (
              <tr key={d.date}>
                <td>{formatDate(d.date)}</td>
                <td>{d.breaks.toLocaleString()}</td>
                <td>{formatMinutes(d.total_minutes)}</td>
                <td>{d.unique_employees.toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}

function OnBreakPanel() {
  const [at, setAt] = useState(nowLocalInput)
  const { data, isFetching, error } = useOnBreak(at)

  return (
    <section className="card stack">
      <div className="section-head">
        <h2>Who is on break?</h2>
        <label className="inline">At
          <input type="datetime-local" value={at} onChange={(e) => setAt(e.target.value)} />
        </label>
      </div>
      {error && <p className="error">{error.message}</p>}
      {data && (
        <div className={isFetching ? 'is-fetching' : ''}>
          <p><strong>{data.count}</strong> {data.count === 1 ? 'employee' : 'employees'} on break</p>
          {data.count > 0 && (
            <ul className="on-break-list">
              {data.breaks.map((b) => (
                <li key={b.id}>
                  {b.employee_name}{' '}
                  <span className="muted small">{formatTime(b.start_at)}–{formatTime(b.end_at)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  )
}

function RegisterTable({ filters }) {
  const { data, error, isLoading, isFetching, fetchNextPage, hasNextPage, isFetchingNextPage } =
    useRegisterList(filters)
  const summary = useRegisterSummary(filters) // same key as the tiles → served from cache, no extra request
  const rows = data?.pages.flatMap((page) => page.results) ?? []

  return (
    <section className="stack">
      <div className="section-head">
        <h2>Approved breaks</h2>
        {summary.data && (
          <span className="muted small">
            Showing {rows.length.toLocaleString()} of {summary.data.total_breaks.toLocaleString()}
          </span>
        )}
      </div>

      {error && <p className="error">{error.message}</p>}
      {isLoading ? (
        <p className="muted">Loading…</p>
      ) : rows.length === 0 ? (
        <p className="muted">No approved breaks match these filters.</p>
      ) : (
        <table className={isFetching && !isFetchingNextPage ? 'is-fetching' : ''}>
          <thead>
            <tr><th>Employee</th><th>Date</th><th>Time</th><th>Duration</th><th>Approved</th><th>Note</th></tr>
          </thead>
          <tbody>
            {rows.map((item) => (
              <tr key={item.id}>
                <td>{item.employee_name}</td>
                <td>{formatDate(item.break_date)}</td>
                <td>{formatTime(item.start_at)}–{formatTime(item.end_at)}</td>
                <td>{formatMinutes(item.duration_minutes)}</td>
                <td className="muted small">{item.reviewed_at ? formatDateTime(item.reviewed_at) : 'Auto'}</td>
                <td className="muted">{item.review_note || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {hasNextPage && (
        <div className="pagination">
          <button className="secondary" onClick={() => fetchNextPage()} disabled={isFetchingNextPage}>
            {isFetchingNextPage ? 'Loading…' : 'Load more'}
          </button>
        </div>
      )}
    </section>
  )
}