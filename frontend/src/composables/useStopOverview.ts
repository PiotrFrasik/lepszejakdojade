import { getStopOverview } from '@/api/client'
import { useApiResource } from '@/composables/useApiResource'
import type { CityId, StopId, StopOverview } from '@/types/api'

/** Same dev-only switch as the departures board (`VITE_DEPARTURES_MOCK=true`). */
const useMock = import.meta.env.DEV && import.meta.env.VITE_DEPARTURES_MOCK === 'true'

async function fetchOverview(
  city: CityId,
  stop: StopId,
  signal: AbortSignal,
): Promise<StopOverview> {
  if (useMock) {
    const { mockGetStopOverview } = await import('@/api/departuresMock')
    return mockGetStopOverview(city, stop, signal)
  }
  return getStopOverview(city, stop, signal)
}

export interface StopOverviewKey {
  city: CityId
  stop: StopId
}

/** Stop group and the lines serving it (`GET /cities/{city}/stops/{stop_id}/`), no auto-refresh. */
export function useStopOverview(key: () => StopOverviewKey | null) {
  return useApiResource(key, (current, signal) => fetchOverview(current.city, current.stop, signal))
}
