import { useCallback, useEffect, useRef, useState } from 'react'
import { api, ApiError, type MandateInput, type RunEvent, type RunSnapshot } from './client'

export function useRunSession() {
  const [run, setRun] = useState<RunSnapshot | null>(null)
  const [events, setEvents] = useState<RunEvent[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const source = useRef<EventSource | null>(null)

  const runId = run?.run_id
  useEffect(() => {
    if (!runId) return
    const es = api.events(runId)
    source.current = es
    es.onmessage = (m) => {
      const e = JSON.parse(m.data) as RunEvent
      setEvents((prev) => (prev.some((p) => p.seq === e.seq) ? prev : [...prev, e]))
      // The server closes the stream when the run completes; stop EventSource from reconnecting.
      if (e.event === 'complete') es.close()
    }
    return () => es.close()
  }, [runId])

  const guard = useCallback(async <T,>(fn: () => Promise<T>): Promise<T | undefined> => {
    setError(null)
    setBusy(true)
    try {
      return await fn()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }, [])

  const refresh = useCallback(async (id: string) => setRun(await api.getRun(id)), [])

  const start = (mandate?: MandateInput, sandbox = false) =>
    guard(async () => {
      setEvents([])
      setRun(await api.startRun(mandate, sandbox))
    })

  const act = (fn: (id: string) => Promise<unknown>) =>
    guard(async () => {
      if (!run) return
      try {
        await fn(run.run_id)
      } finally {
        await refresh(run.run_id) // a refused action (409) still changes what the UI should show
      }
    })

  return { run, events, error, busy, start, act }
}
