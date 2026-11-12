import { useEffect, useRef, useState } from 'react'

// Debounce in the event handler: one onSearch call after typing pauses.
export default function SearchBox({ initial, onSearch, label = 'Search employee', delay = 300 }) {
  const [text, setText] = useState(initial)
  const timer = useRef(null)

  useEffect(() => () => clearTimeout(timer.current), [])

  function handleChange(event) {
    const value = event.target.value
    setText(value)
    clearTimeout(timer.current)
    timer.current = setTimeout(() => onSearch(value.trim()), delay)
  }

  return (
    <label>{label}
      <input type="search" value={text} onChange={handleChange} placeholder="Name or username" />
    </label>
  )
}