// Mirrors the backend schemas in backend/src/models/schemas.py and the chat events in
// backend/src/models/events.py.

export interface ChatRequest {
  message: string
  session_id: string | null
}

export type StepKind = 'resolve_entity' | 'sparql_query' | 'previous_results' | 'papers' | 'clarification'

export type ChatErrorKind =
  | 'llm_unavailable'
  | 'llm_no_content'
  | 'sparql_unavailable'
  | 'sparql_failed'
  | 'internal'

/**
 * One event of a chat turn (`POST /chat` answers with a stream of them):
 * `session` → (`step_started` → `step_finished`)* → `answer`+ → `done`. `error` ends the
 * stream instead of `done`.
 */
export type ChatEvent =
  | { event: 'session'; session_id: string; message_id: string; title: string | null }
  | { event: 'session_title'; session_id: string; title: string }
  | { event: 'step_started'; step_id: string; ordinal: number; kind: StepKind; args: Record<string, unknown> }
  | {
      event: 'step_finished'
      step_id: string
      ok: boolean
      count: number | null
      error: string | null
      duration_ms: number
    }
  | { event: 'thinking'; delta: string }
  | { event: 'answer'; delta: string }
  | { event: 'done'; message_id: string; row_count: number | null }
  | { event: 'error'; kind: ChatErrorKind; message: string }

export interface HistoryMessage {
  role: 'user' | 'assistant'
  content: string
  sparql_query: string | null
  sparql_results: string | null
  created_at: string | null
}

export interface HistoryResponse {
  session_id: string
  messages: HistoryMessage[]
}

export type ServiceStatus = 'ok' | 'degraded' | 'down'

export interface ServiceHealth {
  status: ServiceStatus
  error: string | null
  additional_attributes: Record<string, unknown>
}

export interface HealthResponse {
  status: ServiceStatus
  error: string | null
  services: Record<string, ServiceHealth>
}

export interface ErrorResponse {
  status: 'error'
  error: string
  detail: string | null
}
