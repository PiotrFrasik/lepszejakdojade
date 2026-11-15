import { defineStore } from 'pinia'
import { computed, reactive, ref, shallowRef, watch } from 'vue'

import { searchJourneys } from '@/api/client'
import { DEFAULT_TIME_ZONE } from '@/i18n/format'
import { useCityStore } from '@/stores/city'
import type { Itinerary, JourneyComparison, JourneyPlace, JourneySearchResponse } from '@/types/api'
import {
  buildJourneyRequest,
  validateForm,
  zonedLocalNow,
  type FormProblem,
  type JourneyFormValues,
  type PlaceValue,
  type PreferenceKey,
  type TimeChoice,
} from '@/utils/journey'

export type JourneyField = 'from' | 'to'
export type SearchStatus = 'idle' | 'loading' | 'ready' | 'error'
/** Why "my location" failed. */
export type LocationProblem = 'unsupported' | 'denied' | 'unavailable' | 'timeout'

function isAbortError(err: unknown): boolean {
  return (
    typeof err === 'object' && err !== null && (err as { name?: unknown }).name === 'AbortError'
  )
}

/**
 * Journey planner state: the form (from / to, time, preferences), the last search result and
 * the map interaction (picking a point, "my location"). Kept in a store so the form survives
 * navigating to a timetable and back. Everything is reset when the city changes.
 */
