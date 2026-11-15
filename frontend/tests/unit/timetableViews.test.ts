import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import type { Component } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'

import { applyLocale, i18n } from '@/i18n'
import { routes } from '@/router'
import { useCityStore } from '@/stores/city'
import type { CityDetail } from '@/types/api'
import { STORAGE_KEYS } from '@/utils/storage'
import LineView from '@/views/timetable/LineView.vue'
import StopTimetableView from '@/views/timetable/StopTimetableView.vue'
import TimetableHomeView from '@/views/timetable/TimetableHomeView.vue'

import { cityDetail, cityList } from './citiesFixtures'
import { jsonResponse, resetEnvironment } from './helpers'
import { dep, line, route, timetable, trip } from './timetableFixtures'

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

interface Setup {
  handler?: Handler
  details?: boolean
}

function notFound(): Response {
  return jsonResponse({ error: { code: 'not_found', message: 'nope' } }, 404)
}

async function mountView(component: Component, path: string, setup: Setup = {}) {
  const calls: string[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(String(input), 'http://localhost')
      calls.push(url.pathname + url.search)
      return setup.handler?.(url) ?? jsonResponse([])
    }),
  )
  const pinia = createPinia()
  setActivePinia(pinia)
  const store = useCityStore()
  store.cityId = 'alpha'
  store.cities = cityList('en')
  if (setup.details !== false) store.details = cityDetail('alpha', 'en') as CityDetail
  const router = createRouter({ history: createMemoryHistory(), routes })
  await router.push(path)
  await router.isReady()
  const wrapper = mount(component, {
    global: { plugins: [pinia, i18n, router] },
    attachTo: document.body,
  })
  await flushPromises()
  return { wrapper, router, store, calls }
}

beforeEach(() => {
  resetEnvironment()
  applyLocale('en')
  HTMLDialogElement.prototype.showModal ??= function (this: HTMLDialogElement) {
    this.setAttribute('open', '')
  }
  HTMLDialogElement.prototype.close ??= function (this: HTMLDialogElement) {
    this.removeAttribute('open')
  }
})
afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

