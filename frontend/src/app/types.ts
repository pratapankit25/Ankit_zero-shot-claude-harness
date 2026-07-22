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
}

export interface ConversationSummary {
  id: string
  title: string
  updated_at: string | null
  run_count: number
}
