import { createPinia, setActivePinia, type Pinia } from 'pinia'

import { ApiError } from '@/api/client'
import { findCity, toLngLat } from '@/config/cities'
import { applyLocale } from '@/i18n'
import { useCityStore } from '@/stores/city'
import { STORAGE_KEYS } from '@/utils/storage'

import { cityList, makeCitiesFetch, settle } from './citiesFixtures'
import { jsonResponse } from './helpers'

const pinias: Pinia[] = []

function freshStore() {
  const pinia = createPinia()
  pinias.push(pinia)
  setActivePinia(pinia)
  return useCityStore()
}

beforeEach(() => {
  window.localStorage.clear()
  applyLocale('pl')
  window.localStorage.clear()
})
afterEach(() => {
  // Stop the stores' language watchers so they do not leak into other tests.
  for (const pinia of pinias.splice(0)) {
    const stores = (pinia as unknown as { _s: Map<string, { $dispose: () => void }> })._s
    stores.forEach((s) => s.$dispose())
  }
  vi.unstubAllGlobals()
})

describe('city helpers', () => {
  it('toLngLat converts {lat, lon} to [lon, lat]', () => {
    expect(toLngLat({ lat: 1.5, lon: 2.5 })).toEqual([2.5, 1.5])
  })

  it('findCity finds by id and returns undefined for unknown or empty ids', () => {
    const list = cityList()
    expect(findCity(list, 'beta')?.name).toBe('Beta')
    expect(findCity(list, 'nope')).toBeUndefined()
    expect(findCity(list, null)).toBeUndefined()
    expect(findCity(list, '')).toBeUndefined()
  })
})

