import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent, h } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'

import { applyLocale, i18n } from '@/i18n'
import { routes } from '@/router'
import {
  DEPARTURES_REFRESH_MS,
  LIVE_STALE_AFTER_MS,
  useStopDepartures,
} from '@/composables/useStopDepartures'
import { useCityStore } from '@/stores/city'
import type { CityDetail } from '@/types/api'
import { DEPARTED_GRACE_MS, hasDeparted } from '@/utils/departures'
import StopDeparturesView from '@/views/timetable/StopDeparturesView.vue'

import { cityDetail, cityList } from './citiesFixtures'
import { at, board, departure, liveDeparture, NOW } from './departuresFixtures'
import { jsonResponse, resetEnvironment } from './helpers'

vi.mock('maplibre-gl', () => ({
  Map: class {},
  NavigationControl: class {},
  Popup: class {},
}))
vi.mock('maplibre-gl/dist/maplibre-gl.css', () => ({}))

const failure = () => jsonResponse({ error: { code: 'x', message: 'boom' } }, 500)
const BOARD_PATH = '/timetable/stops/feed_a%3Astop_1'
let visibility: 'visible' | 'hidden' = 'visible'
const mounted: { unmount: () => void }[] = []

beforeEach(() => {
  resetEnvironment()
  applyLocale('en')
  visibility = 'visible'
  Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => visibility })
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval', 'Date'] })
})
afterEach(() => {
  mounted.splice(0).forEach((w) => w.unmount())
  vi.useRealTimers()
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

describe('hasDeparted', () => {
  it('keeps a departure within the one-minute grace window and drops older ones', () => {
    expect(DEPARTED_GRACE_MS).toBe(60_000)
    expect(hasDeparted(departure({ scheduled: at(5) }), true, NOW)).toBe(false)
    expect(hasDeparted(departure({ scheduled: at(0, -59) }), true, NOW)).toBe(false)
    expect(hasDeparted(departure({ scheduled: at(-1) }), true, NOW)).toBe(false)
    expect(hasDeparted(departure({ scheduled: at(-1, -1) }), true, NOW)).toBe(true)
  })

  it('judges live rows by expected time, and by scheduled time without realtime', () => {
    const late = liveDeparture(300, { scheduled: at(-3) })
    expect(hasDeparted(late, true, NOW)).toBe(false)
    expect(hasDeparted(late, false, NOW)).toBe(true)
  })

  it('does not hide rows with an unparsable time or an invalid now', () => {
    expect(hasDeparted(departure({ scheduled: 'garbage' }), true, NOW)).toBe(false)
    expect(hasDeparted(departure({ scheduled: at(-30) }), true, Number.NaN)).toBe(false)
  })
})

describe('useStopDepartures staleness', () => {
  interface Pending {
    resolve: (r: Response) => void
  }
  let pending: Pending[] = []

  function setup() {
    pending = []
    vi.stubGlobal(
      'fetch',
      vi.fn(() => new Promise<Response>((resolve) => pending.push({ resolve }))),
    )
    let api!: ReturnType<typeof useStopDepartures>
    const wrapper = mount(
      defineComponent({
        setup() {
          api = useStopDepartures(() => ({ city: 'alpha', stop: 'feed_a:stop_1' }))
          return () => h('div')
        },
      }),
    )
    mounted.push(wrapper)
    return () => api
  }

  const failRefresh = async () => {
    await vi.advanceTimersByTimeAsync(DEPARTURES_REFRESH_MS)
    pending[pending.length - 1]!.resolve(failure())
    await flushPromises()
  }

  it('is not stale right after a successful load', async () => {
    const api = setup()
    expect(api().stale.value).toBe(false)
    pending[0]!.resolve(jsonResponse(board()))
    await flushPromises()
    expect(api().stale.value).toBe(false)
  })

  it('becomes stale after 5 minutes of failing refreshes and recovers on success', async () => {
    const api = setup()
    pending[0]!.resolve(jsonResponse(board()))
    await flushPromises()
    expect(LIVE_STALE_AFTER_MS).toBe(300_000)
    for (let i = 0; i < 8; i++) await failRefresh()
    expect(api().stale.value).toBe(false)
    for (let i = 0; i < 3; i++) await failRefresh()
    await vi.advanceTimersByTimeAsync(10_000)
    expect(api().stale.value).toBe(true)
    expect(api().data.value).not.toBeNull()
    await vi.advanceTimersByTimeAsync(DEPARTURES_REFRESH_MS)
    pending[pending.length - 1]!.resolve(jsonResponse(board()))
    await flushPromises()
    expect(api().stale.value).toBe(false)
  })

  it('is stale at once when a tab hidden for over 5 minutes becomes visible, while it reloads', async () => {
    const api = setup()
    pending[0]!.resolve(jsonResponse(board()))
    await flushPromises()
    visibility = 'hidden'
    document.dispatchEvent(new Event('visibilitychange'))
    // The clock interval may not tick in a hidden tab: move device time without ticking it.
    vi.setSystemTime(Date.now() + 10 * 60_000)
    expect(api().stale.value).toBe(false)
    visibility = 'visible'
    document.dispatchEvent(new Event('visibilitychange'))
    expect(api().stale.value).toBe(true)
    expect(pending).toHaveLength(2)
    pending[1]!.resolve(jsonResponse(board()))
    await flushPromises()
    expect(api().stale.value).toBe(false)
  })
})

describe('StopDeparturesView staleness and departed rows', () => {
  async function mountView(handler: () => Response) {
    vi.stubGlobal('fetch', vi.fn(async () => handler()))
    const pinia = createPinia()
    setActivePinia(pinia)
    const store = useCityStore()
    store.cityId = 'alpha'
    store.cities = cityList('en')
    store.details = cityDetail('alpha', 'en') as CityDetail
    const router = createRouter({ history: createMemoryHistory(), routes })
    await router.push(BOARD_PATH)
    await router.isReady()
    const wrapper = mount(StopDeparturesView, {
      global: { plugins: [pinia, i18n, router] },
      attachTo: document.body,
    })
    mounted.push(wrapper)
    await flushPromises()
    return wrapper
  }
  const rows = (w: Awaited<ReturnType<typeof mountView>>) =>
    w.findAll('[data-testid="departure-row"]')

  it('hides rows that have already left, and shows the empty message when none remain', async () => {
    const some = await mountView(() =>
      jsonResponse(
        board({
          departures: [
            departure({ trip_id: 'gone', scheduled: at(-5) }),
            departure({ trip_id: 'just-left', scheduled: at(0, -30) }),
          ],
        }),
      ),
    )
    expect(rows(some)).toHaveLength(1)
    const none = await mountView(() =>
      jsonResponse(board({ departures: [departure({ scheduled: at(-5) })] })),
    )
    expect(rows(none)).toHaveLength(0)
    expect(none.text()).toContain('No departures from this stop in the next 3 hours.')
  })

  it('drops a row as time passes while refreshes fail, and keeps the failure warning', async () => {
    let fail = false
    const w = await mountView(() =>
      fail ? failure() : jsonResponse(board({ departures: [departure({ scheduled: at(2) })] })),
    )
    expect(rows(w)).toHaveLength(1)
    fail = true
    await vi.advanceTimersByTimeAsync(4 * 60_000)
    await flushPromises()
    expect(rows(w)).toHaveLength(0)
    expect(w.text()).toContain('No departures from this stop')
    expect(w.find('.stop-board__problem').exists()).toBe(true)
  })

  it('switches live rows to timetable-only with the note once the board is stale', async () => {
    let fail = false
    const w = await mountView(() =>
      fail
        ? failure()
        : jsonResponse(board({ departures: [liveDeparture(300, { scheduled: at(40) })] })),
    )
    expect(w.find('.departure__live').exists()).toBe(true)
    expect(w.find('[data-testid="no-realtime"]').exists()).toBe(false)
    fail = true
    await vi.advanceTimersByTimeAsync(4 * 60_000)
    await flushPromises()
    expect(w.find('.departure__live').exists()).toBe(true)
    await vi.advanceTimersByTimeAsync(2 * 60_000)
    await flushPromises()
    expect(w.find('.departure__live').exists()).toBe(false)
    expect(w.find('.departure__badge').exists()).toBe(false)
    expect(w.find('[data-testid="no-realtime"]').exists()).toBe(true)
    expect(w.find('.stop-board__problem').exists()).toBe(true)
    expect(rows(w)).toHaveLength(1)
    fail = false
    await vi.advanceTimersByTimeAsync(30_000)
    await flushPromises()
    expect(w.find('.departure__live').exists()).toBe(true)
    expect(w.find('[data-testid="no-realtime"]').exists()).toBe(false)
  })
})
