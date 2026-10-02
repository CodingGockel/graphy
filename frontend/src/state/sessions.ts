import { computed, ref, watch } from 'vue'
import { api, MAX_SESSION_IDS } from '../api/client'
import { readJSON, readString, removeKey, writeJSON, writeString } from '../lib/storage'

// Which sessions belong to this browser lives in localStorage: the backend has no
// authentication, so a list of all sessions would show every visitor every chat. It only
// serves titles and metadata for the IDs we already know (see refreshSessions).

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

/** Sets the title of the local entry only. */
export function setTitle(id: string, title: string): void {
  const session = sessions.value.find((s) => s.id === id)
  if (session) session.title = title
}

/** Renames the session on the backend, then locally. Throws `ApiError`. */
export async function renameSession(id: string, title: string): Promise<void> {
  const summary = await api.renameSession(id, title)
  setTitle(id, summary.title ?? title)
}

/**
 * Brings the stored list in line with the backend: titles and `updatedAt` are taken over,
 * sessions the backend no longer knows are dropped. If the backend cannot be reached, the
 * list stays as it is.
 */
export async function refreshSessions(): Promise<void> {
  const ids = sessions.value.map((s) => s.id)
  const known = new Map<string, { title: string | null; updatedAt: number }>()
  try {
    for (let i = 0; i < ids.length; i += MAX_SESSION_IDS) {
      for (const summary of await api.getSessions(ids.slice(i, i + MAX_SESSION_IDS))) {
        known.set(summary.id, { title: summary.title, updatedAt: Date.parse(summary.updated_at) })
      }
    }
  } catch {
    return
  }

  const asked = new Set(ids)
  // Sessions added while the request was running were not asked for: keep them.
  sessions.value = sessions.value.filter((s) => known.has(s.id) || !asked.has(s.id))
  for (const session of sessions.value) {
    const remote = known.get(session.id)
    if (!remote) continue
    // Without a backend title the local one (the shortened first question) stays.
    if (remote.title) session.title = remote.title
    if (!Number.isNaN(remote.updatedAt)) session.updatedAt = remote.updatedAt
  }
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