describe('TimetableHomeView', () => {
  const linesFor = (type: string) =>
    type === 'bus'
      ? [line({ id: 'f:100', short_name: '100', vehicle_type: 'bus', group: 'g1' })]
      : [line({ id: 'f:7', short_name: '7', group: 'g1' })]
  const handler: Handler = (url) =>
    url.pathname.endsWith('/lines/')
      ? jsonResponse(linesFor(url.searchParams.get('vehicle_type') ?? ''))
      : undefined

  it('shows only the vehicle types of the city and loads the first one', async () => {
    const { wrapper, calls } = await mountView(TimetableHomeView, '/timetable', { handler })
    expect(wrapper.findAll('[role="tab"]').map((t) => t.text())).toEqual(['Trams', 'Buses'])
    expect(calls).toEqual(['/api/v1/cities/alpha/lines/?vehicle_type=tram'])
    expect(wrapper.findAll('.line-grid__tile').map((t) => t.text())).toEqual(['7'])
  })

  it('switches tab, refetches for that type and remembers the tab', async () => {
    const { wrapper, calls } = await mountView(TimetableHomeView, '/timetable', { handler })
    await wrapper.findAll('[role="tab"]')[1]!.trigger('click')
    await flushPromises()
    expect(calls[calls.length - 1]).toBe('/api/v1/cities/alpha/lines/?vehicle_type=bus')
    expect(wrapper.findAll('.line-grid__tile').map((t) => t.text())).toEqual(['100'])
    expect(window.localStorage.getItem(STORAGE_KEYS.timetableVehicleType)).toBe('bus')
  })

  it('opens on the remembered tab next time', async () => {
    window.localStorage.setItem(STORAGE_KEYS.timetableVehicleType, 'bus')
    const { wrapper, calls } = await mountView(TimetableHomeView, '/timetable', { handler })
    expect(calls).toEqual(['/api/v1/cities/alpha/lines/?vehicle_type=bus'])
    expect(wrapper.find('[role="tab"][aria-selected="true"]').text()).toBe('Buses')
  })

  it('prefers ?type= from the URL over the remembered tab', async () => {
    window.localStorage.setItem(STORAGE_KEYS.timetableVehicleType, 'bus')
    const { calls } = await mountView(TimetableHomeView, '/timetable?type=tram', { handler })
    expect(calls).toEqual(['/api/v1/cities/alpha/lines/?vehicle_type=tram'])
  })

  it('ignores a type the city does not have (URL and storage)', async () => {
    window.localStorage.setItem(STORAGE_KEYS.timetableVehicleType, 'metro')
    const { wrapper, calls } = await mountView(TimetableHomeView, '/timetable?type=rail', {
      handler,
    })
    expect(calls).toEqual(['/api/v1/cities/alpha/lines/?vehicle_type=tram'])
    expect(wrapper.findAll('[role="tab"]')).toHaveLength(2)
  })

  it('shows an error with retry when loading lines fails, then recovers', async () => {
    let fail = true
    const { wrapper, calls } = await mountView(TimetableHomeView, '/timetable', {
      handler: (url) => {
        if (!url.pathname.endsWith('/lines/')) return undefined
        return fail
          ? jsonResponse({ error: { code: 'server_error', message: 'x' } }, 500)
          : jsonResponse(linesFor('tram'))
      },
    })
    expect(wrapper.find('[role="alert"]').text()).toContain('Something went wrong')
    expect(wrapper.find('.line-grid').exists()).toBe(false)
    fail = false
    await wrapper.find('[role="alert"] button').trigger('click')
    await flushPromises()
    expect(calls).toHaveLength(2)
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.findAll('.line-grid__tile')).toHaveLength(1)
  })

  it('shows a loading status while lines are loading', async () => {
    let release: (r: Response) => void = () => {}
    const pending = new Promise<Response>((resolve) => (release = resolve))
    const { wrapper } = await mountView(TimetableHomeView, '/timetable', {
      handler: () => pending,
    })
    expect(wrapper.find('.load-status[role="status"]').text()).toBe('Loading lines…')
    release(jsonResponse(linesFor('tram')))
    await flushPromises()
    expect(wrapper.findAll('.line-grid__tile')).toHaveLength(1)
  })

  it('shows the empty state when the type has no lines', async () => {
    const { wrapper } = await mountView(TimetableHomeView, '/timetable', {
      handler: () => jsonResponse([]),
    })
    expect(wrapper.text()).toContain('No lines of this type.')
  })

  it('shows a message when the city has no vehicle types', async () => {
    const { wrapper, store, calls } = await mountView(TimetableHomeView, '/timetable', {
      details: false,
    })
    store.details = { ...cityDetail('alpha', 'en'), vehicle_types: [] } as CityDetail
    await flushPromises()
    expect(wrapper.text()).toContain('There are no timetables for this city yet.')
    expect(wrapper.findAll('[role="tab"]')).toHaveLength(0)
    expect(calls).toHaveLength(0)
  })

  it('shows a details error with retry instead of tabs when city details fail', async () => {
    const { wrapper, store } = await mountView(TimetableHomeView, '/timetable', { details: false })
    store.detailsError = new Error('x')
    await flushPromises()
    expect(wrapper.find('[role="alert"]').exists()).toBe(true)
    expect(wrapper.findAll('[role="tab"]')).toHaveLength(0)
  })

  it('translates visible text when the language switches', async () => {
    const { wrapper } = await mountView(TimetableHomeView, '/timetable', { handler })
    expect(wrapper.find('h1').text()).toBe('Timetables')
    applyLocale('pl')
    await flushPromises()
    expect(wrapper.find('h1').text()).toBe('Rozkłady jazdy')
    expect(wrapper.findAll('[role="tab"]')[0]!.text()).toBe('Tramwaje')
  })
})

