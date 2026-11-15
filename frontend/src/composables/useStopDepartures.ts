import { computed, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'

import { getStopDepartures } from '@/api/client'
import type { ResourceStatus } from '@/composables/useApiResource'
import type { CityId, StopDepartures, StopId } from '@/types/api'

/** Board refresh period while the page is visible. */
export const DEPARTURES_REFRESH_MS = 30_000
/** How often countdowns ("in 5 min") are recomputed between refreshes. */
const CLOCK_TICK_MS = 10_000
/** Live times older than this (no successful refresh since) are no longer shown as live. */
export const LIVE_STALE_AFTER_MS = 5 * 60_000

const useMock = import.meta.env.DEV && import.meta.env.VITE_DEPARTURES_MOCK === 'true'

async function fetchDepartures(
  city: CityId,
  stop: StopId,
  limit: number | undefined,
  signal: AbortSignal,
): Promise<StopDepartures> {
  if (useMock) {
    const { mockGetStopDepartures } = await import('@/api/departuresMock')
    return mockGetStopDepartures(city, stop, { limit }, signal)
  }
  return getStopDepartures(city, stop, { limit }, signal)
}

function isAbortError(err: unknown): boolean {
  return (
    typeof err === 'object' && err !== null && (err as { name?: unknown }).name === 'AbortError'
  )
}

function isHidden(): boolean {
  return typeof document !== 'undefined' && document.visibilityState === 'hidden'
}

export interface DeparturesKey {
  city: CityId
  stop: StopId
}

/**
 * Departures board of one stop with auto-refresh.
 *
 * - Refreshes every `DEPARTURES_REFRESH_MS` after the previous request finished, only while the
 *   document is visible; becoming visible again refreshes at once.
 * - A new request (refresh, key change, manual reload) aborts the one in flight.
 * - A failed refresh keeps the last board and sets `refreshError`; only a failed first load
 *   (no board yet) sets `status = 'error'`, and that does not retry by itself.
 * - `nowMs` estimates the server's current time from `generated_at`, so countdowns do not
 *   depend on the device clock being right.
 * - `stale` is true once the last successful response is older than `LIVE_STALE_AFTER_MS`
 *   (refreshes keep failing, or a long-hidden tab is reloading); live times must then not be shown.
 */
export function useStopDepartures(
  key: () => DeparturesKey | null,
  options: { limit?: number; intervalMs?: number } = {},
) {
  const intervalMs = options.intervalMs ?? DEPARTURES_REFRESH_MS
  const data = shallowRef<StopDepartures | null>(null)
  const status = ref<ResourceStatus>('idle')
  const error = shallowRef<unknown>(null)
  const refreshError = shallowRef<unknown>(null)
  const refreshing = ref(false)
  /** Device time when `data` arrived. */
  const receivedAt = ref<number | null>(null)
  const clock = ref(Date.now())

  let controller: AbortController | null = null
  let refreshTimer: ReturnType<typeof setTimeout> | null = null
  let clockTimer: ReturnType<typeof setInterval> | null = null

  function clearRefreshTimer(): void {
    if (refreshTimer !== null) clearTimeout(refreshTimer)
    refreshTimer = null
  }

  function scheduleRefresh(): void {
    clearRefreshTimer()
    if (isHidden() || data.value === null || key() === null) return
    refreshTimer = setTimeout(() => {
      refreshTimer = null
      void load()
    }, intervalMs)
  }

  async function load(): Promise<void> {
    clearRefreshTimer()
    controller?.abort()
    controller = null
    const current = key()
    if (current === null) {
      data.value = null
      error.value = null
      refreshError.value = null
      refreshing.value = false
      status.value = 'idle'
      return
    }
    const own = new AbortController()
    controller = own
    if (data.value) {
      refreshing.value = true
    } else {
      status.value = 'loading'
      error.value = null
    }
    try {
      const result = await fetchDepartures(current.city, current.stop, options.limit, own.signal)
      if (own.signal.aborted) return
      data.value = result
      receivedAt.value = Date.now()
      clock.value = receivedAt.value
      error.value = null
      refreshError.value = null
      status.value = 'ready'
    } catch (err) {
      if (own.signal.aborted || isAbortError(err)) return
      if (data.value) {
        refreshError.value = err
      } else {
        error.value = err
        status.value = 'error'
      }
    } finally {
      if (controller === own) {
        controller = null
        refreshing.value = false
        scheduleRefresh()
      }
    }
  }

  function onVisibilityChange(): void {
    if (isHidden()) {
      clearRefreshTimer()
    } else {
      // The clock may not have ticked while hidden: staleness must be right before the reload.
      clock.value = Date.now()
    }
    if (!isHidden() && key() !== null && status.value !== 'error') {
      void load()
    }
  }

  watch(
    () => {
      const current = key()
      return current === null ? null : JSON.stringify(current)
    },
    () => {
      data.value = null
      receivedAt.value = null
      refreshError.value = null
      void load()
    },
    { immediate: true },
  )

  onMounted(() => {
    document.addEventListener('visibilitychange', onVisibilityChange)
    clockTimer = setInterval(() => {
      clock.value = Date.now()
    }, CLOCK_TICK_MS)
  })

  onBeforeUnmount(() => {
    document.removeEventListener('visibilitychange', onVisibilityChange)
    if (clockTimer !== null) clearInterval(clockTimer)
    clearRefreshTimer()
    controller?.abort()
    controller = null
  })

  const nowMs = computed<number>(() => {
    const generated = data.value ? Date.parse(data.value.generated_at) : Number.NaN
    if (receivedAt.value === null || Number.isNaN(generated)) return clock.value
    return generated + Math.max(0, clock.value - receivedAt.value)
  })

  const stale = computed<boolean>(
    () => receivedAt.value !== null && clock.value - receivedAt.value > LIVE_STALE_AFTER_MS,
  )

  return { data, status, error, refreshError, refreshing, nowMs, stale, reload: () => void load() }
}
