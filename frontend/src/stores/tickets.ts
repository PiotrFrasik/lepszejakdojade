import { defineStore } from 'pinia'
import { ref } from 'vue'

import { STORAGE_KEYS, readStorage, writeStorage } from '@/utils/storage'

/**
 * Fare choice shared by the ticket catalogue (standard / reduced toggle) and the ticket hint
 * under journey results. Remembered in the browser.
 */
export const useTicketsStore = defineStore('tickets', () => {
  const reduced = ref<boolean>(readStorage(STORAGE_KEYS.ticketsReduced) === 'true')

  function setReduced(value: boolean): void {
    reduced.value = value
    writeStorage(STORAGE_KEYS.ticketsReduced, value ? 'true' : 'false')
  }

  return { reduced, setReduced }
})