describe('LineView', () => {
  const lineHandler =
    (r = route()): Handler =>
    (url) =>
      url.pathname.endsWith('/route/')
        ? jsonResponse({ ...r, direction: Number(url.searchParams.get('direction') ?? 0) })
        : undefined

  it('requests the route for the id in the URL (default direction, no date)', async () => {
    const { calls } = await mountView(LineView, '/timetable/lines/feed_a:7', {
      handler: lineHandler(),
    })
    expect(calls).toEqual(['/api/v1/cities/alpha/lines/feed_a%3A7/route/?direction=0'])
  })

  it('shows the headsign, the diagram and the direction toggle', async () => {
    const { wrapper } = await mountView(LineView, '/timetable/lines/feed_a:7', {
      handler: lineHandler(),
    })
    expect(wrapper.find('h1').text()).toContain('→ Southfield')
    expect(wrapper.findAll('.line-diagram__stop')).toHaveLength(3)
    const options = wrapper.findAll('.direction-toggle__option')
    expect(options.map((o) => o.text())).toEqual(['→ Southfield', '→ Northgate'])
    expect(options.map((o) => o.attributes('aria-pressed'))).toEqual(['true', 'false'])
  })

  it('hides the direction toggle for a loop line with one direction', async () => {
    const r = route({ directions: [{ direction: 0, headsign: 'Southfield' }] })
    const { wrapper } = await mountView(LineView, '/timetable/lines/feed_a:7', {
      handler: lineHandler(r),
    })
    expect(wrapper.find('.direction-toggle').exists()).toBe(false)
  })

  it('switching direction puts it in the URL and refetches', async () => {
    const { wrapper, router, calls } = await mountView(LineView, '/timetable/lines/feed_a:7', {
      handler: lineHandler(),
    })
    await wrapper.findAll('.direction-toggle__option')[1]!.trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query.direction).toBe('1')
    expect(calls[calls.length - 1]).toBe('/api/v1/cities/alpha/lines/feed_a%3A7/route/?direction=1')
    expect(wrapper.findAll('.direction-toggle__option')[1]!.attributes('aria-pressed')).toBe('true')
  })

  it('reads direction and date from the URL', async () => {
    const { calls } = await mountView(
      LineView,
      '/timetable/lines/feed_a:7?direction=1&date=2026-12-24',
      {
        handler: lineHandler(),
      },
    )
    expect(calls).toEqual([
      '/api/v1/cities/alpha/lines/feed_a%3A7/route/?direction=1&date=2026-12-24',
    ])
  })

  it('ignores an invalid date in the URL', async () => {
    const { calls } = await mountView(LineView, '/timetable/lines/feed_a:7?date=garbage', {
      handler: lineHandler(),
    })
    expect(calls[0]).not.toContain('date=')
  })

  it('tells the user when the API shifted to the next day with service', async () => {
    const r = route({ date: '2026-11-18' })
    const { wrapper } = await mountView(LineView, '/timetable/lines/feed_a:7?date=2026-11-16', {
      handler: lineHandler(r),
    })
    expect(wrapper.find('.line-view__notice').text()).toContain('The line does not run on')
    const none = await mountView(LineView, '/timetable/lines/feed_a:7?date=2026-11-16', {
      handler: lineHandler(),
    })
    expect(none.wrapper.find('.line-view__notice').exists()).toBe(false)
  })

  it('lists non-main variants in a collapsible block', async () => {
    const { wrapper } = await mountView(LineView, '/timetable/lines/feed_a:7', {
      handler: lineHandler(),
    })
    const details = wrapper.find('.line-view__variants')
    expect(details.text()).toContain('Route variants (1)')
    expect(details.text()).toContain('depot run')
    expect(details.text()).toContain('trips: 3')
  })

  it('shows the oppositeNotServed notice from the URL and removes it from the URL', async () => {
    const { wrapper, router } = await mountView(
      LineView,
      '/timetable/lines/feed_a:7?direction=1&notice=oppositeNotServed',
      { handler: lineHandler() },
    )
    expect(wrapper.text()).toContain('This stop is not served in the opposite direction.')
    expect(router.currentRoute.value.query.notice).toBeUndefined()
    expect(router.currentRoute.value.query.direction).toBe('1')
  })

  it('ignores an unknown notice value', async () => {
    const { wrapper } = await mountView(
      LineView,
      '/timetable/lines/feed_a:7?date=2026-11-16&notice=bogus',
      {
        handler: lineHandler(),
      },
    )
    expect(wrapper.find('.line-view__notice').exists()).toBe(false)
  })

  it('shows the line-specific not-found text on 404', async () => {
    const { wrapper } = await mountView(LineView, '/timetable/lines/ghost:1', { handler: notFound })
    expect(wrapper.find('[role="alert"]').text()).toContain(
      'This line was not found in the selected city.',
    )
    expect(wrapper.find('.line-diagram').exists()).toBe(false)
  })

  it('shows an error with retry on network failure and recovers on retry', async () => {
    let fail = true
    const { wrapper } = await mountView(LineView, '/timetable/lines/feed_a:7', {
      handler: (url) => {
        if (fail) throw new TypeError('failed to fetch')
        return lineHandler()(url)
      },
    })
    expect(wrapper.find('[role="alert"]').text()).toContain('Cannot reach the server')
    fail = false
    await wrapper.find('[role="alert"] button').trigger('click')
    await flushPromises()
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.find('.line-diagram').exists()).toBe(true)
  })

  it('shows a loading status first', async () => {
    let release: (r: Response) => void = () => {}
    const pending = new Promise<Response>((resolve) => (release = resolve))
    const { wrapper } = await mountView(LineView, '/timetable/lines/feed_a:7', {
      handler: () => pending,
    })
    expect(wrapper.find('[role="status"]').text()).toBe('Loading route…')
    release(jsonResponse(route()))
    await flushPromises()
    expect(wrapper.find('.line-diagram').exists()).toBe(true)
  })

  it('shows an empty message when the direction has no stops', async () => {
    const { wrapper } = await mountView(LineView, '/timetable/lines/feed_a:7', {
      handler: lineHandler(route({ stops: [], variants: [] })),
    })
    expect(wrapper.text()).toContain('No stops for this direction.')
  })

  it('stop links in the diagram keep direction and date', async () => {
    const { wrapper } = await mountView(
      LineView,
      '/timetable/lines/feed_a:7?direction=1&date=2026-12-24',
      {
        handler: lineHandler(),
      },
    )
    const href = wrapper.find('.line-diagram__name').attributes('href')!
    expect(href).toContain('/stops/feed_a:s1')
    expect(href).toContain('direction=1')
    expect(href).toContain('date=2026-12-24')
  })
})

