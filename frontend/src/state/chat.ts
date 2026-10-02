import { ref } from 'vue'
import { api, ApiError, isAbortError, toApiError } from '../api/client'
import type { MessageOut, SessionDetail } from '../api/types'
import { errorFromEvent } from '../lib/errors'
import { activeId, makeTitle, removeSession, touchSession } from './sessions'

export interface ChatEntry {
  id: number
  role: 'user' | 'assistant'
  content: string
}

export interface ChatFailure {
  error: ApiError
  /** Null if the session no longer exists: only a new session helps then, not a retry. */
  retry: (() => void) | null
}

export const messages = ref<ChatEntry[]>([])
export const pending = ref(false)
export const loadingHistory = ref(false)
export const aborted = ref(false)
export const chatError = ref<ChatFailure | null>(null)

let nextId = 0
let controller: AbortController | null = null
// Bumped whenever the view changes; responses from an older token are dropped.
let requestToken = 0

function entry(role: ChatEntry['role'], content: string): ChatEntry {
  return { id: nextId++, role, content }
}

function reset(): void {
  controller?.abort()
  controller = null
  requestToken++
  pending.value = false
  loadingHistory.value = false
  aborted.value = false
  chatError.value = null
}

/**
 * The stored messages that are shown. A turn that failed without any answer text is left
 * out as a pair: after "retry" its question would otherwise appear twice. An answer
 * without text (aborted before it started, or still running) is no bubble; its question
 * stays.
 */
function visibleMessages(history: MessageOut[]): MessageOut[] {
  const failedTurns = new Set(
    history.filter((m) => m.role === 'assistant' && m.status === 'error' && !m.content).map((m) => m.turn),
  )
  return history.filter((m) => !failedTurns.has(m.turn) && (m.role === 'user' || m.content !== ''))
}

/** The backend no longer knows this session: forget it and offer a new one. */
function sessionGone(id: string, error: ApiError): void {
  removeSession(id)
  if (activeId.value === id) activeId.value = null
  chatError.value = { error, retry: null }
}

function showSession(session: SessionDetail): void {
  activeId.value = session.id
  messages.value = visibleMessages(session.messages).map((m) => entry(m.role, m.content))
}

export function newSession(): void {
  reset()
  activeId.value = null
  messages.value = []
}

export async function openSession(id: string): Promise<void> {
  reset()
  activeId.value = id
  messages.value = []
  loadingHistory.value = true
  const token = requestToken
  try {
    const session = await api.getSession(id)
    if (token === requestToken) showSession(session)
  } catch (err) {
    if (token !== requestToken) return
    const error = toApiError(err)
    if (error.status === 404) sessionGone(id, error)
    else chatError.value = { error, retry: () => void openSession(id) }
  } finally {
    if (token === requestToken) loadingHistory.value = false
  }
}

/** Adds an existing backend session by ID and opens it. Throws `ApiError` (404 if unknown). */
export async function importSession(id: string): Promise<void> {
  const session = await api.getSession(id)
  const firstQuestion = session.messages.find((m) => m.role === 'user')
  touchSession(id, session.title ?? (firstQuestion ? makeTitle(firstQuestion.content) : id.slice(0, 8)))
  reset()
  showSession(session)
}

export async function deleteSession(id: string): Promise<void> {
  try {
    await api.deleteSession(id)
  } catch (err) {
    // Already gone on the backend: still drop it from the list.
    if (!(err instanceof ApiError && err.status === 404)) throw err
  }
  removeSession(id)
  if (activeId.value === id) newSession()
}

export async function send(text: string): Promise<void> {
  const message = text.trim()
  if (!message || pending.value || loadingHistory.value) return

  aborted.value = false
  // The history still shown belongs to a session that is gone; the new one starts empty.
  if (chatError.value && !chatError.value.retry) messages.value = []
  chatError.value = null
  const question = entry('user', message)
  messages.value.push(question)
  pending.value = true
  controller = new AbortController()
  const token = ++requestToken
  const sessionId = activeId.value
  // What the stream has produced so far.
  const turn: { started: boolean; answer: ChatEntry | null; failure: ApiError | null } = {
    started: false,
    answer: null,
    failure: null,
  }

  try {
    await api.chat(
      message,
      sessionId,
      (event) => {
        if (token !== requestToken) return
        switch (event.event) {
          case 'session':
            turn.started = true
            touchSession(event.session_id, makeTitle(message))
            activeId.value = event.session_id
            break
          case 'answer':
            if (!turn.answer) {
              messages.value.push(entry('assistant', ''))
              // The reactive entry, so appending to it updates the view.
              turn.answer = messages.value[messages.value.length - 1]
            }
            turn.answer.content += event.delta
            break
          case 'error':
            turn.failure = errorFromEvent(event.kind, event.message)
            break
          // `done` ends the stream; steps, reasoning and titles are not shown yet.
        }
      },
      controller.signal,
    )
    if (turn.failure) throw turn.failure
  } catch (err) {
    if (token !== requestToken) return
    if (isAbortError(err)) {
      // A partial answer stays visible.
      aborted.value = true
      // Stopped before the new session was announced: its ID is unknown, so the question
      // cannot be part of what follows.
      if (!sessionId && !turn.started) messages.value = messages.value.filter((m) => m.id !== question.id)
    } else {
      const error = toApiError(err)
      // Drop the unanswered question (and a partial answer); "retry" sends it again.
      const dropped = [question.id, turn.answer?.id]
      messages.value = messages.value.filter((m) => !dropped.includes(m.id))
      if (error.status === 404 && sessionId) sessionGone(sessionId, error)
      else chatError.value = { error, retry: () => void send(message) }
    }
  } finally {
    if (token === requestToken) {
      pending.value = false
      controller = null
    }
  }
}

export function stop(): void {
  controller?.abort()
}
