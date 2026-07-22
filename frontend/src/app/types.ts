export interface ColumnInfo {
  name: string
  original_name: string
  type: string
  null_count: number
  distinct_count: number | null
  min: string | null
  max: string | null
  top_values: string[]
  description: string
}

export interface Dataset {
  id: string
  name: string
  original_filename: string
  source: string
  status: 'ready' | 'error'
  error_message: string | null
  row_count: number | null
  size_bytes: number | null
  columns: ColumnInfo[]
  profile: { warnings: string[]; date_columns: string[]; profiled_rows: number } | null
  district: string | null
  synced_at: string | null
  created_at: string | null
}

export interface Step {
  label_en: string
  label_hi: string
  status: 'start' | 'done' | 'error'
  detail?: string | null
}

export interface ResultTable {
  columns: string[]
  rows: (string | number | null)[][]
  row_count: number
  truncated: boolean
}

export interface ChartSpec {
  type: 'bar' | 'line'
  x: string
  y: string
  points: { x: string; y: number }[]
}

export interface AnomalyFlag {
  kind: string
  message: string
}

export interface RunDetail {
  run_id: string
  conversation_id: string | null
  status: 'completed' | 'failed' | 'clarification' | 'pending'
  question: string | null
  answer: string | null
  language: string | null
  sql: string | null
  steps: Step[]
  result: ResultTable | null
  caveats: string[]
  followups: string[]
  chart: ChartSpec | null
  flags: AnomalyFlag[]
  usage: { input_tokens: number; output_tokens: number }
  duration_ms: number | null
  error: string | null
  freshness: string | null
}

export interface ConversationSummary {
  id: string
  title: string
  updated_at: string | null
  run_count: number
}

export interface User {
  id: string
  username: string
  role: 'admin' | 'analyst' | 'viewer'
  district: string | null
}

export interface SyncTable {
  id: string
  source_table: string
  dataset_name: string
  incremental_column: string | null
  enabled: boolean
  synced_at: string | null
  row_count: number | null
  last_run: { status: string; rows: number | null; note: string | null; error: string | null; started_at: string | null } | null
}

export interface SourcesStatus {
  configured: boolean
  host: string | null
  database: string | null
  sync_hour: number
  sync_running: boolean
  tables: SyncTable[]
  recent_runs: { source_table: string; status: string; rows: number | null; mode: string | null; note: string | null; error: string | null; started_at: string | null }[]
}

export interface Schedule {
  id: string
  name: string
  cadence: 'daily' | 'weekly'
  hour: number
  weekday: number | null
  questions: string[]
  language: string
  recipients: string[]
  enabled: boolean
  last_run_at: string | null
}

export interface ReportSummary {
  id: string
  title: string
  status: string
  note: string | null
  created_at: string | null
}

export interface ReportDetail extends ReportSummary {
  content_md: string
  deliveries: { recipient: string; status: string; attempts: number; error: string | null }[]
}

export interface Costs {
  note: string
  today: { date: string; input_tokens: number; output_tokens: number; runs: number; cost_inr: number }
  days: { date: string; input_tokens: number; output_tokens: number; runs: number; cost_inr: number }[]
  top_conversations: { title: string; tokens: number }[]
}
