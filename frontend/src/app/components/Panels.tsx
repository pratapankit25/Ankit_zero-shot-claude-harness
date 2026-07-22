'use client'

import { useCallback, useEffect, useState } from 'react'
import type { Costs, ReportSummary, Schedule, SourcesStatus, User } from '../types'

const inputCls = 'w-full rounded-lg border border-slate-600 bg-slate-800 px-2.5 py-1.5 text-xs text-slate-100 placeholder-slate-500 focus:border-amber-500 focus:outline-none'
const btnCls = 'rounded-lg bg-gradient-to-b from-amber-400 to-amber-500 px-3 py-1.5 text-xs font-semibold text-slate-900 hover:from-amber-300 hover:to-amber-400 disabled:opacity-50'
const ghostBtn = 'rounded-lg border border-slate-600 px-2.5 py-1 text-xs text-slate-300 hover:border-amber-500/60 hover:text-amber-300 disabled:opacity-50'

async function jfetch(url: string, init?: RequestInit) {
  const r = await fetch(url, init)
  const body = await r.json().catch(() => null)
  if (!r.ok) throw new Error(body?.detail?.message ?? `Request failed (${r.status})`)
  return body?.data
}

/* ---------------------------------------------------------------- login */

export function LoginGate({ onAuthed }: { onAuthed: (u: User) => void }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const data = await jfetch('/auth/login', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      })
      onAuthed(data.user as User)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed')
    } finally { setBusy(false) }
  }

  return (
    <div className="grid min-h-screen place-items-center bg-slate-950" data-testid="login-gate">
      <form onSubmit={submit} className="w-80 rounded-2xl border border-white/10 bg-slate-900 p-6 shadow-2xl">
        <h1 className="text-center text-lg font-bold text-white">UP Police Data Analyst</h1>
        <p className="mb-5 text-center text-xs text-amber-400/80">Sign in to continue</p>
        <label className="mb-1 block text-[11px] font-medium uppercase tracking-wide text-slate-400">Username</label>
        <input className={inputCls} value={username} onChange={e => setUsername(e.target.value)} autoFocus data-testid="login-username" />
        <label className="mb-1 mt-3 block text-[11px] font-medium uppercase tracking-wide text-slate-400">Password</label>
        <input className={inputCls} type="password" value={password} onChange={e => setPassword(e.target.value)} data-testid="login-password" />
        {error && <p className="mt-3 rounded-lg bg-rose-950/60 px-3 py-2 text-xs text-rose-300">{error}</p>}
        <button type="submit" disabled={busy || !username || !password} className={`${btnCls} mt-4 w-full py-2`}>
          {busy ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </div>
  )
}

/* ---------------------------------------------------------------- sources */

