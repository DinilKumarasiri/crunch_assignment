// The backend interprets all times in Asia/Colombo (Django TIME_ZONE, Step 4).
// The UI formats times in the same zone, whatever zone the browser is in.
export const APP_TIME_ZONE = 'Asia/Colombo'

// Creating Intl formatters is relatively expensive, so create them ONCE and reuse them.
const dateFormatter = new Intl.DateTimeFormat('en-GB', {
  timeZone: APP_TIME_ZONE, weekday: 'short', day: '2-digit', month: 'short', year: 'numeric',
})
const timeFormatter = new Intl.DateTimeFormat('en-GB', {
  timeZone: APP_TIME_ZONE, hour: '2-digit', minute: '2-digit',
})
const isoDateFormatter = new Intl.DateTimeFormat('en-CA', { timeZone: APP_TIME_ZONE }) // en-CA → YYYY-MM-DD

export function formatDate(value) {
  // "2026-11-20" (a date only) → use noon UTC so the day never shifts across time zones.
  const date = value.length === 10 ? new Date(`${value}T12:00:00Z`) : new Date(value)
  return dateFormatter.format(date)
}

export const formatTime = (value) => timeFormatter.format(new Date(value))

export const isoDate = (offsetDays = 0) =>
  isoDateFormatter.format(new Date(Date.now() + offsetDays * 86_400_000))

export function formatMinutes(minutes) {
  if (minutes < 60) return `${minutes} min`
  const rest = minutes % 60
  return rest ? `${Math.floor(minutes / 60)} h ${rest} min` : `${minutes / 60} h`
}

const shortDateFormatter = new Intl.DateTimeFormat('en-GB', {
  timeZone: APP_TIME_ZONE, day: 'numeric', month: 'short',
})

export const formatShortDate = (isoDay) => shortDateFormatter.format(new Date(`${isoDay}T12:00:00Z`))
export const formatDateTime = (value) => `${formatDate(value)} ${formatTime(value)}`
// Value for <input type="datetime-local"> meaning "now" in the app's time zone.
export const nowLocalInput = () => `${isoDate(0)}T${formatTime(new Date())}`