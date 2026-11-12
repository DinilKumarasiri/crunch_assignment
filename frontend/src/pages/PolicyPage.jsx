import { useState } from 'react'
import { usePolicy, useUpdatePolicy } from '../api/hooks'
import { FieldError } from '../components/ui'
import { formatDate, formatTime } from '../utils/format'

const NUMBER_FIELDS = [
  { name: 'min_duration_minutes', label: 'Minimum break duration (minutes)', min: 1, max: 480 },
  { name: 'max_duration_minutes', label: 'Maximum break duration (minutes)', min: 1, max: 480 },
  { name: 'max_daily_minutes', label: 'Daily break allowance (minutes)', min: 1, max: 1440 },
  { name: 'max_requests_per_day', label: 'Maximum requests per day', min: 1, max: 50 },
  { name: 'min_advance_notice_minutes', label: 'Minimum advance notice (minutes)', min: 0, max: 10080 },
  { name: 'max_concurrent_breaks', label: 'Maximum employees on break at once', min: 1, max: 10000 },
]

// Client-side copy of the server rules (Step 7): instant feedback only.
// The server re-validates everything.
function validate(values) {
  const errors = {}
  for (const field of NUMBER_FIELDS) {
    const raw = values[field.name]
    const n = Number(raw)
    if (raw === '' || !Number.isInteger(n)) errors[field.name] = 'Enter a whole number.'
    else if (n < field.min || n > field.max) errors[field.name] = `Must be between ${field.min} and ${field.max}.`
  }
  const num = (name) => Number(values[name])
  if (!errors.min_duration_minutes && !errors.max_duration_minutes &&
      num('min_duration_minutes') > num('max_duration_minutes')) {
    errors.min_duration_minutes = 'Must not exceed the maximum duration.'
  }
  if (!errors.max_duration_minutes && !errors.max_daily_minutes &&
      num('max_duration_minutes') > num('max_daily_minutes')) {
    errors.max_duration_minutes = 'A single break cannot exceed the daily allowance.'
  }
  return errors
}

function toFormValues(policy) {
  const values = { requires_approval: policy.requires_approval }
  NUMBER_FIELDS.forEach((field) => {
    values[field.name] = String(policy[field.name])
  })
  return values
}

export default function PolicyPage() {
  const { data: policy, isLoading, error, refetch } = usePolicy()
  // The mutation lives HERE (not in the form) so its result survives the form remounting.
  const update = useUpdatePolicy()

  if (isLoading) return <p className="muted">Loading policy…</p>
  if (error) return <p className="error">{error.message}</p>

  return (
    <div className="stack">
      <h1>Break policy</h1>

      {update.isSuccess && <div className="banner success">Policy saved.</div>}

      {update.error?.status === 409 && (
        <div className="banner warning">
          <span>Someone else changed this policy while you were editing.</span>
          <button className="secondary" onClick={() => { update.reset(); refetch() }}>
            Load latest values
          </button>
        </div>
      )}

      {/* key = version: when the policy changes, the form remounts with fresh values */}
      <PolicyForm key={policy.version} policy={policy} update={update} />

      {policy.updated_at && (
        <p className="muted small">
          Last updated {formatDate(policy.updated_at)} {formatTime(policy.updated_at)}
          {policy.updated_by_name && ` by ${policy.updated_by_name}`} · version {policy.version}
        </p>
      )}
    </div>
  )
}

function PolicyForm({ policy, update }) {
  const initial = toFormValues(policy)
  const [values, setValues] = useState(initial)

  const clientErrors = validate(values)
  const serverErrors = update.error?.fieldErrors ?? {}
  const errors = { ...serverErrors, ...clientErrors }
  const hasClientErrors = Object.keys(clientErrors).length > 0
  const isDirty = JSON.stringify(values) !== JSON.stringify(initial)

  function handleChange(name, value) {
    setValues((current) => ({ ...current, [name]: value }))
    if (update.error || update.isSuccess) update.reset() // clear old messages once the user edits
  }

  function handleSubmit(event) {
    event.preventDefault()
    if (hasClientErrors) return
    const payload = { requires_approval: values.requires_approval, version: policy.version }
    NUMBER_FIELDS.forEach((field) => {
      payload[field.name] = Number(values[field.name])
    })
    update.mutate(payload)
  }

  const otherError =
    update.error && update.error.status !== 409 && Object.keys(serverErrors).length === 0

  return (
    <form className="card form-grid" onSubmit={handleSubmit} noValidate>
      {NUMBER_FIELDS.map((field) => (
        <label key={field.name}>
          {field.label}
          <input
            type="number"
            min={field.min}
            max={field.max}
            value={values[field.name]}
            onChange={(e) => handleChange(field.name, e.target.value)}
            aria-invalid={Boolean(errors[field.name])}
          />
          <FieldError message={errors[field.name]} />
        </label>
      ))}

      <div className="full">
        <label className="checkbox">
          <input
            type="checkbox"
            checked={values.requires_approval}
            onChange={(e) => handleChange('requires_approval', e.target.checked)}
          />
          Manager approval required
        </label>
        {!values.requires_approval && (
          <p className="muted small">
            Requests that fit all limits above (including the maximum on break at once) will be
            approved automatically.
          </p>
        )}
      </div>

      {otherError && <p className="error full">{update.error.message}</p>}

      <div className="actions full">
        <button type="submit" disabled={!isDirty || hasClientErrors || update.isPending}>
          {update.isPending ? 'Saving…' : 'Save policy'}
        </button>
        <button type="button" className="secondary" disabled={!isDirty} onClick={() => setValues(initial)}>
          Discard changes
        </button>
      </div>
    </form>
  )
}