describe('StopTimetableView', () => {
  const PATH = '/timetable/lines/feed_a:7/stops/feed_a:s2'
  const tt = () =>
    timetable({
      weekday: [dep('05:10'), dep('08:30'), dep('09:00', { markers: ['low_floor'] })],
      saturday: [dep('06:00')],
    })
  const ttHandler =
    (data = tt()): Handler =>
    (url) => {
      if (url.pathname.endsWith('/timetable/')) return jsonResponse(data)
      if (url.pathname.includes('/trips/')) return jsonResponse(trip())
      return undefined
    }

  it('requests the timetable with both ids encoded and renders the grid', async () => {
    const { wrapper, calls } = await mountView(StopTimetableView, PATH, { handler: ttHandler() })
    expect(calls).toEqual([
      '/api/v1/cities/alpha/lines/feed_a%3A7/stops/feed_a%3As2/timetable/?direction=0',
    ])
    expect(wrapper.find('h1').text()).toContain('Market Square')
    expect(wrapper.findAll('.tt-grid__col-head')).toHaveLength(3)
    expect(wrapper.find('.stop-tt__headsign').text()).toBe('→ Southfield')
  })

  it('highlights the next departure when the selected date is today in the city time zone', async () => {
    // 07:30 in Warsaw (UTC+1 in November) on 2026-11-16.
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-11-16T06:30:00Z'))
    const { wrapper } = await mountView(StopTimetableView, PATH, { handler: ttHandler() })
    expect(wrapper.find('.tt-grid__minute--next').attributes('aria-label')).toContain('08:30')
    expect(wrapper.findAll('.tt-grid__minute--past')).toHaveLength(1)
  })

  it('does not highlight next / past when a date other than today is selected', async () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-11-14T06:30:00Z'))
    const { wrapper } = await mountView(StopTimetableView, `${PATH}?date=2026-11-16`, {
      handler: ttHandler(),
    })
    expect(wrapper.find('.tt-grid__minute--next').exists()).toBe(false)
    expect(wrapper.find('.tt-grid__minute--past').exists()).toBe(false)
  })

  it('uses the city time zone for "today" around midnight UTC', async () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-11-15T23:30:00Z')) // already 2026-11-16 00:30 in Warsaw
    const { wrapper } = await mountView(StopTimetableView, PATH, { handler: ttHandler() })
    // Today in Warsaw is the 16th; it is before the first departure, so nothing is next or past.
    expect((wrapper.find('input[type="date"]').element as HTMLInputElement).value).toBe(
      '2026-11-16',
    )
    expect(wrapper.find('.tt-grid__minute--next').exists()).toBe(false)
    expect(wrapper.find('.tt-grid__minute--past').exists()).toBe(false)
  })

  it('changing the date puts it in the URL and refetches; picking today clears it', async () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-11-14T10:00:00Z'))
    const { wrapper, router, calls } = await mountView(StopTimetableView, PATH, {
      handler: ttHandler(),
    })
    await wrapper.find('input[type="date"]').setValue('2026-12-24')
    await flushPromises()
    expect(router.currentRoute.value.query.date).toBe('2026-12-24')
    expect(calls[calls.length - 1]).toContain('date=2026-12-24')
    await wrapper.find('.date-picker button').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query.date).toBeUndefined()
  })

  it('links to the previous and next stop, keeping the direction', async () => {
    const { wrapper } = await mountView(StopTimetableView, `${PATH}?direction=1`, {
      handler: ttHandler(),
    })
    const links = wrapper.findAll('.stop-tt__neighbour')
    expect(links.map((l) => l.text())).toEqual(
      expect.arrayContaining([
        expect.stringContaining('Old Mill'),
        expect.stringContaining('River Bridge'),
      ]),
    )
    expect(links[0]!.attributes('href')).toContain('/stops/feed_a:s1')
    expect(links[0]!.attributes('href')).toContain('direction=1')
  })

  it('omits the neighbour links at the ends of the line', async () => {
    const { wrapper } = await mountView(StopTimetableView, PATH, {
      handler: ttHandler(
        timetable({ previous_stop: null, next_stop: null, weekday: [dep('05:00')] }),
      ),
    })
    expect(wrapper.findAll('.stop-tt__neighbour')).toHaveLength(0)
  })

  it('opens the trip dialog on a minute click and requests the trip for that column date', async () => {
    const { wrapper, calls } = await mountView(StopTimetableView, PATH, { handler: ttHandler() })
    const sat = wrapper
      .findAll('.tt-grid__minute')
      .find((b) => b.attributes('aria-label')!.startsWith('06:00'))!
    await sat.trigger('click')
    await flushPromises()
    expect(calls[calls.length - 1]).toBe(
      '/api/v1/cities/alpha/trips/feed_a%3Atrip_06%3A00/?date=2026-11-21',
    )
    expect(wrapper.find('dialog').exists()).toBe(true)
    expect(wrapper.findAll('.trip-dialog__stop')).toHaveLength(3)
    await wrapper.find('.trip-dialog__close').trigger('click')
    await flushPromises()
    expect(wrapper.find('dialog').exists()).toBe(false)
  })

  it('opposite direction opens the same stop in the other direction when it is on that route', async () => {
    const other = route({
      direction: 1,
      stops: [{ ...route().stops[2]!, stop_id: 'feed_a:s2b', name: 'Market Square' }],
    })
    const { wrapper, router, calls } = await mountView(StopTimetableView, PATH, {
      handler: (url) => (url.pathname.endsWith('/route/') ? jsonResponse(other) : ttHandler()(url)),
    })
    await wrapper.findAll('.stop-tt__actions button')[0]!.trigger('click')
    await flushPromises()
    expect(calls.some((c) => c.includes('/route/?direction=1'))).toBe(true)
    expect(router.currentRoute.value.name).toBe('timetable-stop')
    expect(router.currentRoute.value.params.stopId).toBe('feed_a:s2b')
    expect(router.currentRoute.value.query.direction).toBe('1')
  })

  it('opposite direction falls back to the line diagram when the stop is not served', async () => {
    const other = route({ direction: 1, stops: [] })
    const { wrapper, router } = await mountView(StopTimetableView, PATH, {
      handler: (url) => (url.pathname.endsWith('/route/') ? jsonResponse(other) : ttHandler()(url)),
    })
    await wrapper.findAll('.stop-tt__actions button')[0]!.trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('timetable-line')
    expect(router.currentRoute.value.query.direction).toBe('1')
  })

  it('hides the opposite-direction button after a 404 for the other direction', async () => {
    const { wrapper } = await mountView(StopTimetableView, PATH, {
      handler: (url) => (url.pathname.endsWith('/route/') ? notFound() : ttHandler()(url)),
    })
    await wrapper.findAll('.stop-tt__actions button')[0]!.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('This line has no opposite direction.')
    expect(wrapper.text()).not.toContain('Opposite direction')
  })

  it('shows the stop-specific not-found text on 404', async () => {
    const { wrapper } = await mountView(StopTimetableView, PATH, { handler: notFound })
    expect(wrapper.find('[role="alert"]').text()).toContain(
      'This line does not stop here in this direction.',
    )
    expect(wrapper.find('.tt-grid').exists()).toBe(false)
  })

  it('shows an error with retry on server error', async () => {
    let fail = true
    const { wrapper } = await mountView(StopTimetableView, PATH, {
      handler: (url) =>
        fail
          ? jsonResponse({ error: { code: 'server_error', message: 'x' } }, 500)
          : ttHandler()(url),
    })
    expect(wrapper.find('[role="alert"]').exists()).toBe(true)
    fail = false
    await wrapper.find('[role="alert"] button').trigger('click')
    await flushPromises()
    expect(wrapper.find('.tt-grid').exists()).toBe(true)
  })

  it('shows the empty state for a timetable without departures', async () => {
    const { wrapper } = await mountView(StopTimetableView, PATH, {
      handler: ttHandler(timetable()),
    })
    expect(wrapper.text()).toContain('No departures in the next 14 days.')
  })

  it('refetches with the new language when nothing else changed: labels switch to Polish', async () => {
    const { wrapper } = await mountView(StopTimetableView, PATH, { handler: ttHandler() })
    expect(wrapper.find('.tt-grid__day').text()).toBe('Weekdays')
    applyLocale('pl')
    await flushPromises()
    expect(wrapper.find('.tt-grid__day').text()).toBe('Dni robocze')
  })
})