export const useJourneyStore = defineStore('journey', () => {
  const cityStore = useCityStore()

  const from = ref<PlaceValue | null>(null)
  const to = ref<PlaceValue | null>(null)
  const timeChoice = ref<TimeChoice>('now')
  const localTime = ref('')
  const preferences = reactive<Record<PreferenceKey, boolean>>({
    fewer_transfers: false,
    less_walking: false,
    wheelchair: false,
  })

  const status = ref<SearchStatus>('idle')
  const result = shallowRef<JourneySearchResponse | null>(null)
  const error = shallowRef<unknown>(null)
  /** Problem found before sending (shown next to the form); cleared when the form changes. */
  const problem = ref<FormProblem | null>(null)
  const selectedId = ref<string | null>(null)

  /** Field waiting for a click on the map, if any. */
  const picking = ref<JourneyField | null>(null)
  const locating = ref<JourneyField | null>(null)
  const locationProblem = ref<{ field: JourneyField; reason: LocationProblem } | null>(null)

  let controller: AbortController | null = null

  const timeZone = computed(() => cityStore.currentCityDetails?.timezone || DEFAULT_TIME_ZONE)

  const formValues = computed<JourneyFormValues>(() => ({
    from: from.value,
    to: to.value,
    timeChoice: timeChoice.value,
    localTime: localTime.value,
    preferences: { ...preferences },
  }))

  const selectedItinerary = computed<Itinerary | null>(() => {
    const list = result.value?.itineraries ?? []
    return list.find((item) => item.id === selectedId.value) ?? list[0] ?? null
  })

  const activePreferences = computed(() => Object.values(preferences).filter(Boolean).length)

  function setPlace(field: JourneyField, value: PlaceValue | null): void {
    if (field === 'from') from.value = value
    else to.value = value
    problem.value = null
    if (locationProblem.value?.field === field) locationProblem.value = null
    // Results (and the route on the map) belong to the old places.
    if (status.value !== 'idle') clearResults()
  }

  function swap(): void {
    const previousFrom = from.value
    from.value = to.value
    to.value = previousFrom
    problem.value = null
    if (status.value !== 'idle') clearResults()
  }

  function setTimeChoice(choice: TimeChoice): void {
    timeChoice.value = choice
    if (choice !== 'now' && !localTime.value) localTime.value = zonedLocalNow(timeZone.value)
    problem.value = null
  }

  function startPicking(field: JourneyField): void {
    picking.value = picking.value === field ? null : field
  }

  function cancelPicking(): void {
    picking.value = null
  }

  /** Sets the field being picked to the clicked map point. */
  function pickPoint(lat: number, lon: number): void {
    const field = picking.value
    if (!field) return
    setPlace(field, { source: 'map', name: null, lat, lon })
    picking.value = null
  }

  /** Fills the field with the device position (browser geolocation). */
  function useMyLocation(field: JourneyField): Promise<void> {
    locationProblem.value = null
    const geo = typeof navigator !== 'undefined' ? navigator.geolocation : undefined
    if (!geo) {
      locationProblem.value = { field, reason: 'unsupported' }
      return Promise.resolve()
    }
    locating.value = field
    return new Promise((resolve) => {
      geo.getCurrentPosition(
        (position) => {
          if (locating.value === field) locating.value = null
          setPlace(field, {
            source: 'location',
            name: null,
            lat: position.coords.latitude,
            lon: position.coords.longitude,
          })
          resolve()
        },
        (err) => {
          if (locating.value === field) locating.value = null
          const reason: LocationProblem =
            err.code === 1 ? 'denied' : err.code === 3 ? 'timeout' : 'unavailable'
          locationProblem.value = { field, reason }
          resolve()
        },
        { enableHighAccuracy: true, timeout: 15_000, maximumAge: 60_000 },
      )
    })
  }

  function setPreference(key: PreferenceKey, value: boolean): void {
    preferences[key] = value
  }

  function selectItinerary(id: string): void {
    selectedId.value = id
  }

  /** Validates the form and runs the search. Resolves when the request ends (or is replaced). */
  async function search(): Promise<void> {
    const city = cityStore.cityId
    const found = validateForm(formValues.value)
    problem.value = found
    if (found || !city) return
    const request = buildJourneyRequest(formValues.value, timeZone.value)
    if (!request) {
      problem.value = 'invalid_time'
      return
    }

    controller?.abort()
    const current = new AbortController()
    controller = current
    status.value = 'loading'
    error.value = null
    picking.value = null
    try {
      const response = await searchJourneys(city, request, current.signal)
      if (current.signal.aborted) return
      result.value = {
        ...response,
        itineraries: Array.isArray(response?.itineraries) ? response.itineraries : [],
      }
      selectedId.value = result.value.itineraries[0]?.id ?? null
      status.value = 'ready'
    } catch (err) {
      if (current.signal.aborted || isAbortError(err)) return
      error.value = err
      result.value = null
      status.value = 'error'
    } finally {
      if (controller === current) controller = null
    }
  }

  /** Drops the results (back to the "Your journeys" panel); the form is kept. */
  function clearResults(): void {
    controller?.abort()
    controller = null
    status.value = 'idle'
    result.value = null
    error.value = null
    selectedId.value = null
  }

  /**
   * Shows a ready-made connection (e.g. from an assistant card) as the search result, with its
   * end points filled into the form as named points.
   */
  function showItinerary(
    fromPlace: JourneyPlace,
    toPlace: JourneyPlace,
    itinerary: Itinerary,
    comparison: JourneyComparison,
  ): void {
    controller?.abort()
    controller = null
    from.value = { source: 'map', name: fromPlace.name, lat: fromPlace.lat, lon: fromPlace.lon }
    to.value = { source: 'map', name: toPlace.name, lat: toPlace.lat, lon: toPlace.lon }
    problem.value = null
    picking.value = null
    error.value = null
    result.value = { from: fromPlace, to: toPlace, itineraries: [itinerary], comparison }
    selectedId.value = itinerary.id
    status.value = 'ready'
  }

  /** Clears everything (used when the city changes: stops and points belong to one city). */
  function reset(): void {
    clearResults()
    from.value = null
    to.value = null
    problem.value = null
    picking.value = null
    locating.value = null
    locationProblem.value = null
  }

  watch(
    () => cityStore.cityId,
    (next, previous) => {
      if (previous !== null && next !== previous) reset()
    },
  )

  return {
    from,
    to,
    timeChoice,
    localTime,
    preferences,
    status,
    result,
    error,
    problem,
    selectedId,
    selectedItinerary,
    activePreferences,
    picking,
    locating,
    locationProblem,
    timeZone,
    setPlace,
    swap,
    setTimeChoice,
    startPicking,
    cancelPicking,
    pickPoint,
    useMyLocation,
    setPreference,
    selectItinerary,
    search,
    clearResults,
    showItinerary,
    reset,
  }
})
