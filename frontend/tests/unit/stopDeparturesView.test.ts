import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import { applyLocale, i18n } from '@/i18n'
import { routes } from '@/router'
import { useCityStore } from '@/stores/city'
import type { CityDetail } from '@/types/api'
import StopDeparturesView from '@/views/timetable/StopDeparturesView.vue'
import StopTimetableView from '@/views/timetable/StopTimetableView.vue'
import TimetableHomeView from '@/views/timetable/TimetableHomeView.vue'

import { cityDetail, cityList } from './citiesFixtures'
import { at, board, departure, liveDeparture } from './departuresFixtures'
import { jsonResponse, resetEnvironment } from './helpers'
import { stopResult } from './journeyFixtures'
import { line, timetable } from './timetableFixtures'

vi.mock('maplibre-gl', () => ({
  Map: class {
    on() {}
    addControl() {}
    remove() {}
    getCenter() {
      return { lng: 0, lat: 0 }
    }
    getZoom() {
      return 1
    }
  },
  NavigationControl: class {},
  Popup: class {},
}))
vi.mock('maplibre-gl/dist/maplibre-gl.css', () => ({}))

type Handler = (url: URL) => Response | Promise<Response> | undefined

async function mountAt(component: object, path: string, handler: Handler) {
  const calls: string[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(String(input), 'http://localhost')
      calls.push(url.pathname + url.search)
      return handler(url) ?? jsonResponse([])
    }),
  )
  const pinia = createPinia()
  setActivePinia(pinia)
  const store = useCityStore()
  store.cityId = 'alpha'
  store.cities = cityList('en')
  store.details = cityDetail('alpha', 'en') as CityDetail
  const router = createRouter({ history: createMemoryHistory(), routes })
  await router.push(path)
  await router.isReady()
  const wrapper = mount(component, {
    global: { plugins: [pinia, i18n, router] },
    attachTo: document.body,
  })
  await flushPromises()
  return { wrapper, router, calls }
}

const BOARD_PATH = '/timetable/stops/feed_a%3Astop_1'
const isBoard = (url: URL) => url.pathname.endsWith('/departures/')

beforeEach(() => {
  resetEnvironment()
  applyLocale('en')
})
afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

