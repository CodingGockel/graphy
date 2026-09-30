// Mirrors the backend schemas in backend/src/models/schemas.py.

export interface ChatRequest {
  message: string
  session_id: string | null
}

export interface ChatResponse {
  answer: string
  session_id: string
  llm_generated_query: string
  sparql_query_result: string | null
}

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
