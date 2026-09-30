import { computed, ref } from 'vue'
import { api, isAbortError, toApiError, type ApiError } from '../api/client'
import type { HealthResponse, ServiceStatus } from '../api/types'

const POLL_INTERVAL_MS = 60_000
// Refocusing the tab re-checks, but not more often than this (health pings the LLM API).
const MIN_REFRESH_GAP_MS = 15_000

export type OverallStatus = ServiceStatus | 'unknown'

export const health = ref<HealthResponse | null>(null)
/** Set when the backend itself could not be reached or answered with an error. */
export const healthError = ref<ApiError | null>(null)
export const checking = ref(false)
export const checkedAt = ref<number | null>(null)

export const backendStatus = computed<OverallStatus>(() =>
  healthError.value ? 'down' : health.value ? 'ok' : 'unknown',
)

export const overallStatus = computed<OverallStatus>(() =>
  healthError.value ? 'down' : (health.value?.status ?? 'unknown'),
)

/** Locale key for a one-line summary of the overall status. */
export const statusSummaryKey = computed(() =>
  healthError.value ? 'status.unreachable' : `status.summary_${overallStatus.value}`,
)

let controller: AbortController | null = null

export async function refreshHealth(): Promise<void> {
  controller?.abort()
  const own = new AbortController()
  controller = own
  checking.value = true
  try {
    health.value = await api.getHealth(own.signal)
    healthError.value = null
  } catch (err) {
    if (isAbortError(err)) return
    health.value = null
    healthError.value = toApiError(err)
  } finally {
    // A newer check took over; leave the state to it.
    if (controller === own) {
      controller = null
      checking.value = false
      checkedAt.value = Date.now()
    }
  }
}

/** Checks now, then periodically while the tab is visible. Returns a stop function. */
export function startHealthPolling(): () => void {
  void refreshHealth()

  const refreshIfVisible = () => {
    if (document.visibilityState !== 'visible') return
    if (checkedAt.value && Date.now() - checkedAt.value < MIN_REFRESH_GAP_MS) return
    void refreshHealth()
  }

  const timer = window.setInterval(refreshIfVisible, POLL_INTERVAL_MS)
  document.addEventListener('visibilitychange', refreshIfVisible)

  return () => {
    window.clearInterval(timer)
    document.removeEventListener('visibilitychange', refreshIfVisible)
    controller?.abort()
  }
}