export function SourcesPanel({ visible }: { visible: boolean }) {
  const [status, setStatus] = useState<SourcesStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [form, setForm] = useState({ source_table: '', dataset_name: '', incremental_column: '' })

  const refresh = useCallback(() => {
    jfetch('/sources').then(setStatus).catch(e => setError(e.message))
  }, [])
  useEffect(() => { if (visible) refresh() }, [visible, refresh])
  useEffect(() => {
    if (!visible || !status?.sync_running) return
    const t = setInterval(refresh, 4000)
    return () => clearInterval(t)
  }, [visible, status?.sync_running, refresh])

  if (!visible) return null
  if (error) return <p className="text-xs text-rose-300">{error}</p>
  if (!status) return <div className="h-10 animate-pulse rounded-lg bg-white/5" />

  async function addTable() {
    if (!form.source_table.trim()) return
    const tables = [
      ...status!.tables.map(t => ({ source_table: t.source_table, dataset_name: t.dataset_name, incremental_column: t.incremental_column })),
      { source_table: form.source_table.trim(), dataset_name: form.dataset_name.trim() || form.source_table.trim(), incremental_column: form.incremental_column.trim() || null },
    ]
    try {
      await jfetch('/sources/tables', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ tables }) })
      setForm({ source_table: '', dataset_name: '', incremental_column: '' })
      refresh()
    } catch (e) { setError(e instanceof Error ? e.message : 'failed') }
  }

  async function removeTable(source_table: string) {
    const tables = status!.tables.filter(t => t.source_table !== source_table)
      .map(t => ({ source_table: t.source_table, dataset_name: t.dataset_name, incremental_column: t.incremental_column }))
    await jfetch('/sources/tables', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ tables }) })
    refresh()
  }

  return (
    <div className="space-y-2 text-xs" data-testid="sources-panel">
      {!status.configured ? (
        <p className="rounded-lg border border-dashed border-slate-600 bg-white/5 p-2.5 leading-relaxed text-slate-400">
          Not configured. Set <span className="font-mono text-[10px]">AGENT_MSSQL_HOST / DATABASE / USERNAME / PASSWORD</span> in <span className="font-mono text-[10px]">.env</span> (read-only login), restart, and the nightly extract runs at {String(status.sync_hour).padStart(2, '0')}:00 — daytime questions never touch the DB.
        </p>
      ) : (
        <>
          <p className="text-slate-400">Connected to <span className="text-slate-200">{status.database}</span> · nightly at {String(status.sync_hour).padStart(2, '0')}:00 · questions never touch MsSQL in the day.</p>
          <div className="flex gap-1.5">
            <button className={btnCls} disabled={status.sync_running}
              onClick={() => jfetch('/sources/sync', { method: 'POST' }).then(refresh).catch(e => setError(e.message))}>
              {status.sync_running ? 'Syncing…' : '⟳ Sync now'}
            </button>
          </div>
        </>
      )}
      <ul className="space-y-1.5">
        {status.tables.map(t => (
          <li key={t.id} className="rounded-lg border border-white/10 bg-white/5 p-2">
            <div className="flex items-start justify-between gap-1">
              <div>
                <p className="font-mono text-[11px] text-slate-200">{t.source_table}</p>
                <p className="text-[10px] text-slate-500">
                  → {t.dataset_name}{t.incremental_column ? ` · Δ ${t.incremental_column}` : ' · full'}
                  {t.synced_at ? ` · synced ${t.synced_at.slice(0, 16).replace('T', ' ')}` : ' · never synced'}
                  {t.row_count != null ? ` · ${t.row_count.toLocaleString('en-IN')} rows` : ''}
                </p>
                {t.last_run?.error && <p className="text-[10px] text-rose-300">last run failed: {t.last_run.error}</p>}
              </div>
              <button onClick={() => removeTable(t.source_table)} className="text-slate-600 hover:text-rose-400">✕</button>
            </div>
          </li>
        ))}
      </ul>
      <div className="space-y-1.5 rounded-lg border border-dashed border-slate-700 p-2">
        <input className={inputCls} placeholder="source table e.g. dbo.FIR" value={form.source_table}
          onChange={e => setForm({ ...form, source_table: e.target.value })} />
        <input className={inputCls} placeholder="dataset name in the library" value={form.dataset_name}
          onChange={e => setForm({ ...form, dataset_name: e.target.value })} />
        <input className={inputCls} placeholder="incremental column (optional, e.g. fir_id)" value={form.incremental_column}
          onChange={e => setForm({ ...form, incremental_column: e.target.value })} />
        <button onClick={addTable} className={ghostBtn}>+ Add table</button>
      </div>
    </div>
  )
}

/* ---------------------------------------------------------------- reports & schedules */

