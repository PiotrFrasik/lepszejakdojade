import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter, type LocationQuery, type RouteLocationRaw } from 'vue-router'

import { useFormat } from '@/composables/useFormat'
import { useCityStore } from '@/stores/city'
import type { DirectionId, LineId, ServiceDate, StopId } from '@/types/api'
import { parseDate, parseDirection, zonedNow } from '@/utils/serviceDate'

/** Current time, refreshed every 30 s while the component is mounted. */
export function useNow(intervalMs = 30_000) {
  const now = ref(new Date())
  let timer: ReturnType<typeof setInterval> | null = null
  onMounted(() => {
    timer = setInterval(() => {
      now.value = new Date()
    }, intervalMs)
  })
  onBeforeUnmount(() => {
    if (timer !== null) clearInterval(timer)
  })
  return now
}

function param(value: string | string[] | undefined): string {
  return (Array.isArray(value) ? value[0] : value) ?? ''
}

/**
 * Route state shared by the line and stop timetable pages: `lineId` / `stopId` path params,
 * `direction` and `date` from the query (shareable URLs), the city's "today" and link builders.
 * When the user switches city, line and stop ids of the old city are meaningless, so the page
 * goes back to the timetable start.
 */
export function useTimetableRoute() {
  const route = useRoute()
  const router = useRouter()
  const cityStore = useCityStore()
  const fmt = useFormat()
  const now = useNow()

  const lineId = computed<LineId>(() => param(route.params.lineId))
  const stopId = computed<StopId>(() => param(route.params.stopId))
  const direction = computed<DirectionId>(() => parseDirection(route.query.direction))
  /** Date from the URL, or `null` (= today, the API default). */
  const queryDate = computed<ServiceDate | null>(() => parseDate(route.query.date))

  const zoned = computed(() => zonedNow(fmt.timeZone.value, now.value))
  const today = computed<ServiceDate>(() => zoned.value.date)
  /** Minutes since midnight now, in the city time zone. */
  const nowMinutes = computed<number>(() => zoned.value.minutes)
  const date = computed<ServiceDate>(() => queryDate.value ?? today.value)

  function query(dir: DirectionId, day: ServiceDate | null): LocationQuery {
    const out: LocationQuery = {}
    if (dir !== 0) out.direction = String(dir)
    if (day) out.date = day
    return out
  }

  /** `extra` adds query values, e.g. a one-off `notice` for the line page. */
  function lineLink(
    id: LineId = lineId.value,
    dir: DirectionId = direction.value,
    extra: LocationQuery = {},
  ): RouteLocationRaw {
    return {
      name: 'timetable-line',
      params: { lineId: id },
      query: { ...query(dir, queryDate.value), ...extra },
    }
  }

  function stopLink(
    id: StopId,
    dir: DirectionId = direction.value,
    line: LineId = lineId.value,
  ): RouteLocationRaw {
    return {
      name: 'timetable-stop',
      params: { lineId: line, stopId: id },
      query: query(dir, queryDate.value),
    }
  }

  function setDate(value: ServiceDate): void {
    void router.replace({
      query: { ...route.query, date: value === today.value ? undefined : value },
    })
  }

  function setDirection(value: DirectionId): void {
    void router.replace({ query: { ...route.query, direction: value === 0 ? undefined : '1' } })
  }

  watch(
    () => cityStore.cityId,
    (next, previous) => {
      if (previous && next && next !== previous) void router.push({ name: 'timetable' })
    },
  )

  return {
    cityId: computed(() => cityStore.cityId),
    lineId,
    stopId,
    direction,
    queryDate,
    date,
    today,
    nowMinutes,
    lineLink,
    stopLink,
    setDate,
    setDirection,
  }
}
