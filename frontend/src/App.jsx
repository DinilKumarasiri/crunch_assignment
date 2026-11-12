import { useEffect, useState } from 'react'

function App() {
  const [status, setStatus] = useState('checking...')

  useEffect(() => {
    // Relative URL → goes to localhost:5173 → Vite proxies it to Django
    fetch('/api/health/')
      .then((res) => res.json())
      .then((data) => setStatus(data.status))
      .catch(() => setStatus('backend unreachable'))
  }, []) // [] = run once, when the component first appears

  return (
    <main style={{ fontFamily: 'sans-serif', padding: 24 }}>
      <h1>Break Management</h1>
      <p>
        Backend status: <strong>{status}</strong>
      </p>
    </main>
  )
}

export default App