import type { ChatRequest, ChatResponse, ErrorResponse, HealthResponse, HistoryResponse } from './types'

const BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '/api/v1').replace(/\/$/, '')

/**
 * An error talking to the backend.
 * `status` is the HTTP status, 0 if the backend was unreachable, -1 for anything unexpected.
 */
export class ApiError extends Error {
  readonly status: number
  readonly detail: string | null

  constructor(status: number, message: string, detail: string | null = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

export function isAbortError(err: unknown): boolean {
  return err instanceof DOMException && err.name === 'AbortError'
}

export function toApiError(err: unknown): ApiError {
  if (err instanceof ApiError) return err
  return new ApiError(-1, err instanceof Error ? err.message : String(err))
}

interface RequestOptions {
  method?: string
  body?: unknown
  signal?: AbortSignal
  /** Non-2xx statuses whose body is still a regular response (e.g. 503 from /health). */
  acceptStatus?: number[]
}

async function request<T>(
  path: string,
  { method = 'GET', body, signal, acceptStatus = [] }: RequestOptions = {},
): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (body !== undefined) headers['Content-Type'] = 'application/json'

  let response: Response
  try {
    response = await fetch(BASE_URL + path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    })
  } catch (err) {
    if (isAbortError(err)) throw err
    throw new ApiError(0, 'Network error')
  }

  if (!response.ok && !acceptStatus.includes(response.status)) throw await errorFromResponse(response)
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

async function errorFromResponse(response: Response): Promise<ApiError> {
  const fallback = response.statusText || `HTTP ${response.status}`
  try {
    const body = (await response.json()) as Partial<ErrorResponse>
    return new ApiError(response.status, body.error ?? fallback, body.detail ?? null)
  } catch {
    return new ApiError(response.status, fallback)
  }
}

const sessionPath = (id: string) => `/session/${encodeURIComponent(id)}`

export const api = {
  chat(message: string, sessionId: string | null, signal?: AbortSignal): Promise<ChatResponse> {
    const body: ChatRequest = { message, session_id: sessionId }
    return request<ChatResponse>('/chat', { method: 'POST', body, signal })
  },

  getHistory(sessionId: string, signal?: AbortSignal): Promise<HistoryResponse> {
    return request<HistoryResponse>(`${sessionPath(sessionId)}/history`, { signal })
  },

  deleteSession(sessionId: string): Promise<void> {
    return request<void>(sessionPath(sessionId), { method: 'DELETE' })
  },

  /** The backend answers 503 when a service is degraded or down, with the same body. */
  getHealth(signal?: AbortSignal): Promise<HealthResponse> {
    return request<HealthResponse>('/health', { signal, acceptStatus: [503] })
  },
}
