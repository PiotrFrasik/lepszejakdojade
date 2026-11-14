import { computed } from 'vue'

import {
  DEFAULT_TIME_ZONE,
  formatDate,
  formatDateLong,
  formatDateTime,
  formatDistance,
  formatDuration,
  formatPrice,
  formatTime,
  type DateInput,
} from '@/i18n/format'
import { useCityStore } from '@/stores/city'

/**
 * Formatting helpers bound to the current UI locale and the selected city's time zone
 * (`CityDetail.timezone`, `Europe/Warsaw` until the city details are loaded).
 *
 * Calling the returned functions in a template or `computed` is reactive: the output changes
 * when the language or the city changes.
 */
export function useFormat() {
  const cityStore = useCityStore()
  const timeZone = computed<string>(
    () => cityStore.currentCityDetails?.timezone || DEFAULT_TIME_ZONE,
  )

  return {
    timeZone,
    time: (value: DateInput): string => formatTime(value, timeZone.value),
    date: (value: DateInput): string => formatDate(value, timeZone.value),
    dateLong: (value: DateInput): string => formatDateLong(value, timeZone.value),
    dateTime: (value: DateInput): string => formatDateTime(value, timeZone.value),
    price: formatPrice,
    duration: formatDuration,
    distance: formatDistance,
  }
}
