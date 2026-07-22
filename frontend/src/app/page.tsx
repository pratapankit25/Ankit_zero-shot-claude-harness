'use client'

import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { ConversationSummary, Dataset, RunDetail, Step } from './types'

const COMING_SOON: { label: string; phase: string }[] = [
  { label: 'Charts & graphs', phase: 'Phase 2' },
  { label: 'Excel / PDF export', phase: 'Phase 2' },
  { label: 'Saved datasets', phase: 'Phase 2' },
  { label: 'Data dictionary', phase: 'Phase 2' },
  { label: 'MsSQL nightly sync', phase: 'Phase 3' },
  { label: 'Scheduled summaries', phase: 'Phase 3' },
  { label: 'Login & district roles', phase: 'Phase 4' },
  { label: 'Cost dashboard', phase: 'Phase 4' },
]

interface Turn extends Partial<RunDetail> {
  question: string
  live?: boolean
  liveSteps?: Step[]
  liveAnswer?: string
}

export default function Home() {
  const [datasets, setDatasets] = useState<Dataset[] | null>(null)
  const [conversations, setConversations] = useState<ConversationSummary[]>([])
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [turns, setTurns] = useState<Turn[]>([])
  const [input, setInput] = useState('')
  const [running, setRunning] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const [banner, setBanner] = useState<string | null>(null)
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const chatEndRef = useRef<HTMLDivElement>(null)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  async function refreshDatasets() {
    try {
      const r = await fetch('/datasets')
      const j = await r.json()
      setDatasets(j.data ?? [])
    } catch {
      setDatasets([])
      setBanner('Could not reach the server — is it running?')
    }
  }
  async function refreshConversations() {
    try {
      const r = await fetch('/conversations')
      setConversations((await r.json()).data ?? [])
    } catch { /* banner already handled by datasets fetch */ }
  }
  useEffect(() => { refreshDatasets(); refreshConversations() }, [])
  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [turns])

  async function openConversation(id: string) {
    const r = await fetch(`/conversations/${id}`)
    if (!r.ok) return
    const detail = (await r.json()).data
    setConversationId(id)
    setTurns(detail.runs.map((run: RunDetail) => ({ ...run, question: run.question ?? '' })))
  }

  function newConversation() {
    setConversationId(null)
    setTurns([])
  }

  async function handleUpload(files: FileList | null) {
    if (!files || files.length === 0) return
    setUploading(true)
    setBanner(null)
    const form = new FormData()
    Array.from(files).forEach(f => form.append('files', f))
    try {
      const r = await fetch('/datasets', { method: 'POST', body: form })
      if (!r.ok) {
        const j = await r.json().catch(() => null)
        setBanner(j?.detail?.message ?? `Upload failed (${r.status})`)
      }
      await refreshDatasets()
    } catch {
      setBanner('Upload failed — could not reach the server.')
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  async function deleteDataset(id: string) {
    setConfirmDelete(null)
    await fetch(`/datasets/${id}`, { method: 'DELETE' })
    await refreshDatasets()
  }

  async function ask(question: string) {
    const q = question.trim()
    if (!q || running) return
    setInput('')
    setRunning(true)
    setElapsed(0)
    const startedAt = Date.now()
    timerRef.current = setInterval(() => setElapsed(Math.floor((Date.now() - startedAt) / 1000)), 1000)
    setTurns(prev => [...prev, { question: q, live: true, liveSteps: [], liveAnswer: '' }])

    const updateLive = (fn: (t: Turn) => Turn) =>
      setTurns(prev => prev.map((t, i) => (i === prev.length - 1 ? fn(t) : t)))

    try {
      const r = await fetch('/questions/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: q, conversation_id: conversationId }),
      })
      if (!r.ok || !r.body) {
        const j = await r.json().catch(() => null)
        throw new Error(j?.detail?.message ?? j?.detail?.[0]?.msg ?? `Request failed (${r.status})`)
      }
      const reader = r.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let finalRun: RunDetail | null = null
      for (;;) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        for (;;) {
          const sep = buffer.indexOf('\n\n')
          if (sep === -1) break
          const block = buffer.slice(0, sep)
          buffer = buffer.slice(sep + 2)
          const eventLine = block.split('\n').find(l => l.startsWith('event: '))
          const dataLine = block.split('\n').find(l => l.startsWith('data: '))
          if (!eventLine || !dataLine) continue
          const type = eventLine.slice(7).trim()
          const data = JSON.parse(dataLine.slice(6))
          if (type === 'run' && !conversationId) setConversationId(data.conversation_id)
          if (type === 'step') {
            updateLive(t => {
              const steps = [...(t.liveSteps ?? [])]
              const last = steps[steps.length - 1]
              if (data.status !== 'start' && last && last.label_en === data.label_en) {
                steps[steps.length - 1] = data
              } else steps.push(data)
              return { ...t, liveSteps: steps }
            })
          }
          if (type === 'answer_delta') updateLive(t => ({ ...t, liveAnswer: (t.liveAnswer ?? '') + data.text }))
          if (type === 'final') finalRun = data.run as RunDetail
          if (type === 'error') finalRun = { error: data.message, status: 'failed' } as RunDetail
        }
      }
      updateLive(t => ({ ...t, ...(finalRun ?? { status: 'failed', error: 'The stream ended unexpectedly.' }), question: q, live: false }))
    } catch (e) {
      updateLive(t => ({ ...t, live: false, status: 'failed', error: e instanceof Error ? e.message : 'Network error — is the server running?' }))
    } finally {
      if (timerRef.current) clearInterval(timerRef.current)
      setRunning(false)
      refreshConversations()
    }
  }

  const libraryEmpty = datasets !== null && datasets.length === 0

  return (
    <div className="flex h-screen">
      {/* ---------------------------- sidebar ---------------------------- */}
      <aside className="flex w-80 shrink-0 flex-col overflow-y-auto border-r border-slate-200 bg-white">
        <div className="border-b border-slate-200 px-4 py-4">
          <h1 className="text-base font-bold leading-tight">UP Police Data Analyst</h1>
          <p className="text-xs text-slate-500">डेटा से पूछिए — English या हिंदी में</p>
        </div>

        <section className="px-4 py-3" data-testid="datasets-panel">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Datasets</h2>
            <button
              onClick={() => fileRef.current?.click()}
              disabled={uploading}
              className="rounded-md bg-blue-600 px-2.5 py-1.5 text-xs font-medium text-white hover:bg-blue-700 disabled:opacity-50"
            >
              {uploading ? 'Uploading…' : 'Upload CSVs'}
            </button>
            <input ref={fileRef} type="file" accept=".csv,text/csv" multiple hidden data-testid="file-input"
              onChange={e => handleUpload(e.target.files)} />
          </div>

          {datasets === null && <div className="h-16 animate-pulse rounded-lg bg-slate-100" />}
          {libraryEmpty && (
            <p className="rounded-lg border border-dashed border-slate-300 p-3 text-xs text-slate-500">
              No datasets yet. Upload one or more CSV exports (FIRs, Dial-112, personnel…) to begin.
            </p>
          )}
          <ul className="space-y-2">
            {datasets?.map(d => (
              <li key={d.id} className={`rounded-lg border p-2.5 text-sm ${d.status === 'error' ? 'border-red-200 bg-red-50' : 'border-slate-200'}`} data-testid="dataset-card">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="truncate font-medium" title={d.original_filename}>{d.name}</p>
                    {d.status === 'ready' ? (
                      <p className="text-xs text-slate-500">{d.row_count?.toLocaleString('en-IN')} rows × {d.columns.length} cols · <span className="rounded bg-slate-100 px-1">{d.source.toUpperCase()}</span></p>
                    ) : (
                      <p className="text-xs text-red-600">{d.error_message}</p>
                    )}
                  </div>
                  {confirmDelete === d.id ? (
                    <span className="flex shrink-0 gap-1">
                      <button onClick={() => deleteDataset(d.id)} className="rounded bg-red-600 px-1.5 py-0.5 text-[11px] font-medium text-white hover:bg-red-700">Delete</button>
                      <button onClick={() => setConfirmDelete(null)} className="rounded border border-slate-300 px-1.5 py-0.5 text-[11px] hover:bg-slate-50">Keep</button>
                    </span>
                  ) : (
                    <button onClick={() => setConfirmDelete(d.id)} aria-label={`Delete ${d.name}`}
                      className="shrink-0 rounded px-1.5 py-0.5 text-[11px] text-slate-400 hover:bg-slate-100 hover:text-red-600">✕</button>
                  )}
                </div>
                {confirmDelete === d.id && (
                  <p className="mt-1.5 text-[11px] text-red-700">Removes “{d.name}” and its data. Past answers stay in the audit log.</p>
                )}
                {d.status === 'ready' && (
                  <details className="mt-1.5">
                    <summary className="cursor-pointer text-xs text-blue-700 hover:underline">Profile</summary>
                    <div className="mt-1.5 space-y-1 text-xs">
                      {(d.profile?.warnings ?? []).map((w, i) => (
                        <p key={i} className="rounded bg-amber-50 px-1.5 py-1 text-amber-800">⚠ {w}</p>
                      ))}
                      <table className="w-full text-[11px]">
                        <tbody>
                          {d.columns.slice(0, 30).map(c => (
                            <tr key={c.name} className="border-t border-slate-100 align-top">
                              <td className="py-1 pr-2 font-mono">{c.name}</td>
                              <td className="py-1 pr-2 text-slate-500">{c.type}</td>
                              <td className="py-1 text-slate-400">{c.top_values.slice(0, 3).join(', ')}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                      {d.columns.length > 30 && <p className="text-slate-400">… and {d.columns.length - 30} more columns</p>}
                    </div>
                  </details>
                )}
              </li>
            ))}
          </ul>
        </section>

        <section className="border-t border-slate-200 px-4 py-3">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Conversations</h2>
            <button onClick={newConversation} className="rounded-md border border-slate-300 px-2 py-1 text-xs font-medium hover:bg-slate-50">New</button>
          </div>
          {conversations.length === 0 && <p className="text-xs text-slate-400">Questions you ask will appear here.</p>}
          <ul className="space-y-1">
            {conversations.slice(0, 15).map(c => (
              <li key={c.id}>
                <button onClick={() => openConversation(c.id)}
                  className={`w-full truncate rounded-md px-2 py-1.5 text-left text-xs hover:bg-slate-100 ${c.id === conversationId ? 'bg-slate-100 font-medium' : ''}`}>
                  {c.title}
                </button>
              </li>
            ))}
          </ul>
        </section>

        <section className="mt-auto border-t border-slate-200 px-4 py-3" data-testid="coming-soon">
          <h2 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-400">Coming soon</h2>
          <p className="mb-2 text-[11px] text-slate-400">Planned — not built yet.</p>
          <div className="flex flex-wrap gap-1.5">
            {COMING_SOON.map(s => (
              <span key={s.label} title="Planned — not built yet"
                className="cursor-not-allowed select-none rounded-full border border-dashed border-slate-300 px-2 py-0.5 text-[11px] text-slate-400">
                {s.label} · {s.phase}
              </span>
            ))}
          </div>
        </section>
      </aside>

      {/* ---------------------------- chat pane ---------------------------- */}
      <main className="flex min-w-0 flex-1 flex-col">
        <div className="flex-1 overflow-y-auto px-6 py-6">
          {turns.length === 0 && (
            <div className="mx-auto mt-24 max-w-md text-center text-sm text-slate-500">
              <p className="mb-2 text-3xl">🗂️ → ❓ → 📊</p>
              <p className="font-medium text-slate-700">Two steps:</p>
              <p className="mt-1">1. Upload CSVs from the left panel.<br />2. Ask a question below — English या हिंदी, जैसे “2025 में सबसे ज़्यादा FIR किस जिले में?”</p>
            </div>
          )}

          <div className="mx-auto max-w-3xl space-y-6">
            {turns.map((t, i) => (
              <div key={i} data-testid="turn">
                <div className="mb-2 flex justify-end">
                  <p className="max-w-[80%] rounded-2xl rounded-br-sm bg-blue-600 px-4 py-2 text-sm text-white">{t.question}</p>
                </div>

                <div className="max-w-[92%] rounded-2xl rounded-bl-sm border border-slate-200 bg-white px-4 py-3 text-sm shadow-sm">
                  {t.live && (
                    <div className="mb-2 space-y-1" data-testid="step-ticker">
                      {(t.liveSteps ?? []).map((s, j) => (
                        <p key={j} className="text-xs text-slate-500">
                          {s.status === 'done' ? '✓' : s.status === 'error' ? '✕' : <span className="inline-block animate-pulse">●</span>}{' '}
                          {s.label_en} <span className="text-slate-400">/ {s.label_hi}</span>
                        </p>
                      ))}
                      {elapsed >= 3 && <p className="text-[11px] text-slate-400">{elapsed}s elapsed…</p>}
                    </div>
                  )}

                  {t.status === 'failed' ? (
                    <div className="text-sm">
                      <p className="mb-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-red-700">{t.error ?? 'Something went wrong.'}</p>
                      <button onClick={() => ask(t.question)} disabled={running}
                        className="rounded-md border border-slate-300 px-2.5 py-1 text-xs font-medium hover:bg-slate-50 disabled:opacity-50">↻ Retry</button>
                    </div>
                  ) : (
                    <div className="prose prose-sm max-w-none prose-p:my-1.5 prose-table:my-2" data-testid="answer">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {(t.live ? t.liveAnswer : t.answer) || (t.live ? '' : '_No answer._')}
                      </ReactMarkdown>
                    </div>
                  )}

                  {t.status === 'clarification' && !t.live && (
                    <p className="mt-1.5 text-[11px] text-slate-400">Answering helps me get this right — reply below.</p>
                  )}

                  {!t.live && t.status === 'completed' && (
                    <>
                      {t.result && t.result.rows.length > 0 && (
                        <div className="mt-2 max-h-72 overflow-auto rounded-lg border border-slate-200" data-testid="result-table">
                          <table className="w-full text-xs">
                            <thead className="sticky top-0 bg-slate-50">
                              <tr>{t.result.columns.map(c => <th key={c} className="px-2 py-1.5 text-left font-semibold">{c}</th>)}</tr>
                            </thead>
                            <tbody>
                              {t.result.rows.map((row, ri) => (
                                <tr key={ri} className="border-t border-slate-100">
                                  {row.map((cell, ci) => <td key={ci} className="px-2 py-1">{cell === null ? '—' : String(cell)}</td>)}
                                </tr>
                              ))}
                            </tbody>
                          </table>
                          {t.result.truncated && <p className="bg-slate-50 px-2 py-1 text-[11px] text-slate-500">Showing the first {t.result.rows.length} rows.</p>}
                        </div>
                      )}

                      <div className="mt-2 space-y-1">
                        {t.sql && (
                          <details data-testid="sql-disclosure">
                            <summary className="cursor-pointer text-xs font-medium text-blue-700 hover:underline">SQL</summary>
                            <div className="relative mt-1">
                              <pre className="overflow-x-auto rounded-lg bg-slate-900 p-3 text-[11px] leading-relaxed text-slate-100">{t.sql}</pre>
                              <button onClick={() => navigator.clipboard.writeText(t.sql!)}
                                className="absolute right-2 top-2 rounded bg-slate-700 px-1.5 py-0.5 text-[10px] text-slate-200 hover:bg-slate-600">Copy</button>
                            </div>
                          </details>
                        )}
                        {(t.steps?.length ?? 0) > 0 && (
                          <details>
                            <summary className="cursor-pointer text-xs font-medium text-blue-700 hover:underline">Steps</summary>
                            <ul className="mt-1 space-y-0.5 text-xs text-slate-600">
                              {t.steps!.map((s, j) => (
                                <li key={j}>{s.status === 'error' ? '✕' : '✓'} {s.label_en}{s.detail ? <span className="text-slate-400"> — {s.detail}</span> : null}</li>
                              ))}
                            </ul>
                          </details>
                        )}
                        {(t.caveats?.length ?? 0) > 0 && (
                          <details>
                            <summary className="cursor-pointer text-xs font-medium text-blue-700 hover:underline">Caveats & assumptions</summary>
                            <ul className="mt-1 list-inside list-disc text-xs text-slate-600">
                              {t.caveats!.map((c, j) => <li key={j}>{c}</li>)}
                            </ul>
                          </details>
                        )}
                      </div>

                      {(t.followups?.length ?? 0) > 0 && (
                        <div className="mt-2.5 flex flex-wrap gap-1.5" data-testid="followups">
                          {t.followups!.map((f, j) => (
                            <button key={j} onClick={() => ask(f)} disabled={running}
                              className="rounded-full border border-blue-200 bg-blue-50 px-2.5 py-1 text-xs text-blue-700 hover:bg-blue-100 disabled:opacity-50">
                              {f}
                            </button>
                          ))}
                        </div>
                      )}
                    </>
                  )}
                </div>
              </div>
            ))}
          </div>
          <div ref={chatEndRef} />
        </div>

        {banner && (
          <p className="mx-6 mb-2 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-800">{banner}</p>
        )}

        <form
          onSubmit={e => { e.preventDefault(); ask(input) }}
          className="border-t border-slate-200 bg-white px-6 py-4"
        >
          <div className="mx-auto flex max-w-3xl items-end gap-2">
            <textarea
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); ask(input) } }}
              rows={2}
              placeholder="Ask in English or हिंदी…  (Enter to send, Shift+Enter for a new line)"
              disabled={running}
              data-testid="composer"
              className="flex-1 resize-none rounded-xl border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:bg-slate-50"
            />
            <button type="submit" disabled={running || !input.trim()} data-testid="ask-button"
              className="rounded-xl bg-blue-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50">
              {running ? 'Working…' : 'Ask'}
            </button>
          </div>
        </form>
      </main>
    </div>
  )
}
