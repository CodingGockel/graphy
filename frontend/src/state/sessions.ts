import { computed, ref, watch } from 'vue'
import { readJSON, readString, removeKey, writeJSON, writeString } from '../lib/storage'

// The backend has no endpoint to list sessions yet, so the list lives in the browser.
// Once it does, this module is the one place to switch over.

export interface SessionEntry {
  id: string
  title: string
  updatedAt: number
}

const LIST_KEY = 'graphy.sessions'
const ACTIVE_KEY = 'graphy.activeSession'

export const sessions = ref<SessionEntry[]>(loadSessions())
export const activeId = ref<string | null>(readString(ACTIVE_KEY))

export const sortedSessions = computed(() =>
  [...sessions.value].sort((a, b) => b.updatedAt - a.updatedAt),
)

watch(sessions, (list) => writeJSON(LIST_KEY, list), { deep: true })
watch(activeId, (id) => (id ? writeString(ACTIVE_KEY, id) : removeKey(ACTIVE_KEY)))

function loadSessions(): SessionEntry[] {
  const raw = readJSON<unknown>(LIST_KEY, [])
  if (!Array.isArray(raw)) return []
  return raw.filter(
    (s): s is SessionEntry =>
      typeof s?.id === 'string' && typeof s?.title === 'string' && typeof s?.updatedAt === 'number',
  )
}

/** Adds the session if it is unknown (with `title`), otherwise marks it as recently used. */
export function touchSession(id: string, title: string): void {
  const existing = sessions.value.find((s) => s.id === id)
  if (existing) existing.updatedAt = Date.now()
  else sessions.value.push({ id, title, updatedAt: Date.now() })
}

export function renameSession(id: string, title: string): void {
  const session = sessions.value.find((s) => s.id === id)
  if (session) session.title = title
}

export function removeSession(id: string): void {
  sessions.value = sessions.value.filter((s) => s.id !== id)
}

/** Shortens a question to a one-line title, cut at a word boundary. */
export function makeTitle(text: string, max = 50): string {
  const clean = text.replace(/\s+/g, ' ').trim()
  if (clean.length <= max) return clean
  const cut = clean.slice(0, max)
  const space = cut.lastIndexOf(' ')
  return `${(space > max / 2 ? cut.slice(0, space) : cut).trimEnd()}…`
}