describe('StopDeparturesView', () => {
  it('requests the board of the route stop and renders one row per departure', async () => {
    const { wrapper, calls } = await mountAt(StopDeparturesView, BOARD_PATH, (url) =>
      isBoard(url)
        ? jsonResponse(
            board({
              departures: [
                departure({ trip_id: 't1', headsign: 'Southfield', scheduled: at(5) }),
                liveDeparture(300, { trip_id: 't2', headsign: 'Eastbrook', scheduled: at(8) }),
              ],
            }),
          )
        : undefined,
    )
    expect(calls).toContain('/api/v1/cities/alpha/stops/feed_a%3Astop_1/departures/')
    expect(wrapper.find('h1').text()).toBe('Northgate')
    expect(wrapper.findAll('[data-testid="departure-row"]')).toHaveLength(2)
    expect(wrapper.text()).toContain('Updated')
    expect(wrapper.find('[data-testid="no-realtime"]').exists()).toBe(false)
  })

  it('shows a loading status while the board is loading', async () => {
    let release: (r: Response) => void = () => {}
    const slow = new Promise<Response>((resolve) => (release = resolve))
    const { wrapper } = await mountAt(StopDeparturesView, BOARD_PATH, () => slow)
    expect(wrapper.find('.load-status[role="status"]').text()).toBe('Loading departures…')
    release(jsonResponse(board()))
    await flushPromises()
    expect(wrapper.find('.load-status').exists()).toBe(false)
    expect(wrapper.findAll('[data-testid="departure-row"]')).toHaveLength(1)
  })

  it('shows an error with a retry button that reloads the board', async () => {
    let fail = true
    const { wrapper, calls } = await mountAt(StopDeparturesView, BOARD_PATH, () =>
      fail ? jsonResponse({ error: { code: 'x', message: 'boom' } }, 500) : jsonResponse(board()),
    )
    expect(wrapper.find('[role="alert"]').exists()).toBe(true)
    expect(calls).toHaveLength(1)
    fail = false
    await wrapper.find('[role="alert"] button').trigger('click')
    await flushPromises()
    expect(calls).toHaveLength(2)
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.findAll('[data-testid="departure-row"]')).toHaveLength(1)
  })

  it('shows an empty-state message for a valid board without departures', async () => {
    const { wrapper } = await mountAt(StopDeparturesView, BOARD_PATH, () =>
      jsonResponse(board({ departures: [] })),
    )
    expect(wrapper.text()).toContain('No departures from this stop in the next 3 hours.')
    expect(wrapper.findAll('[data-testid="departure-row"]')).toHaveLength(0)
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  })

  it('shows a timetable-only note and no live markers when realtime is unavailable', async () => {
    const { wrapper } = await mountAt(StopDeparturesView, BOARD_PATH, () =>
      jsonResponse(
        board({
          realtime_available: false,
          departures: [liveDeparture(300, { scheduled: at(10) })],
        }),
      ),
    )
    expect(wrapper.find('[data-testid="no-realtime"]').text()).toContain('Timetable only')
    expect(wrapper.find('.departure__live').exists()).toBe(false)
    expect(wrapper.find('.departure__badge').exists()).toBe(false)
  })

  it('shows a "stop not found" message with retry for a 404', async () => {
    const { wrapper } = await mountAt(StopDeparturesView, BOARD_PATH, () =>
      jsonResponse({ error: { code: 'not_found', message: 'nope' } }, 404),
    )
    expect(wrapper.find('[role="alert"]').text()).toContain(
      'This stop was not found in the selected city.',
    )
    expect(wrapper.findAll('[data-testid="departure-row"]')).toHaveLength(0)
  })

  it('shows the messages in Polish after switching the language', async () => {
    applyLocale('pl')
    const { wrapper } = await mountAt(StopDeparturesView, BOARD_PATH, () =>
      jsonResponse(board({ departures: [] })),
    )
    expect(wrapper.text()).toContain('Brak odjazdów z tego przystanku')
    expect(wrapper.text()).toContain('Zaktualizowano')
  })

  it('keeps the board and shows a one-time warning when a refresh fails', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval', 'Date'] })
    let fail = false
    const { wrapper } = await mountAt(StopDeparturesView, BOARD_PATH, () =>
      fail ? jsonResponse({ error: { code: 'x', message: 'boom' } }, 500) : jsonResponse(board()),
    )
    expect(wrapper.find('.stop-board__problem').exists()).toBe(false)
    fail = true
    await vi.advanceTimersByTimeAsync(30_000)
    await flushPromises()
    expect(wrapper.find('.stop-board__problem').text()).toContain('Could not refresh')
    expect(wrapper.findAll('[data-testid="departure-row"]')).toHaveLength(1)
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    fail = false
    await vi.advanceTimersByTimeAsync(30_000)
    await flushPromises()
    expect(wrapper.find('.stop-board__problem').exists()).toBe(false)
  })
})

describe('timetable entry points', () => {
  it('links the stop timetable to the all-departures board', async () => {
    const { wrapper } = await mountAt(
      StopTimetableView,
      '/timetable/lines/feed_a%3A7/stops/feed_a%3Astop_1',
      (url) => (url.pathname.endsWith('/timetable/') ? jsonResponse(timetable()) : undefined),
    )
    const link = wrapper.find('a[href="/timetable/stops/feed_a:s2"]')
    expect(link.exists()).toBe(true)
    expect(link.text()).toBe('All departures from this stop')
  })

  it('opens the departures board after choosing a stop in the timetable stop search', async () => {
    const { wrapper, router } = await mountAt(TimetableHomeView, '/timetable', (url) => {
      if (url.pathname.endsWith('/stops/')) return jsonResponse([stopResult()])
      if (url.pathname.endsWith('/lines/')) return jsonResponse([line()])
      return undefined
    })
    const input = wrapper.find('.timetable-home__stop-search input')
    expect(input.attributes('placeholder')).toBe('Type a stop name')
    expect(wrapper.find('.timetable-home__stop-search .place-input__icon-button').exists()).toBe(
      false,
    )
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    await input.setValue('north')
    await vi.advanceTimersByTimeAsync(500)
    vi.useRealTimers()
    await flushPromises()
    const option = wrapper.find('[role="option"]')
    expect(option.exists()).toBe(true)
    await option.trigger('mousedown')
    await option.trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('timetable-stop-departures')
    expect(router.currentRoute.value.params.stopId).toBe('feed_a:stop_1')
  })
})
