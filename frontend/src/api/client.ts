import type {
  ChatEvent,
  ChatRequest,
  ErrorResponse,
  HealthResponse,
  SessionDetail,
  SessionSummary,
  StepResult,
} from './types'

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

/** One SSE frame (the text between two blank lines) as an event; null for a comment-only frame. */
function parseFrame(frame: string): ChatEvent | null {
  let name = ''
  const data: string[] = []
  for (const line of frame.split('\n')) {
    if (line.startsWith(':')) continue // comment, e.g. the `: ping` heartbeat
    if (line.startsWith('event:')) name = line.slice(6).trim()
    else if (line.startsWith('data:')) data.push(line.slice(5).replace(/^ /, ''))
  }
  if (!name) return null
  try {
    return { event: name, ...JSON.parse(data.join('\n')) } as ChatEvent
  } catch {
    throw new ApiError(-1, 'Invalid event from the backend')
  }
}

/** Reads an SSE body and calls `onEvent` per event. Frames may be split across chunks. */
async function readEvents(response: Response, onEvent: (event: ChatEvent) => void): Promise<void> {
  if (!response.body) throw new ApiError(-1, 'Empty response')
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let finished = false

  for (;;) {
    let chunk: ReadableStreamReadResult<Uint8Array>
    try {
      chunk = await reader.read()
    } catch (err) {
      if (isAbortError(err)) throw err
      throw new ApiError(0, 'Network error')
    }
    if (chunk.done) break
    buffer = (buffer + decoder.decode(chunk.value, { stream: true })).replace(/\r\n/g, '\n')

    let end: number
    while ((end = buffer.indexOf('\n\n')) !== -1) {
      const event = parseFrame(buffer.slice(0, end))
      buffer = buffer.slice(end + 2)
      if (!event) continue
      if (event.event === 'done' || event.event === 'error') finished = true
      onEvent(event)
    }
  }

  if (!finished) throw new ApiError(-1, 'The answer stream ended unexpectedly')
}

const sessionPath = (id: string) => `/sessions/${encodeURIComponent(id)}`

/** The most IDs the backend accepts in one `getSessions` call. */
export const MAX_SESSION_IDS = 100

export const api = {
  /**
   * Sends a message and reports the turn's events as they arrive. Resolves once the stream
   * has ended with `done` or `error`; an HTTP error (e.g. 404 for an unknown session) or a
   * stream that just stops rejects with `ApiError`.
   */
  async chat(
    message: string,
    sessionId: string | null,
    onEvent: (event: ChatEvent) => void,
    signal?: AbortSignal,
  ): Promise<void> {
    const body: ChatRequest = { message, session_id: sessionId }
    let response: Response
    try {
      // fetch + ReadableStream: EventSource cannot POST.
      response = await fetch(`${BASE_URL}/chat`, {
        method: 'POST',
        headers: { Accept: 'text/event-stream', 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal,
      })
    } catch (err) {
      if (isAbortError(err)) throw err
      throw new ApiError(0, 'Network error')
    }
    if (!response.ok) throw await errorFromResponse(response)
    await readEvents(response, onEvent)
  },

  /** Metadata of the given sessions (at most `MAX_SESSION_IDS`). Unknown IDs are left out. */
  getSessions(ids: string[], signal?: AbortSignal): Promise<SessionSummary[]> {
    return request<SessionSummary[]>(`/sessions?ids=${ids.map(encodeURIComponent).join(',')}`, { signal })
  },

  getSession(sessionId: string, signal?: AbortSignal): Promise<SessionDetail> {
    return request<SessionDetail>(sessionPath(sessionId), { signal })
  },

  renameSession(sessionId: string, title: string): Promise<SessionSummary> {
    return request<SessionSummary>(sessionPath(sessionId), { method: 'PATCH', body: { title } })
  },

  deleteSession(sessionId: string): Promise<void> {
    return request<void>(sessionPath(sessionId), { method: 'DELETE' })
  },

  /** Loaded on demand: results are neither part of the chat stream nor of the history. */
  getStepResult(stepId: string, signal?: AbortSignal): Promise<StepResult> {
    return request<StepResult>(`/steps/${encodeURIComponent(stepId)}/result`, { signal })
  },

  /** The backend answers 503 when a service is degraded or down, with the same body. */
  getHealth(signal?: AbortSignal): Promise<HealthResponse> {
    return request<HealthResponse>('/health', { signal, acceptStatus: [503] })
  },
}
