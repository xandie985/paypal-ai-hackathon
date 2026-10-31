import { useEffect, useState } from 'react'

export default function App() {
  const [health, setHealth] = useState<unknown>(null)
  useEffect(() => {
    fetch('/api/health').then((r) => r.json()).then(setHealth).catch(() => setHealth('backend offline'))
  }, [])
  return (
    <main className="p-8">
      <h1 className="text-2xl font-bold">PactGuard AI</h1>
      <pre className="mt-4 text-sm">{JSON.stringify(health, null, 2)}</pre>
    </main>
  )
}
