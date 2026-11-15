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
import { stopOverview } from './stopOverviewFixtures'
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

const isBoard = (url: URL) => url.pathname.endsWith('/departures/')
const isOverview = (url: URL) => /\/stops\/[^/]+\/$/.test(url.pathname) && !isBoard(url)

type Handler = (url: URL) => Response | Promise<Response> | undefined

async function mountAt(component: object, path: string, handler: Handler) {
  const calls: string[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(String(input), 'http://localhost')
      calls.push(url.pathname + url.search)
      const handled = handler(url)
      if (handled) return handled
      if (isBoard(url)) return jsonResponse(board())
      return isOverview(url) ? jsonResponse(stopOverview()) : jsonResponse([])
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
    const { wrapper } = await mountAt(StopDeparturesView, BOARD_PATH, (url) =>
      isBoard(url) ? slow : undefined,
    )
    expect(wrapper.find('.load-status[role="status"]').text()).toBe('Loading departures…')
    release(jsonResponse(board()))
    await flushPromises()
    expect(wrapper.find('.load-status').exists()).toBe(false)
    expect(wrapper.findAll('[data-testid="departure-row"]')).toHaveLength(1)
  })

  it('shows an error with a retry button that reloads the board', async () => {
    let fail = true
    const { wrapper, calls } = await mountAt(StopDeparturesView, BOARD_PATH, (url) =>
      !isBoard(url)
        ? undefined
        : fail
          ? jsonResponse({ error: { code: 'x', message: 'boom' } }, 500)
          : jsonResponse(board()),
    )
    const boardCalls = () => calls.filter((c) => c.includes('/departures/'))
    expect(wrapper.find('[role="alert"]').exists()).toBe(true)
    expect(boardCalls()).toHaveLength(1)
    fail = false
    await wrapper.find('[role="alert"] button').trigger('click')
    await flushPromises()
    expect(boardCalls()).toHaveLength(2)
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.findAll('[data-testid="departure-row"]')).toHaveLength(1)
  })

  it('shows an empty-state message for a valid board without departures', async () => {
    const { wrapper } = await mountAt(StopDeparturesView, BOARD_PATH, (url) =>
      isBoard(url) ? jsonResponse(board({ departures: [] })) : undefined,
    )
    expect(wrapper.text()).toContain('No departures from this stop in the next 3 hours.')
    expect(wrapper.findAll('[data-testid="departure-row"]')).toHaveLength(0)
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  })

  it('shows a timetable-only note and no live markers when realtime is unavailable', async () => {
    const { wrapper } = await mountAt(StopDeparturesView, BOARD_PATH, (url) =>
      isBoard(url)
        ? jsonResponse(
            board({
              realtime_available: false,
              departures: [liveDeparture(300, { scheduled: at(10) })],
            }),
          )
        : undefined,
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
    const { wrapper } = await mountAt(StopDeparturesView, BOARD_PATH, (url) =>
      isBoard(url) ? jsonResponse(board({ departures: [] })) : undefined,
    )
    expect(wrapper.text()).toContain('Brak odjazdów z tego przystanku')
    expect(wrapper.text()).toContain('Zaktualizowano')
  })

  it('keeps the board and shows a one-time warning when a refresh fails', async () => {
    vi.useFakeTimers({
      toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval', 'Date'],
    })
    let fail = false
    const { wrapper } = await mountAt(StopDeparturesView, BOARD_PATH, (url) =>
      !isBoard(url)
        ? undefined
        : fail
          ? jsonResponse({ error: { code: 'x', message: 'boom' } }, 500)
          : jsonResponse(board()),
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

const notFound = () => jsonResponse({ error: { code: 'not_found', message: 'nope' } }, 404)
const serverError = () => jsonResponse({ error: { code: 'x', message: 'boom' } }, 500)
const OVERVIEW_URL = '/api/v1/cities/alpha/stops/feed_a%3Astop_1/'

describe('StopDeparturesView lines section', () => {
  it('requests the departures and the stop overview in parallel', async () => {
    const release: Array<(r: Response) => void> = []
    const { calls } = await mountAt(
      StopDeparturesView,
      BOARD_PATH,
      () => new Promise<Response>((resolve) => release.push(resolve)),
    )
    // Both requests were sent before either answered.
    expect(calls).toContain(OVERVIEW_URL)
    expect(calls).toContain('/api/v1/cities/alpha/stops/feed_a%3Astop_1/departures/')
    expect(release).toHaveLength(2)
    release[0]!(jsonResponse(board()))
    release[1]!(jsonResponse(stopOverview()))
  })

  it('shows a loading status for the lines while the overview is pending', async () => {
    let release: (r: Response) => void = () => {}
    const slow = new Promise<Response>((resolve) => (release = resolve))
    const { wrapper } = await mountAt(StopDeparturesView, BOARD_PATH, (url) =>
      isOverview(url) ? slow : isBoard(url) ? jsonResponse(board()) : undefined,
    )
    expect(wrapper.text()).toContain('Loading lines…')
    expect(wrapper.findAll('[data-testid="departure-row"]')).toHaveLength(1)
    release(jsonResponse(stopOverview()))
    await flushPromises()
    expect(wrapper.text()).not.toContain('Loading lines…')
    expect(wrapper.findAll('[data-testid="stop-line"]').length).toBeGreaterThan(0)
  })

  it('renders the lines section with a heading', async () => {
    const { wrapper } = await mountAt(StopDeparturesView, BOARD_PATH, () => undefined)
    expect(wrapper.text()).toContain('Lines at this stop')
    expect(wrapper.find('h1').text()).toBe('Northgate')
    expect(wrapper.findAll('[data-testid="stop-line"]')).toHaveLength(1)
  })

  it('shows the empty state when no lines stop there', async () => {
    const { wrapper } = await mountAt(StopDeparturesView, BOARD_PATH, (url) =>
      isOverview(url) ? jsonResponse(stopOverview({ lines: [] })) : undefined,
    )
    expect(wrapper.find('[data-testid="no-stop-lines"]').text()).toBe('No lines stop here.')
  })

  it('keeps the board when the overview fails, and retries only the overview', async () => {
    let failOverview = true
    const { wrapper, calls } = await mountAt(StopDeparturesView, BOARD_PATH, (url) =>
      isOverview(url) && failOverview ? serverError() : undefined,
    )
    expect(wrapper.findAll('[data-testid="departure-row"]')).toHaveLength(1)
    const alerts = wrapper.findAll('[role="alert"]')
    expect(alerts).toHaveLength(1)
    const boardBefore = calls.filter((c) => c.includes('/departures/')).length
    failOverview = false
    await alerts[0]!.find('button').trigger('click')
    await flushPromises()
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.findAll('[data-testid="stop-line"]')).toHaveLength(1)
    expect(calls.filter((c) => c.includes('/departures/'))).toHaveLength(boardBefore)
    expect(calls.filter((c) => c === OVERVIEW_URL)).toHaveLength(2)
  })

  it('keeps the lines when the board fails, and retries only the board', async () => {
    let failBoard = true
    const { wrapper, calls } = await mountAt(StopDeparturesView, BOARD_PATH, (url) =>
      isBoard(url) && failBoard ? serverError() : undefined,
    )
    expect(wrapper.findAll('[data-testid="stop-line"]')).toHaveLength(1)
    expect(wrapper.findAll('[role="alert"]')).toHaveLength(1)
    failBoard = false
    await wrapper.find('[role="alert"] button').trigger('click')
    await flushPromises()
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.findAll('[data-testid="departure-row"]')).toHaveLength(1)
    expect(calls.filter((c) => c === OVERVIEW_URL)).toHaveLength(1)
  })

  it('shows one not-found message when both requests return 404, and retry reloads both', async () => {
    let missing = true
    const { wrapper, calls } = await mountAt(StopDeparturesView, BOARD_PATH, (url) =>
      missing && (isBoard(url) || isOverview(url)) ? notFound() : undefined,
    )
    expect(wrapper.findAll('[role="alert"]')).toHaveLength(1)
    expect(wrapper.text()).toContain('This stop was not found in the selected city.')
    expect(wrapper.text()).not.toContain('Lines at this stop')
    missing = false
    await wrapper.find('[role="alert"] button').trigger('click')
    await flushPromises()
    expect(calls.filter((c) => c === OVERVIEW_URL)).toHaveLength(2)
    expect(calls.filter((c) => c.includes('/departures/'))).toHaveLength(2)
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.findAll('[data-testid="departure-row"]')).toHaveLength(1)
    expect(wrapper.findAll('[data-testid="stop-line"]')).toHaveLength(1)
  })

  it('does not merge the sections when only the board returns 404', async () => {
    const { wrapper } = await mountAt(StopDeparturesView, BOARD_PATH, (url) =>
      isBoard(url) ? notFound() : undefined,
    )
    expect(wrapper.findAll('[data-testid="stop-line"]')).toHaveLength(1)
    expect(wrapper.text()).toContain('Lines at this stop')
  })

  it('shows the lines section in Polish', async () => {
    applyLocale('pl')
    const { wrapper } = await mountAt(StopDeparturesView, BOARD_PATH, () => undefined)
    expect(wrapper.text()).toContain('Linie na tym przystanku')
  })

  it('uses the stop page title key for the route', () => {
    const route = routes.find((r) => r.name === 'timetable-stop-departures')
    expect(route?.meta?.titleKey).toBe('timetable.stopPage')
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
