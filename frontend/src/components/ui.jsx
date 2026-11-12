export function StatusBadge({ status }) {
  return <span className={`badge ${status}`}>{status.charAt(0) + status.slice(1).toLowerCase()}</span>
}

// Accepts a string or DRF's ["message", ...] array.
export function FieldError({ message }) {
  if (!message) return null
  return <span className="error">{Array.isArray(message) ? message.join(' ') : message}</span>
}