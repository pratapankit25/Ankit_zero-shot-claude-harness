'use client'

import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import type { ChartSpec, ConversationSummary, Dataset, RunDetail, Step } from './types'

const COMING_SOON: { label: string; phase: string; tone: string }[] = [
  { label: 'MsSQL nightly sync', phase: 'Phase 3', tone: 'text-violet-300/70 border-violet-800' },
  { label: 'Scheduled summaries', phase: 'Phase 3', tone: 'text-violet-300/70 border-violet-800' },
  { label: 'Login & district roles', phase: 'Phase 4', tone: 'text-amber-300/70 border-amber-800' },
  { label: 'Cost dashboard', phase: 'Phase 4', tone: 'text-amber-300/70 border-amber-800' },
]

interface Turn extends Partial<RunDetail> {
  question: string
  live?: boolean
  liveSteps?: Step[]
  liveAnswer?: string
}

function Shield() {
  return (
    <svg viewBox="0 0 48 48" className="h-10 w-10 shrink-0" aria-hidden="true">
      <defs>
        <linearGradient id="sg" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#f59e0b" />
          <stop offset="1" stopColor="#b45309" />
        </linearGradient>
      </defs>
      <path d="M24 3l16 6v12c0 10.5-6.8 19.3-16 24C14.8 40.3 8 31.5 8 21V9l16-6z" fill="url(#sg)" />
      <path d="M24 7.2l12 4.5v9.6c0 8.3-5.2 15.4-12 19.4-6.8-4-12-11.1-12-19.4v-9.6l12-4.5z" fill="#0f172a" />
      <path d="M24 12l2.7 5.6 6.1.8-4.5 4.2 1.1 6-5.4-3-5.4 3 1.1-6-4.5-4.2 6.1-.8L24 12z" fill="#f59e0b" />
    </svg>
  )
}

// Single-series chart per the dataviz doctrine: one hue (amber-600 ink on white),
// thin marks with rounded data-ends, recessive grid/axes, hover tooltip, and the
// result table always beside it as the accessible view.
const CHART_INK = '#d97706'
const AXIS_INK = '#64748b'
const GRID_INK = '#e2e8f0'

function AnalystChart({ spec }: { spec: ChartSpec }) {
  const data = spec.points
  const common = {
    margin: { top: 8, right: 12, bottom: 4, left: 0 },
  }
  const tooltipStyle = {
    fontSize: 12, borderRadius: 10, border: `1px solid ${GRID_INK}`,
    boxShadow: '0 4px 12px rgba(15,23,42,0.08)',
  }
  return (
    <div className="mt-3 rounded-xl border border-slate-200 bg-white p-3 shadow-sm" data-testid="chart">
      <p className="mb-1 pl-1 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
        {spec.y} <span className="font-normal normal-case text-slate-400">by {spec.x}</span>
      </p>
      <ResponsiveContainer width="100%" height={240}>
        {spec.type === 'line' ? (
          <LineChart data={data} {...common}>
            <CartesianGrid stroke={GRID_INK} strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="x" tick={{ fontSize: 11, fill: AXIS_INK }} tickLine={false} axisLine={{ stroke: GRID_INK }} />
            <YAxis tick={{ fontSize: 11, fill: AXIS_INK }} tickLine={false} axisLine={false} width={40} />
            <Tooltip contentStyle={tooltipStyle} cursor={{ stroke: AXIS_INK, strokeDasharray: '3 3' }} />
            <Line type="monotone" dataKey="y" name={spec.y} stroke={CHART_INK} strokeWidth={2}
              dot={{ r: 3, fill: CHART_INK, strokeWidth: 0 }} activeDot={{ r: 5 }} />
          </LineChart>
        ) : (
          <BarChart data={data} {...common} barCategoryGap="25%">
            <CartesianGrid stroke={GRID_INK} strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="x" tick={{ fontSize: 11, fill: AXIS_INK }} tickLine={false} axisLine={{ stroke: GRID_INK }}
              interval={0} angle={data.length > 8 ? -30 : 0} textAnchor={data.length > 8 ? 'end' : 'middle'}
              height={data.length > 8 ? 60 : 28} />
            <YAxis tick={{ fontSize: 11, fill: AXIS_INK }} tickLine={false} axisLine={false} width={40} />
            <Tooltip contentStyle={tooltipStyle} cursor={{ fill: 'rgba(148,163,184,0.12)' }} />
            <Bar dataKey="y" name={spec.y} fill={CHART_INK} radius={[4, 4, 0, 0]} maxBarSize={36} />
          </BarChart>
        )}
      </ResponsiveContainer>
    </div>
  )
}

