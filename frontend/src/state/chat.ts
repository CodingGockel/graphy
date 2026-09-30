import { ref } from 'vue'
import { api, ApiError, isAbortError, toApiError } from '../api/client'
import type { HistoryResponse } from '../api/types'
import { activeId, makeTitle, removeSession, touchSession } from './sessions'

export interface ChatEntry {
  id: number
  role: 'user' | 'assistant'
  content: string
}

export interface ChatFailure {
  error: ApiError
  retry: () => void
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

function showHistory(id: string, history: HistoryResponse): void {
  activeId.value = id
  messages.value = history.messages.map((m) => entry(m.role, m.content))
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
    const history = await api.getHistory(id)
    if (token === requestToken) showHistory(id, history)
  } catch (err) {
    if (token === requestToken) chatError.value = { error: toApiError(err), retry: () => void openSession(id) }
  } finally {
    if (token === requestToken) loadingHistory.value = false
  }
}

/** Adds an existing backend session by ID and opens it. Throws `ApiError` (404 if unknown). */
export async function importSession(id: string): Promise<void> {
  const history = await api.getHistory(id)
  const firstQuestion = history.messages.find((m) => m.role === 'user')
  touchSession(id, firstQuestion ? makeTitle(firstQuestion.content) : id.slice(0, 8))
  reset()
  showHistory(id, history)
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
  chatError.value = null
  const question = entry('user', message)
  messages.value.push(question)
  pending.value = true
  controller = new AbortController()
  const token = ++requestToken

  try {
    const response = await api.chat(message, activeId.value, controller.signal)
    if (token !== requestToken) return
    touchSession(response.session_id, makeTitle(message))
    activeId.value = response.session_id
    messages.value.push(entry('assistant', response.answer))
  } catch (err) {
    if (token !== requestToken) return
    if (isAbortError(err)) {
      aborted.value = true
    } else {
      // Drop the unanswered question; "retry" sends it again.
      messages.value = messages.value.filter((m) => m.id !== question.id)
      chatError.value = { error: toApiError(err), retry: () => void send(message) }
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