export function ReportsPanel({ visible, isAdmin, onOpenReport }: {
  visible: boolean; isAdmin: boolean; onOpenReport: (id: string) => void
}) {
  const [schedules, setSchedules] = useState<Schedule[]>([])
  const [reports, setReports] = useState<ReportSummary[]>([])
  const [error, setError] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [form, setForm] = useState({ name: '', cadence: 'daily', hour: 7, questions: '', recipients: '', language: 'en' })

  const refresh = useCallback(() => {
    jfetch('/schedules').then(setSchedules).catch(e => setError(e.message))
    jfetch('/reports').then(setReports).catch(() => {})
  }, [])
  useEffect(() => { if (visible) refresh() }, [visible, refresh])

  if (!visible) return null
  if (error) return <p className="text-xs text-rose-300">{error}</p>

  async function create() {
    const questions = form.questions.split('\n').map(q => q.trim()).filter(Boolean)
    if (!form.name.trim() || questions.length === 0) return
    try {
      await jfetch('/schedules', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: form.name.trim(), cadence: form.cadence, hour: Number(form.hour),
          questions, language: form.language,
          recipients: form.recipients.split(',').map(r => r.trim()).filter(Boolean),
        }),
      })
      setCreating(false)
      setForm({ name: '', cadence: 'daily', hour: 7, questions: '', recipients: '', language: 'en' })
      refresh()
    } catch (e) { setError(e instanceof Error ? e.message : 'failed') }
  }

  return (
    <div className="space-y-2 text-xs" data-testid="reports-panel">
      {schedules.length === 0 && !creating && (
        <p className="text-slate-500">No scheduled briefs yet{isAdmin ? ' — create one below.' : '.'}</p>
      )}
      <ul className="space-y-1.5">
        {schedules.map(s => (
          <li key={s.id} className="rounded-lg border border-white/10 bg-white/5 p-2">
            <div className="flex items-center justify-between gap-1">
              <p className="font-medium text-slate-200">{s.name}</p>
              {isAdmin && (
                <span className="flex gap-1">
                  <button className={ghostBtn}
                    onClick={() => jfetch(`/schedules/${s.id}/run`, { method: 'POST' }).then(() => setTimeout(refresh, 1500))}>▶ Run</button>
                  <button className={ghostBtn}
                    onClick={() => jfetch(`/schedules/${s.id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ enabled: !s.enabled }) }).then(refresh)}>
                    {s.enabled ? 'Pause' : 'Resume'}
                  </button>
                </span>
              )}
            </div>
            <p className="text-[10px] text-slate-500">
              {s.cadence} at {String(s.hour).padStart(2, '0')}:00 · {s.questions.length} question(s)
              {s.recipients.length > 0 ? ` · ✉ ${s.recipients.length}` : ''}
              {!s.enabled ? ' · paused' : ''}
              {s.last_run_at ? ` · last ${s.last_run_at.slice(0, 16).replace('T', ' ')}` : ''}
            </p>
          </li>
        ))}
      </ul>
      {isAdmin && (creating ? (
        <div className="space-y-1.5 rounded-lg border border-dashed border-slate-700 p-2">
          <input className={inputCls} placeholder="name e.g. Morning crime brief" value={form.name}
            onChange={e => setForm({ ...form, name: e.target.value })} />
          <div className="flex gap-1.5">
            <select className={inputCls} value={form.cadence} onChange={e => setForm({ ...form, cadence: e.target.value })}>
              <option value="daily">daily</option><option value="weekly">weekly (Mon)</option>
            </select>
            <select className={inputCls} value={form.hour} onChange={e => setForm({ ...form, hour: Number(e.target.value) })}>
              {Array.from({ length: 24 }, (_, h) => <option key={h} value={h}>{String(h).padStart(2, '0')}:00</option>)}
            </select>
          </div>
          <textarea className={`${inputCls} h-20 resize-none`} placeholder={'one question per line\nYesterday’s FIR count by district'}
            value={form.questions} onChange={e => setForm({ ...form, questions: e.target.value })} />
          <input className={inputCls} placeholder="email recipients, comma-separated (optional)" value={form.recipients}
            onChange={e => setForm({ ...form, recipients: e.target.value })} />
          <div className="flex gap-1.5">
            <button onClick={create} className={btnCls}>Create</button>
            <button onClick={() => setCreating(false)} className={ghostBtn}>Cancel</button>
          </div>
        </div>
      ) : (
        <button onClick={() => setCreating(true)} className={ghostBtn} data-testid="new-schedule">+ New scheduled brief</button>
      ))}
      {reports.length > 0 && (
        <>
          <h3 className="pt-1 text-[10px] font-semibold uppercase tracking-widest text-slate-500">Generated reports</h3>
          <ul className="space-y-1">
            {reports.slice(0, 8).map(r => (
              <li key={r.id}>
                <button onClick={() => onOpenReport(r.id)}
                  className="w-full truncate rounded-lg px-2 py-1 text-left text-[11px] text-slate-300 hover:bg-white/10">
                  📄 {r.title}{r.status !== 'completed' ? ` · ${r.status}` : ''}
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  )
}

/* ---------------------------------------------------------------- admin */

export function AdminPanel({ visible, authRequired, me, onUsersChanged }: {
  visible: boolean; authRequired: boolean; me: User | null; onUsersChanged: () => void
}) {
  const [users, setUsers] = useState<User[]>([])
  const [costs, setCosts] = useState<Costs | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [form, setForm] = useState({ username: '', password: '', role: 'viewer', district: '' })

  const refresh = useCallback(() => {
    if (authRequired || me) {
      jfetch('/admin/users').then(setUsers).catch(() => {})
      jfetch('/admin/costs').then(setCosts).catch(() => {})
    }
  }, [authRequired, me])
  useEffect(() => { if (visible) refresh() }, [visible, refresh])

  if (!visible) return null

  async function bootstrap() {
    try {
      await jfetch('/auth/bootstrap', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: form.username, password: form.password }),
      })
      onUsersChanged()
    } catch (e) { setError(e instanceof Error ? e.message : 'failed') }
  }

  async function createUser() {
    try {
      await jfetch('/admin/users', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...form, district: form.district.trim() || null }),
      })
      setForm({ username: '', password: '', role: 'viewer', district: '' })
      refresh()
    } catch (e) { setError(e instanceof Error ? e.message : 'failed') }
  }

  return (
    <div className="space-y-3 text-xs" data-testid="admin-panel">
      {error && <p className="rounded-lg bg-rose-950/60 px-2 py-1.5 text-rose-300">{error}</p>}

      {!authRequired ? (
        <div className="space-y-1.5 rounded-lg border border-dashed border-amber-700/60 bg-amber-950/30 p-2.5">
          <p className="leading-relaxed text-amber-200/90">Open access (no login yet). Create the first admin to switch on login &amp; district roles:</p>
          <input className={inputCls} placeholder="admin username" value={form.username} onChange={e => setForm({ ...form, username: e.target.value })} />
          <input className={inputCls} type="password" placeholder="password (8+ chars)" value={form.password} onChange={e => setForm({ ...form, password: e.target.value })} />
          <button onClick={bootstrap} className={btnCls} data-testid="bootstrap-admin">Create admin &amp; enable login</button>
        </div>
      ) : (
        <>
          <div>
            <h3 className="mb-1 text-[10px] font-semibold uppercase tracking-widest text-slate-500">Users</h3>
            <ul className="space-y-1">
              {users.map(u => (
                <li key={u.id} className="flex items-center justify-between rounded-lg bg-white/5 px-2 py-1">
                  <span className="text-slate-200">{u.username} <span className="text-slate-500">· {u.role}{u.district ? ` · ${u.district}` : ''}</span></span>
                  {me?.id !== u.id && (
                    <button onClick={() => jfetch(`/admin/users/${u.id}`, { method: 'DELETE' }).then(refresh)}
                      className="text-slate-600 hover:text-rose-400">✕</button>
                  )}
                </li>
              ))}
            </ul>
            <div className="mt-1.5 space-y-1.5 rounded-lg border border-dashed border-slate-700 p-2">
              <input className={inputCls} placeholder="username" value={form.username} onChange={e => setForm({ ...form, username: e.target.value })} />
              <input className={inputCls} type="password" placeholder="password (8+ chars)" value={form.password} onChange={e => setForm({ ...form, password: e.target.value })} />
              <div className="flex gap-1.5">
                <select className={inputCls} value={form.role} onChange={e => setForm({ ...form, role: e.target.value })}>
                  <option value="viewer">viewer</option><option value="analyst">analyst</option><option value="admin">admin</option>
                </select>
                <input className={inputCls} placeholder="district (viewers)" value={form.district} onChange={e => setForm({ ...form, district: e.target.value })} />
              </div>
              <button onClick={createUser} className={ghostBtn}>+ Add user</button>
            </div>
          </div>
        </>
      )}

      {costs && (
        <div data-testid="costs-panel">
          <h3 className="mb-1 text-[10px] font-semibold uppercase tracking-widest text-slate-500">LLM spend (estimates)</h3>
          <p className="text-slate-200">Today: ₹{costs.today.cost_inr.toFixed(2)} <span className="text-slate-500">· {(costs.today.input_tokens + costs.today.output_tokens).toLocaleString('en-IN')} tokens · {costs.today.runs} answers</span></p>
          {costs.days.length > 1 && (
            <div className="mt-1 flex h-12 items-end gap-px" aria-hidden="true">
              {costs.days.map(d => {
                const max = Math.max(...costs.days.map(x => x.cost_inr), 0.01)
                return <span key={d.date} title={`${d.date}: ₹${d.cost_inr}`}
                  className="min-w-[6px] flex-1 rounded-t bg-amber-500/70"
                  style={{ height: `${Math.max(8, (d.cost_inr / max) * 100)}%` }} />
              })}
            </div>
          )}
          {costs.top_conversations.length > 0 && (
            <p className="mt-1 truncate text-[10px] text-slate-500">Top: {costs.top_conversations[0].title} ({costs.top_conversations[0].tokens.toLocaleString('en-IN')} tokens)</p>
          )}
        </div>
      )}
    </div>
  )
}
