import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { CITIES, findCity, type CityConfig, type CityId } from '@/config/cities'
import { STORAGE_KEYS, readStorage, writeStorage } from '@/utils/storage'

/** Selected city, remembered in the browser. `null` until the user picks one (first visit). */
export const useCityStore = defineStore('city', () => {
  const cityId = ref<CityId | null>(findCity(readStorage(STORAGE_KEYS.city))?.id ?? null)

  const cities = computed<readonly CityConfig[]>(() => CITIES)
  const currentCity = computed<CityConfig | null>(() => findCity(cityId.value) ?? null)
  const hasCity = computed(() => currentCity.value !== null)

  function setCity(id: CityId): void {
    const city = findCity(id)
    if (!city) return
    cityId.value = city.id
    writeStorage(STORAGE_KEYS.city, city.id)
  }

  return { cityId, cities, currentCity, hasCity, setCity }
})