function StatusDot({ status }: { status: string }) {
  if (status === 'done') return <span className="grid h-4 w-4 shrink-0 place-items-center rounded-full bg-emerald-500 text-[9px] font-bold text-white">✓</span>
  if (status === 'error') return <span className="grid h-4 w-4 shrink-0 place-items-center rounded-full bg-rose-500 text-[9px] font-bold text-white">✕</span>
  return <span className="relative grid h-4 w-4 shrink-0 place-items-center"><span className="absolute h-4 w-4 animate-ping rounded-full bg-amber-400/60 motion-reduce:hidden" /><span className="h-2.5 w-2.5 rounded-full bg-amber-500" /></span>
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
  const [copied, setCopied] = useState<string | null>(null)
  const [savingFor, setSavingFor] = useState<string | null>(null)   // run_id with the save-name input open
  const [saveName, setSaveName] = useState('')
  const [savedFor, setSavedFor] = useState<string | null>(null)
  const [editingCol, setEditingCol] = useState<{ ds: string; col: string } | null>(null)
  const [editVal, setEditVal] = useState('')
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

  function copySql(sql: string, runId: string) {
    navigator.clipboard.writeText(sql)
    setCopied(runId)
    setTimeout(() => setCopied(null), 1500)
  }

  async function saveDerived(runId: string) {
    const name = saveName.trim()
    if (!name) return
    const r = await fetch('/datasets/derived', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ run_id: runId, name }),
    })
    if (r.ok) {
      setSavedFor(runId)
      setTimeout(() => setSavedFor(null), 2500)
      await refreshDatasets()
    } else {
      const j = await r.json().catch(() => null)
      setBanner(j?.detail?.message ?? 'Could not save the dataset.')
    }
    setSavingFor(null)
    setSaveName('')
  }

  async function saveColumnDescription(dsId: string, col: string) {
    await fetch(`/datasets/${dsId}/columns/${encodeURIComponent(col)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ description: editVal }),
    })
    setEditingCol(null)
    setEditVal('')
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
    <div className="flex h-screen bg-slate-100">
      {/* ---------------------------- sidebar ---------------------------- */}
      <aside className="flex w-[21rem] shrink-0 flex-col overflow-y-auto bg-slate-900 text-slate-200 shadow-2xl">
        <div className="flex items-center gap-3 border-b border-white/10 px-5 py-4">
          <Shield />
          <div>
            <h1 className="text-[15px] font-bold leading-tight tracking-wide text-white">UP Police Data Analyst</h1>
            <p className="text-[11px] text-amber-400/90">डेटा से पूछिए — English या हिंदी में</p>
          </div>
        </div>

        <section className="px-4 py-4" data-testid="datasets-panel">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400">Datasets</h2>
            <button
              onClick={() => fileRef.current?.click()}
              disabled={uploading}
              className="rounded-lg bg-gradient-to-b from-amber-400 to-amber-500 px-3 py-1.5 text-xs font-semibold text-slate-900 shadow-md shadow-amber-900/30 transition hover:from-amber-300 hover:to-amber-400 focus:outline-none focus:ring-2 focus:ring-amber-300 disabled:opacity-50"
            >
              {uploading ? 'Uploading…' : '⬆ Upload CSVs'}
            </button>
            <input ref={fileRef} type="file" accept=".csv,text/csv" multiple hidden data-testid="file-input"
              onChange={e => handleUpload(e.target.files)} />
          </div>

          {datasets === null && <div className="h-16 animate-pulse rounded-xl bg-white/5" />}
          {libraryEmpty && (
            <p className="rounded-xl border border-dashed border-slate-600 bg-white/5 p-3 text-xs leading-relaxed text-slate-400">
              No datasets yet. Upload one or more CSV exports (FIRs, Dial-112, personnel…) to begin.
            </p>
          )}
          <ul className="space-y-2">
            {datasets?.map(d => (
              <li key={d.id} className={`group rounded-xl border p-3 text-sm transition ${d.status === 'error' ? 'border-rose-800 bg-rose-950/40' : 'border-white/10 bg-white/5 hover:border-amber-500/40 hover:bg-white/10'}`} data-testid="dataset-card">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex min-w-0 items-start gap-2.5">
                    <span className={`mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-lg text-sm ${d.status === 'error' ? 'bg-rose-900/60' : 'bg-slate-800 text-amber-400'}`}>
                      {d.status === 'error' ? '⚠' : '▦'}
                    </span>
                    <div className="min-w-0">
                      <p className="truncate font-medium text-white" title={d.original_filename}>{d.name}</p>
                      {d.status === 'ready' ? (
                        <p className="text-[11px] tabular-nums text-slate-400">{d.row_count?.toLocaleString('en-IN')} rows × {d.columns.length} cols · <span className={`rounded px-1 py-px text-[10px] tracking-wide ${d.source === 'derived' ? 'bg-amber-900/60 text-amber-300' : 'bg-slate-800 text-slate-300'}`}>{d.source.toUpperCase()}</span></p>
                      ) : (
                        <p className="text-[11px] leading-snug text-rose-300">{d.error_message}</p>
                      )}
                    </div>
                  </div>
                  {confirmDelete === d.id ? (
                    <span className="flex shrink-0 gap-1">
                      <button onClick={() => deleteDataset(d.id)} className="rounded-md bg-rose-600 px-2 py-0.5 text-[11px] font-semibold text-white hover:bg-rose-500">Delete</button>
                      <button onClick={() => setConfirmDelete(null)} className="rounded-md border border-slate-600 px-2 py-0.5 text-[11px] text-slate-300 hover:bg-white/10">Keep</button>
                    </span>
                  ) : (
                    <button onClick={() => setConfirmDelete(d.id)} aria-label={`Delete ${d.name}`}
                      className="shrink-0 rounded-md px-1.5 py-0.5 text-[11px] text-slate-500 opacity-0 transition focus:opacity-100 group-hover:opacity-100 hover:bg-rose-900/50 hover:text-rose-300">✕</button>
                  )}
                </div>
                {confirmDelete === d.id && (
                  <p className="mt-2 text-[11px] leading-snug text-rose-300">Removes “{d.name}” and its data. Past answers stay in the audit log.</p>
                )}
                {d.status === 'ready' && (
                  <details className="mt-2">
                    <summary className="cursor-pointer text-xs font-medium text-amber-400/90 hover:text-amber-300">Profile</summary>
                    <div className="mt-2 space-y-1.5 text-xs">
                      {(d.profile?.warnings ?? []).map((w, i) => (
                        <p key={i} className="rounded-lg bg-amber-950/60 px-2 py-1 text-[11px] leading-snug text-amber-300">⚠ {w}</p>
                      ))}
                      <p className="text-[10px] text-slate-500">Tip: click ✎ to tell the agent what a column means — it reads these notes on every question.</p>
                      <div className="overflow-hidden rounded-lg border border-white/10">
                        <table className="w-full text-[11px]">
                          <tbody>
                            {d.columns.slice(0, 30).map((c, ci) => (
                              <tr key={c.name} className={`group/col align-top ${ci % 2 ? 'bg-white/5' : ''}`}>
                                <td className="py-1 pl-2 pr-2 font-mono text-slate-200">{c.name}</td>
                                <td className="py-1 pr-2"><span className={`rounded px-1 py-px text-[10px] ${c.type === 'integer' || c.type === 'real' ? 'bg-sky-900/70 text-sky-300' : c.type === 'date' ? 'bg-violet-900/70 text-violet-300' : 'bg-slate-800 text-slate-400'}`}>{c.type}</span></td>
                                <td className="py-1 pr-2 text-slate-500">
                                  {editingCol?.ds === d.id && editingCol?.col === c.name ? (
                                    <input
                                      autoFocus
                                      value={editVal}
                                      onChange={e => setEditVal(e.target.value)}
                                      onKeyDown={e => {
                                        if (e.key === 'Enter') saveColumnDescription(d.id, c.name)
                                        if (e.key === 'Escape') { setEditingCol(null); setEditVal('') }
                                      }}
                                      onBlur={() => saveColumnDescription(d.id, c.name)}
                                      placeholder="what this column means…"
                                      className="w-full rounded border border-amber-500/60 bg-slate-900 px-1.5 py-0.5 text-[11px] text-amber-100 focus:outline-none"
                                      data-testid="dictionary-input"
                                    />
                                  ) : (
                                    <span className="flex items-start justify-between gap-1">
                                      <span className={c.description ? 'italic text-amber-200/90' : ''}>
                                        {c.description || c.top_values.slice(0, 3).join(', ')}
                                      </span>
                                      <button
                                        aria-label={`Describe ${c.name}`}
                                        onClick={() => { setEditingCol({ ds: d.id, col: c.name }); setEditVal(c.description || '') }}
                                        className="shrink-0 rounded px-1 text-slate-600 opacity-0 transition group-hover/col:opacity-100 focus:opacity-100 hover:text-amber-300">✎</button>
                                    </span>
                                  )}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                      {d.columns.length > 30 && <p className="text-slate-500">… and {d.columns.length - 30} more columns</p>}
                    </div>
                  </details>
                )}
              </li>
            ))}
          </ul>
        </section>

        <section className="border-t border-white/10 px-4 py-4">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400">Conversations</h2>
            <button onClick={newConversation} className="rounded-lg border border-slate-600 px-2.5 py-1 text-xs font-medium text-slate-200 transition hover:border-amber-500/60 hover:text-amber-300">+ New</button>
          </div>
          {conversations.length === 0 && <p className="text-xs text-slate-500">Questions you ask will appear here.</p>}
          <ul className="space-y-1">
            {conversations.slice(0, 15).map(c => (
              <li key={c.id}>
                <button onClick={() => openConversation(c.id)}
                  className={`w-full truncate rounded-lg px-2.5 py-1.5 text-left text-xs transition ${c.id === conversationId ? 'bg-amber-500/15 font-medium text-amber-300' : 'text-slate-300 hover:bg-white/10'}`}>
                  {c.title}
                </button>
              </li>
            ))}
          </ul>
        </section>

        <section className="mt-auto border-t border-white/10 px-4 py-4" data-testid="coming-soon">
          <h2 className="mb-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">Coming soon</h2>
          <p className="mb-2.5 text-[11px] text-slate-500">Planned — not built yet.</p>
          <div className="flex flex-wrap gap-1.5">
            {COMING_SOON.map(s => (
              <span key={s.label} title="Planned — not built yet"
                className={`cursor-not-allowed select-none rounded-full border border-dashed px-2.5 py-1 text-[11px] ${s.tone}`}>
                🔒 {s.label} · {s.phase}
              </span>
            ))}
          </div>
        </section>
      </aside>

      {/* ---------------------------- chat pane ---------------------------- */}
      <main className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center justify-between border-b border-slate-200 bg-white/80 px-6 py-3 backdrop-blur">
          <p className="truncate text-sm font-semibold text-slate-700">
            {conversationId ? (conversations.find(c => c.id === conversationId)?.title ?? 'Conversation') : 'New conversation'}
          </p>
          <span className="flex items-center gap-1.5 rounded-full bg-emerald-50 px-2.5 py-1 text-[11px] font-medium text-emerald-700">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" /> Phase 2 · live
          </span>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-6">
          {turns.length === 0 && (
            <div className="mx-auto mt-20 max-w-lg text-center">
              <div className="mx-auto mb-5 grid h-20 w-20 place-items-center rounded-3xl bg-slate-900 shadow-xl"><Shield /></div>
              <p className="text-lg font-bold text-slate-800">Two steps:</p>
              <div className="mx-auto mt-4 grid max-w-md grid-cols-1 gap-3 text-left sm:grid-cols-2">
                <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                  <p className="text-xl">🗂️</p>
                  <p className="mt-1 text-sm font-semibold text-slate-800">1 · Upload CSVs</p>
                  <p className="mt-0.5 text-xs leading-relaxed text-slate-500">FIRs, Dial-112, personnel — from the left panel.</p>
                </div>
                <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                  <p className="text-xl">💬</p>
                  <p className="mt-1 text-sm font-semibold text-slate-800">2 · Ask anything</p>
                  <p className="mt-0.5 text-xs leading-relaxed text-slate-500">English या हिंदी — जैसे “2025 में सबसे ज़्यादा FIR किस जिले में?”</p>
                </div>
              </div>
            </div>
          )}

          <div className="mx-auto max-w-3xl space-y-7">
            {turns.map((t, i) => (
              <div key={i} data-testid="turn" className="animate-rise">
                <div className="mb-2.5 flex justify-end">
                  <p className="max-w-[80%] rounded-2xl rounded-br-md bg-gradient-to-br from-slate-800 to-slate-900 px-4 py-2.5 text-sm leading-relaxed text-white shadow-md">{t.question}</p>
                </div>

                <div className="max-w-[94%] rounded-2xl rounded-bl-md border border-slate-200 border-l-4 border-l-amber-500 bg-white px-5 py-4 text-sm shadow-md shadow-slate-200/60">
                  {t.live && (
                    <div className="mb-3 space-y-2" data-testid="step-ticker">
                      {(t.liveSteps ?? []).map((s, j) => (
                        <p key={j} className="flex items-center gap-2.5 text-xs text-slate-600">
                          <StatusDot status={s.status} />
                          <span className="font-medium">{s.label_en}</span>
                          <span className="text-slate-400">/ {s.label_hi}</span>
                        </p>
                      ))}
                      {elapsed >= 3 && <p className="pl-6 text-[11px] tabular-nums text-slate-400">{elapsed}s elapsed…</p>}
                    </div>
                  )}

                  {t.status === 'failed' ? (
                    <div className="text-sm">
                      <p className="mb-2.5 rounded-xl border border-rose-200 bg-rose-50 px-3.5 py-2.5 leading-relaxed text-rose-700">{t.error ?? 'Something went wrong.'}</p>
                      <button onClick={() => ask(t.question)} disabled={running}
                        className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-semibold text-slate-700 transition hover:border-amber-500 hover:text-amber-700 disabled:opacity-50">↻ Retry</button>
                    </div>
                  ) : (
                    <div className="prose prose-sm max-w-none prose-p:my-1.5 prose-table:my-2 prose-strong:text-slate-900" data-testid="answer">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {(t.live ? t.liveAnswer : t.answer) || (t.live ? '' : '_No answer._')}
                      </ReactMarkdown>
                    </div>
                  )}

                  {t.status === 'clarification' && !t.live && (
                    <p className="mt-2 text-[11px] text-slate-400">Answering helps me get this right — reply below.</p>
                  )}

                  {!t.live && t.status === 'completed' && (
                    <>
                      {(t.flags?.length ?? 0) > 0 && (
                        <div className="mt-2.5 space-y-1.5" data-testid="flags">
                          {t.flags!.map((f, j) => (
                            <p key={j} className="flex items-start gap-2 rounded-lg border border-orange-200 bg-orange-50 px-3 py-2 text-xs leading-snug text-orange-800">
                              <span aria-hidden="true">⚑</span><span><span className="font-semibold">Data check:</span> {f.message}</span>
                            </p>
                          ))}
                        </div>
                      )}

                      {t.chart && <AnalystChart spec={t.chart} />}

                      {t.result && t.result.rows.length > 0 && (
                        <div className="mt-3 max-h-72 overflow-auto rounded-xl border border-slate-200 shadow-sm" data-testid="result-table">
                          <table className="w-full text-xs">
                            <thead className="sticky top-0">
                              <tr className="bg-slate-900 text-left text-white">
                                {t.result.columns.map(c => <th key={c} className="px-3 py-2 font-semibold">{c}</th>)}
                              </tr>
                            </thead>
                            <tbody className="tabular-nums">
                              {t.result.rows.map((row, ri) => (
                                <tr key={ri} className={ri % 2 ? 'bg-slate-50' : 'bg-white'}>
                                  {row.map((cell, ci) => <td key={ci} className="px-3 py-1.5 text-slate-700">{cell === null ? '—' : String(cell)}</td>)}
                                </tr>
                              ))}
                            </tbody>
                          </table>
                          {t.result.truncated && <p className="bg-slate-100 px-3 py-1.5 text-[11px] text-slate-500">Showing the first {t.result.rows.length} rows.</p>}
                        </div>
                      )}

                      <div className="mt-3 space-y-1.5">
                        {t.sql && (
                          <details data-testid="sql-disclosure" className="group/sql">
                            <summary className="cursor-pointer text-xs font-semibold text-amber-700 hover:text-amber-600">SQL</summary>
                            <div className="mt-1.5 overflow-hidden rounded-xl shadow-md">
                              <div className="flex items-center justify-between bg-slate-800 px-3 py-1.5">
                                <span className="flex gap-1.5"><i className="h-2.5 w-2.5 rounded-full bg-rose-400" /><i className="h-2.5 w-2.5 rounded-full bg-amber-400" /><i className="h-2.5 w-2.5 rounded-full bg-emerald-400" /></span>
                                <span className="text-[10px] uppercase tracking-widest text-slate-400">query it ran</span>
                                <button onClick={() => copySql(t.sql!, t.run_id ?? String(i))}
                                  className="rounded-md bg-slate-700 px-2 py-0.5 text-[10px] font-medium text-slate-200 transition hover:bg-slate-600">
                                  {copied === (t.run_id ?? String(i)) ? '✓ Copied' : 'Copy'}
                                </button>
                              </div>
                              <pre className="overflow-x-auto bg-slate-950 p-3.5 text-[11px] leading-relaxed text-emerald-200">{t.sql}</pre>
                            </div>
                          </details>
                        )}
                        {(t.steps?.length ?? 0) > 0 && (
                          <details>
                            <summary className="cursor-pointer text-xs font-semibold text-amber-700 hover:text-amber-600">Steps</summary>
                            <ul className="mt-1.5 space-y-1 rounded-xl bg-slate-50 p-3 text-xs text-slate-600">
                              {t.steps!.map((s, j) => (
                                <li key={j} className="flex gap-2"><StatusDot status={s.status === 'error' ? 'error' : 'done'} /><span>{s.label_en}{s.detail ? <span className="text-slate-400"> — {s.detail}</span> : null}</span></li>
                              ))}
                            </ul>
                          </details>
                        )}
                        {(t.caveats?.length ?? 0) > 0 && (
                          <details>
                            <summary className="cursor-pointer text-xs font-semibold text-amber-700 hover:text-amber-600">Caveats & assumptions</summary>
                            <ul className="mt-1.5 list-inside list-disc rounded-xl bg-amber-50/70 p-3 text-xs leading-relaxed text-amber-900">
                              {t.caveats!.map((c, j) => <li key={j}>{c}</li>)}
                            </ul>
                          </details>
                        )}
                      </div>

                      {t.run_id && t.sql && (t.result?.rows.length ?? 0) > 0 && (
                        <div className="mt-3 flex flex-wrap items-center gap-2" data-testid="result-actions">
                          <a href={`/runs/${t.run_id}/export?format=xlsx`}
                            className="rounded-lg border border-slate-300 px-2.5 py-1 text-[11px] font-semibold text-slate-600 transition hover:border-emerald-500 hover:text-emerald-700">
                            ⬇ Excel</a>
                          <a href={`/runs/${t.run_id}/export?format=csv`}
                            className="rounded-lg border border-slate-300 px-2.5 py-1 text-[11px] font-semibold text-slate-600 transition hover:border-emerald-500 hover:text-emerald-700">
                            ⬇ CSV</a>
                          {savingFor === t.run_id ? (
                            <span className="flex items-center gap-1.5">
                              <input
                                autoFocus
                                value={saveName}
                                onChange={e => setSaveName(e.target.value)}
                                onKeyDown={e => {
                                  if (e.key === 'Enter') saveDerived(t.run_id!)
                                  if (e.key === 'Escape') { setSavingFor(null); setSaveName('') }
                                }}
                                placeholder="dataset name…"
                                className="w-44 rounded-lg border border-amber-400 px-2 py-1 text-[11px] focus:outline-none focus:ring-1 focus:ring-amber-300"
                                data-testid="save-dataset-name"
                              />
                              <button onClick={() => saveDerived(t.run_id!)} className="rounded-lg bg-amber-500 px-2.5 py-1 text-[11px] font-bold text-slate-900 hover:bg-amber-400">Save</button>
                              <button onClick={() => { setSavingFor(null); setSaveName('') }} className="rounded-lg border border-slate-300 px-2 py-1 text-[11px] text-slate-500 hover:bg-slate-50">Cancel</button>
                            </span>
                          ) : savedFor === t.run_id ? (
                            <span className="rounded-lg bg-emerald-50 px-2.5 py-1 text-[11px] font-semibold text-emerald-700">✓ Saved to library</span>
                          ) : (
                            <button onClick={() => { setSavingFor(t.run_id!); setSaveName('') }}
                              className="rounded-lg border border-slate-300 px-2.5 py-1 text-[11px] font-semibold text-slate-600 transition hover:border-amber-500 hover:text-amber-700"
                              data-testid="save-dataset-button">
                              💾 Save as dataset</button>
                          )}
                        </div>
                      )}

                      {(t.followups?.length ?? 0) > 0 && (
                        <div className="mt-3.5 flex flex-wrap gap-2" data-testid="followups">
                          {t.followups!.map((f, j) => (
                            <button key={j} onClick={() => ask(f)} disabled={running}
                              className="rounded-full border border-amber-300 bg-amber-50 px-3 py-1.5 text-xs font-medium text-amber-900 shadow-sm transition hover:-translate-y-px hover:bg-amber-100 hover:shadow motion-reduce:hover:translate-y-0 disabled:opacity-50">
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
          <p className="mx-6 mb-2 rounded-xl border border-amber-300 bg-amber-50 px-3.5 py-2.5 text-xs text-amber-800">{banner}</p>
        )}

        <form
          onSubmit={e => { e.preventDefault(); ask(input) }}
          className="border-t border-slate-200 bg-white px-6 py-4"
        >
          <div className="mx-auto flex max-w-3xl items-end gap-2.5">
            <textarea
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); ask(input) } }}
              rows={2}
              placeholder="Ask in English or हिंदी…  (Enter to send, Shift+Enter for a new line)"
              disabled={running}
              data-testid="composer"
              className="flex-1 resize-none rounded-2xl border border-slate-300 bg-slate-50 px-4 py-3 text-sm shadow-inner transition focus:border-amber-500 focus:bg-white focus:outline-none focus:ring-2 focus:ring-amber-200 disabled:bg-slate-100"
            />
            <button type="submit" disabled={running || !input.trim()} data-testid="ask-button"
              className="rounded-2xl bg-gradient-to-b from-amber-400 to-amber-500 px-6 py-3 text-sm font-bold text-slate-900 shadow-lg shadow-amber-500/30 transition hover:from-amber-300 hover:to-amber-400 focus:outline-none focus:ring-2 focus:ring-amber-300 disabled:opacity-50 disabled:shadow-none">
              {running ? 'Working…' : 'Ask →'}
            </button>
          </div>
        </form>
      </main>
    </div>
  )
}