describe('city store', () => {
  it('has no city and no list before init', () => {
    vi.stubGlobal('fetch', makeCitiesFetch().fn)
    const store = freshStore()
    expect(store.cityId).toBeNull()
    expect(store.cities).toEqual([])
    expect(store.hasCity).toBe(false)
    expect(store.needsPicker).toBe(true)
    expect(store.listStatus).toBe('idle')
  })

  it('loads the list from the API on init and only once', async () => {
    const mock = makeCitiesFetch()
    vi.stubGlobal('fetch', mock.fn)
    const store = freshStore()
    store.init()
    store.init()
    expect(store.listStatus).toBe('loading')
    await settle()
    expect(store.listStatus).toBe('ready')
    expect(store.cities.map((c) => c.id)).toEqual(['alpha', 'beta'])
    expect(mock.calls.filter((c) => c.url.endsWith('/cities/'))).toHaveLength(1)
  })

  it('setCity persists the id and loads its details', async () => {
    vi.stubGlobal('fetch', makeCitiesFetch().fn)
    const store = freshStore()
    store.init()
    await settle()
    store.setCity('beta')
    expect(window.localStorage.getItem(STORAGE_KEYS.city)).toBe('beta')
    expect(store.currentCity?.name).toBe('Beta')
    await settle()
    expect(store.detailsStatus).toBe('ready')
    expect(store.currentCityDetails?.timezone).toBe('Europe/Warsaw')
    expect(store.currentCityDetails?.line_groups[0]?.colour).toBe('#112233')
    expect(store.needsPicker).toBe(false)
  })

  it('ignores an id that is not in the loaded list', async () => {
    vi.stubGlobal('fetch', makeCitiesFetch().fn)
    const store = freshStore()
    store.init()
    await settle()
    store.setCity('gotham')
    expect(store.cityId).toBeNull()
    expect(window.localStorage.getItem(STORAGE_KEYS.city)).toBeNull()
  })

  it('keeps a remembered city that is in the list, without showing the picker', async () => {
    window.localStorage.setItem(STORAGE_KEYS.city, 'alpha')
    vi.stubGlobal('fetch', makeCitiesFetch().fn)
    const store = freshStore()
    store.init()
    // While validating the remembered city the picker must not flash.
    expect(store.needsPicker).toBe(false)
    await settle()
    expect(store.hasCity).toBe(true)
    expect(store.needsPicker).toBe(false)
    expect(store.currentCityDetails?.id).toBe('alpha')
    expect(window.localStorage.getItem(STORAGE_KEYS.city)).toBe('alpha')
  })

  it('forgets a remembered city that is not in the list and shows the picker', async () => {
    window.localStorage.setItem(STORAGE_KEYS.city, 'gotham')
    vi.stubGlobal('fetch', makeCitiesFetch().fn)
    const store = freshStore()
    store.init()
    await settle()
    expect(store.cityId).toBeNull()
    expect(window.localStorage.getItem(STORAGE_KEYS.city)).toBeNull()
    expect(store.needsPicker).toBe(true)
  })

  it('reports an error when the list request fails, and retry recovers', async () => {
    let fail = true
    const mock = makeCitiesFetch({
      list: (lang) =>
        fail
          ? jsonResponse({ error: { code: 'server_error', message: 'x' } }, 500)
          : jsonResponse(cityList(lang)),
    })
    vi.stubGlobal('fetch', mock.fn)
    const store = freshStore()
    store.init()
    await settle()
    expect(store.listStatus).toBe('error')
    expect(store.listError).toBeInstanceOf(ApiError)
    expect(store.needsPicker).toBe(true)
    fail = false
    await store.loadCities()
    expect(store.listStatus).toBe('ready')
    expect(store.listError).toBeNull()
    expect(store.cities).toHaveLength(2)
  })

  it('treats a network failure as an error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')))
    const store = freshStore()
    store.init()
    await settle()
    expect(store.listStatus).toBe('error')
    expect((store.listError as ApiError).code).toBe('network_error')
  })

  it('treats a non-array list response as an error', async () => {
    vi.stubGlobal('fetch', makeCitiesFetch({ list: () => jsonResponse({ results: [] }) }).fn)
    const store = freshStore()
    store.init()
    await settle()
    expect(store.listStatus).toBe('error')
    expect(store.cities).toEqual([])
  })

  it('accepts an empty list as ready with no cities', async () => {
    vi.stubGlobal('fetch', makeCitiesFetch({ list: () => jsonResponse([]) }).fn)
    const store = freshStore()
    store.init()
    await settle()
    expect(store.listStatus).toBe('ready')
    expect(store.cities).toEqual([])
    expect(store.needsPicker).toBe(true)
  })

  it('shows the picker with an error when verifying a remembered city fails', async () => {
    window.localStorage.setItem(STORAGE_KEYS.city, 'alpha')
    vi.stubGlobal('fetch', makeCitiesFetch({ list: () => jsonResponse({}, 500) }).fn)
    const store = freshStore()
    store.init()
    await settle()
    expect(store.listStatus).toBe('error')
    expect(store.needsPicker).toBe(true)
    // The remembered id is kept for the next successful load.
    expect(window.localStorage.getItem(STORAGE_KEYS.city)).toBe('alpha')
  })

  it('sends Accept-Language on both endpoints', async () => {
    const mock = makeCitiesFetch()
    vi.stubGlobal('fetch', mock.fn)
    applyLocale('en')
    const store = freshStore()
    store.init()
    await settle()
    store.setCity('alpha')
    await settle()
    const list = mock.calls.find((c) => c.url.endsWith('/cities/'))
    const detail = mock.calls.find((c) => c.url.endsWith('/cities/alpha/'))
    expect(list?.acceptLanguage).toBe('en')
    expect(detail?.acceptLanguage).toBe('en')
  })

  it('re-fetches the list and details when the language changes', async () => {
    const mock = makeCitiesFetch()
    vi.stubGlobal('fetch', mock.fn)
    const store = freshStore()
    store.init()
    await settle()
    store.setCity('beta')
    await settle()
    expect(store.currentCity?.name).toBe('Beta')
    applyLocale('en')
    await settle()
    expect(store.currentCity?.name).toBe('Betaville')
    expect(store.currentCityDetails?.name).toBe('Betaville')
    expect(store.cities.map((c) => c.name)).toEqual(['Alpha', 'Betaville'])
    const listCalls = mock.calls.filter((c) => c.url.endsWith('/cities/'))
    expect(listCalls[listCalls.length - 1]?.acceptLanguage).toBe('en')
  })

  it('does not fetch on language change before init', async () => {
    const mock = makeCitiesFetch()
    vi.stubGlobal('fetch', mock.fn)
    freshStore()
    applyLocale('en')
    await settle()
    expect(mock.calls).toHaveLength(0)
  })

  it('a details 404 does not reset the selected city', async () => {
    const mock = makeCitiesFetch({
      detail: () => jsonResponse({ error: { code: 'not_found', message: 'nope' } }, 404),
    })
    vi.stubGlobal('fetch', mock.fn)
    const store = freshStore()
    store.init()
    await settle()
    store.setCity('alpha')
    await settle()
    expect(store.detailsStatus).toBe('error')
    expect((store.detailsError as ApiError).status).toBe(404)
    expect((store.detailsError as ApiError).code).toBe('not_found')
    expect(store.cityId).toBe('alpha')
    expect(store.hasCity).toBe(true)
    expect(store.currentCityDetails).toBeNull()
    expect(window.localStorage.getItem(STORAGE_KEYS.city)).toBe('alpha')
  })

  it('aborts a superseded details request and ignores its result', async () => {
    const resolvers: Record<string, () => void> = {}
    const mock = makeCitiesFetch({
      detail: (id, lang) =>
        new Promise<Response>((resolve) => {
          resolvers[id] = () =>
            resolve(
              jsonResponse({
                id,
                name: `${id}-${lang}`,
                map: { center: { lat: 0, lon: 0 }, zoom: 1 },
                timezone: 'UTC',
                vehicle_types: [],
                line_groups: [],
                realtime: { departures: false, vehicles: false },
              }),
            )
        }),
    })
    vi.stubGlobal('fetch', mock.fn)
    const store = freshStore()
    store.init()
    await settle()
    store.setCity('alpha')
    store.setCity('beta')
    await settle()
    const alphaCall = mock.calls.find((c) => c.url.endsWith('/cities/alpha/'))
    expect(alphaCall?.signal?.aborted).toBe(true)
    // The stale response arrives late and must be ignored.
    resolvers.alpha!()
    resolvers.beta!()
    await settle()
    expect(store.cityId).toBe('beta')
    expect(store.currentCityDetails?.id).toBe('beta')
    expect(store.detailsStatus).toBe('ready')
  })

  it('aborts a superseded list request', async () => {
    let n = 0
    const mock = makeCitiesFetch({
      list: (lang) => {
        n += 1
        return n === 1 ? new Promise<Response>(() => {}) : jsonResponse(cityList(lang))
      },
    })
    vi.stubGlobal('fetch', mock.fn)
    const store = freshStore()
    store.init()
    await store.loadCities()
    const first = mock.calls.filter((c) => c.url.endsWith('/cities/'))[0]
    expect(first?.signal?.aborted).toBe(true)
    expect(store.listStatus).toBe('ready')
    expect(store.cities).toHaveLength(2)
  })
})
