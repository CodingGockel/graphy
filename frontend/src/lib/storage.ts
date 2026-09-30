// localStorage can be unavailable or throw (private mode, blocked site data),
// so every access is guarded and falls back silently.

export function readString(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

export function writeString(key: string, value: string): void {
  try {
    localStorage.setItem(key, value)
  } catch {
    // ignore: persistence is best effort
  }
}

export function removeKey(key: string): void {
  try {
    localStorage.removeItem(key)
  } catch {
    // ignore: persistence is best effort
  }
}

export function readJSON<T>(key: string, fallback: T): T {
  const raw = readString(key)
  if (raw === null) return fallback
  try {
    return JSON.parse(raw) as T
  } catch {
    return fallback
  }
}

export function writeJSON(key: string, value: unknown): void {
  writeString(key, JSON.stringify(value))
}
