import { defineStore } from 'pinia'
import { computed, ref, shallowRef, watch } from 'vue'

import { ApiError, getCities, getCity } from '@/api/client'
import { findCity, type City, type CityDetail, type CityId } from '@/config/cities'
import { i18n } from '@/i18n'
import { STORAGE_KEYS, readStorage, removeStorage, writeStorage } from '@/utils/storage'

export type LoadStatus = 'idle' | 'loading' | 'ready' | 'error'

function isAbortError(err: unknown): boolean {
  return (
    typeof err === 'object' && err !== null && (err as { name?: unknown }).name === 'AbortError'
  )
}

/**
 * Cities and the selected city.
 *
 * The list comes from `GET /api/v1/cities/` and the selected city's settings from
 * `GET /api/v1/cities/{city}/`; both are re-fetched when the UI language changes so translated
 * names follow the language switcher. The selected city id is remembered in the browser; if it
 * is not in the loaded list any more, it is forgotten and the city picker is shown again.
 * `App.vue` calls `init()` (idempotent) to start loading.
 */
export const useCityStore = defineStore('city', () => {
  const cityId = ref<CityId | null>(readStorage(STORAGE_KEYS.city) || null)

  const cities = shallowRef<readonly City[]>([])
  const listStatus = ref<LoadStatus>('idle')
  const listError = shallowRef<unknown>(null)

  // Known limitation: `detailsStatus` / `detailsError` are not surfaced in the UI yet; no screen
  // uses the city details so far. Show them once one does (timetable, live data).
  const details = shallowRef<CityDetail | null>(null)
  const detailsStatus = ref<LoadStatus>('idle')
  const detailsError = shallowRef<unknown>(null)

  let listController: AbortController | null = null
  let detailsController: AbortController | null = null

  const currentCity = computed<City | null>(() => findCity(cities.value, cityId.value) ?? null)
  const hasCity = computed(() => currentCity.value !== null)
  /** Settings of the selected city, once loaded. */
  const currentCityDetails = computed<CityDetail | null>(() =>
    details.value && details.value.id === cityId.value ? details.value : null,
  )

  /**
   * Whether the city picker must be shown: there is no usable city. While a remembered city is
   * still being verified against the first list load, the picker is not shown (no flash for
   * returning users); if that load fails, the picker shows the error with a retry button.
   */
  const needsPicker = computed<boolean>(() => {
    if (currentCity.value) return false
    const verifying = cityId.value !== null && listError.value === null
    return !(verifying && listStatus.value !== 'ready')
  })

  async function loadDetails(id: CityId): Promise<void> {
    detailsController?.abort()
    const controller = new AbortController()
    detailsController = controller
    detailsStatus.value = 'loading'
    try {
      const result = await getCity(id, controller.signal)
      if (controller.signal.aborted) return
      details.value = result
      detailsError.value = null
      detailsStatus.value = 'ready'
    } catch (err) {
      if (controller.signal.aborted || isAbortError(err)) return
      detailsError.value = err
      detailsStatus.value = 'error'
    } finally {
      if (detailsController === controller) detailsController = null
    }
  }

  async function loadCities(): Promise<void> {
    listController?.abort()
    const controller = new AbortController()
    listController = controller
    listStatus.value = 'loading'
    try {
      const result = await getCities(controller.signal)
      if (controller.signal.aborted) return
      if (!Array.isArray(result)) {
        throw new ApiError(200, 'invalid_response', 'Expected a list of cities')
      }
      cities.value = result
      listError.value = null
      listStatus.value = 'ready'

      if (cityId.value !== null) {
        if (findCity(result, cityId.value)) {
          void loadDetails(cityId.value)
        } else {
          cityId.value = null
          removeStorage(STORAGE_KEYS.city)
        }
      }
    } catch (err) {
      if (controller.signal.aborted || isAbortError(err)) return
      listError.value = err
      listStatus.value = 'error'
    } finally {
      if (listController === controller) listController = null
    }
  }

  /** Starts the first load; later calls do nothing. */
  function init(): void {
    if (listStatus.value === 'idle') void loadCities()
  }

  /** Selects a city from the loaded list and remembers it. Unknown ids are ignored. */
  function setCity(id: CityId): void {
    const city = findCity(cities.value, id)
    if (!city) return
    const changed = city.id !== cityId.value
    cityId.value = city.id
    writeStorage(STORAGE_KEYS.city, city.id)
    if (changed || !currentCityDetails.value) void loadDetails(city.id)
  }

  // Names are translated by the API, so reload in the new language (keeping the old data
  // on screen until the new one arrives).
  watch(
    () => i18n.global.locale.value,
    () => {
      if (listStatus.value !== 'idle') void loadCities()
    },
  )

  return {
    cityId,
    cities,
    listStatus,
    listError,
    currentCity,
    hasCity,
    needsPicker,
    details,
    detailsStatus,
    detailsError,
    currentCityDetails,
    init,
    loadCities,
    loadDetails,
    setCity,
  }
})
