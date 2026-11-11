import { createPinia, setActivePinia } from 'pinia'

import { findCity } from '@/config/cities'
import { useCityStore } from '@/stores/city'
import { STORAGE_KEYS } from '@/utils/storage'

beforeEach(() => {
  window.localStorage.clear()
  setActivePinia(createPinia())
})

describe('city store', () => {
  it('has no city until one is chosen', () => {
    const store = useCityStore()
    expect(store.cityId).toBeNull()
    expect(store.currentCity).toBeNull()
    expect(store.hasCity).toBe(false)
  })

  it('persists the chosen city to localStorage', () => {
    const store = useCityStore()
    store.setCity('warszawa')
    expect(store.currentCity?.name).toBe('Warszawa')
    expect(window.localStorage.getItem(STORAGE_KEYS.city)).toBe('warszawa')
  })

  it('restores the stored city on init', () => {
    window.localStorage.setItem(STORAGE_KEYS.city, 'krakow')
    setActivePinia(createPinia())
    const store = useCityStore()
    expect(store.cityId).toBe('krakow')
    expect(store.hasCity).toBe(true)
  })

  it('ignores an unknown stored city', () => {
    window.localStorage.setItem(STORAGE_KEYS.city, 'gotham')
    setActivePinia(createPinia())
    expect(useCityStore().hasCity).toBe(false)
  })

  it('ignores an unknown city id passed to setCity', () => {
    const store = useCityStore()
    store.setCity('gotham' as never)
    expect(store.cityId).toBeNull()
    expect(window.localStorage.getItem(STORAGE_KEYS.city)).toBeNull()
  })

  it('exposes both cities from config', () => {
    expect(useCityStore().cities.map((c) => c.id)).toEqual(['krakow', 'warszawa'])
    expect(findCity('krakow')?.center).toHaveLength(2)
  })
})
