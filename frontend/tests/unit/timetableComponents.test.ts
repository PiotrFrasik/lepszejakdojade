import { mount, flushPromises } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import LoadStatus from '@/components/LoadStatus.vue'
import LineBadge from '@/components/timetable/LineBadge.vue'
import LineDiagram from '@/components/timetable/LineDiagram.vue'
import LineGrid from '@/components/timetable/LineGrid.vue'
import ServiceDatePicker from '@/components/timetable/ServiceDatePicker.vue'
import TimetableGrid from '@/components/timetable/TimetableGrid.vue'
import TripDialog from '@/components/timetable/TripDialog.vue'
import VehicleTypeTabs from '@/components/timetable/VehicleTypeTabs.vue'
import { ApiError } from '@/api/client'
import { applyLocale, i18n } from '@/i18n'
import { routes } from '@/router'

import { jsonResponse, resetEnvironment } from './helpers'
import { GROUPS, dep, line, route, summary, timetable, trip } from './timetableFixtures'

function plugins() {
  const router = createRouter({ history: createMemoryHistory(), routes })
  return { global: { plugins: [createPinia(), i18n, router] } }
}

beforeEach(() => {
  resetEnvironment()
  applyLocale('en')
})
afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('LineBadge', () => {
  it('shows the short name in the line colours from the API', () => {
    const w = mount(LineBadge, {
      props: { line: summary({ short_name: 'N1', colour: '#aa0000', text_colour: '#000000' }) },
    })
    expect(w.text()).toBe('N1')
    const style = w.attributes('style')!
    expect(style).toContain('background-color: rgb(170, 0, 0)')
    expect(style).toContain('color: rgb(0, 0, 0)')
  })
})

function emittedLast(w: {
  emitted: (n: string) => unknown[][] | undefined
}): unknown[] | undefined {
  const all = w.emitted('update:modelValue') ?? []
  return all[all.length - 1]
}

describe('VehicleTypeTabs', () => {
  const props = {
    types: ['tram', 'bus'] as const,
    modelValue: 'tram' as const,
    panelId: 'p',
    idPrefix: 'x',
  }

  it('renders exactly the given vehicle types, translated, with the selected one marked', () => {
    const w = mount(VehicleTypeTabs, { props, ...plugins() })
    const tabs = w.findAll('[role="tab"]')
    expect(tabs.map((t) => t.text())).toEqual(['Trams', 'Buses'])
    expect(tabs.map((t) => t.attributes('aria-selected'))).toEqual(['true', 'false'])
    expect(tabs.map((t) => t.attributes('tabindex'))).toEqual(['0', '-1'])
  })

  it('emits the clicked type', async () => {
    const w = mount(VehicleTypeTabs, { props, ...plugins() })
    await w.findAll('[role="tab"]')[1]!.trigger('click')
    expect(w.emitted('update:modelValue')![0]).toEqual(['bus'])
  })

  it('moves with arrow keys, wrapping around, and Home / End', async () => {
    const w = mount(VehicleTypeTabs, { props, ...plugins() })
    const list = w.find('[role="tablist"]')
    await list.trigger('keydown', { key: 'ArrowLeft' })
    expect(emittedLast(w)).toEqual(['bus'])
    await list.trigger('keydown', { key: 'ArrowRight' })
    expect(emittedLast(w)).toEqual(['bus'])
    await list.trigger('keydown', { key: 'End' })
    expect(emittedLast(w)).toEqual(['bus'])
    await list.trigger('keydown', { key: 'Home' })
    expect(emittedLast(w)).toEqual(['tram'])
  })

  it('labels follow the UI language', async () => {
    const w = mount(VehicleTypeTabs, { props, ...plugins() })
    applyLocale('pl')
    await w.vm.$nextTick()
    expect(w.findAll('[role="tab"]').map((t) => t.text())).toEqual(['Tramwaje', 'Autobusy'])
  })
})

describe('LineGrid', () => {
  const lines = [
    line({ id: 'f:2', short_name: '2', long_name: 'Lake - Hill' }),
    line({
      id: 'f:10',
      short_name: '10',
      long_name: 'Żółć Park - Źródło',
      colour: '#00ff00',
      text_colour: '#000000',
    }),
    line({ id: 'f:50', short_name: '50', long_name: 'Station - Depot' }),
    line({
      id: 'f:N1',
      short_name: 'N1',
      group: 'night',
      long_name: 'Night loop',
      colour: '#222222',
    }),
  ]

  function mountGrid(ls = lines) {
    return mount(LineGrid, { props: { lines: ls, groups: GROUPS }, ...plugins() })
  }
  const tiles = (w: ReturnType<typeof mountGrid>) => w.findAll('.line-grid__tile')

  it('groups lines in group order and keeps the API order inside a group', () => {
    const w = mountGrid()
    expect(w.findAll('h2').map((h) => h.text())).toEqual(['Day lines', 'Night lines'])
    expect(tiles(w).map((t) => t.text())).toEqual(['2', '10', '50', 'N1'])
  })

  it('colours each group heading and each tile from the data', () => {
    const w = mountGrid()
    expect(w.find('h2').attributes('style')).toContain('border-left-color: rgb(17, 34, 51)')
    expect(tiles(w)[1]!.attributes('style')).toContain('background-color: rgb(0, 255, 0)')
  })

  it('links a tile to the line page with the id as a single path segment', async () => {
    const p = plugins()
    const w = mount(LineGrid, { props: { lines, groups: GROUPS }, ...p })
    const router = p.global.plugins[2] as ReturnType<typeof createRouter>
    expect(router.resolve({ name: 'timetable-line', params: { lineId: 'f:10' } }).href).toBe(
      '/timetable/lines/f:10',
    )
    expect(tiles(w)[1]!.attributes('href')).toBe('/timetable/lines/f:10')
  })

  it('filters by line number prefix', async () => {
    const w = mountGrid()
    await w.find('input[type="search"]').setValue('1')
    expect(tiles(w).map((t) => t.text())).toEqual(['10'])
    await w.find('input[type="search"]').setValue('5')
    expect(tiles(w).map((t) => t.text())).toEqual(['50'])
  })

  it('searches the long name ignoring accents and case', async () => {
    const w = mountGrid()
    await w.find('input[type="search"]').setValue('zolc')
    expect(tiles(w).map((t) => t.text())).toEqual(['10'])
    await w.find('input[type="search"]').setValue('ŹRÓDŁO')
    expect(tiles(w).map((t) => t.text())).toEqual(['10'])
  })

  it('hides groups with no matching lines', async () => {
    const w = mountGrid()
    await w.find('input[type="search"]').setValue('night')
    expect(w.findAll('h2').map((h) => h.text())).toEqual(['Night lines'])
  })

  it('shows a "no results" message with the query, and an empty message without lines', async () => {
    const w = mountGrid()
    await w.find('input[type="search"]').setValue('zzz')
    expect(tiles(w)).toHaveLength(0)
    expect(w.text()).toContain('No lines match “zzz”.')
    expect(mountGrid([]).text()).toContain('No lines of this type.')
  })

  it('shows the notice badge only for lines with a non-null notice', () => {
    const w = mountGrid([
      line({ id: 'f:1', short_name: '1', notice: null }),
      line({ id: 'f:3', short_name: '3', notice: { kind: 'detour', text: 'Bridge works' } }),
    ])
    const [plain, flagged] = tiles(w)
    expect(plain!.find('.line-grid__notice').exists()).toBe(false)
    expect(flagged!.find('.line-grid__notice').exists()).toBe(true)
    expect(flagged!.attributes('aria-label')).toContain('Detour: Bridge works')
  })

  it('puts a line of an unknown group into the first group', () => {
    const w = mountGrid([line({ id: 'f:9', short_name: '9', group: 'ghost' })])
    expect(w.findAll('h2').map((h) => h.text())).toEqual(['Day lines'])
    expect(tiles(w)).toHaveLength(1)
  })
})

describe('LineDiagram', () => {
  function mountDiagram(r = route(), highlighted: string | null = null) {
    return mount(LineDiagram, {
      props: {
        route: r,
        highlightedStopId: highlighted,
        stopLink: (id: string) => ({
          name: 'timetable-stop',
          params: { lineId: r.line.id, stopId: id },
        }),
      },
      ...plugins(),
    })
  }

  it('lists the stops in order, each linking to its timetable', () => {
    const w = mountDiagram()
    expect(w.findAll('.line-diagram__name').map((a) => a.text().replace(/\s+/g, ' '))).toEqual([
      'Old Mill 01',
      'Depot Gate',
      'Market Square',
    ])
    expect(w.findAll('.line-diagram__name')[0]!.attributes('href')).toBe(
      '/timetable/lines/feed_a:7/stops/feed_a:s1',
    )
  })

  it('marks variant-only stops and no others', () => {
    const w = mountDiagram()
    const stops = w.findAll('.line-diagram__stop')
    expect(stops.map((s) => s.classes('line-diagram__stop--variant'))).toEqual([false, true, false])
    expect(stops[1]!.text()).toContain('some trips only')
    expect(stops[0]!.text()).not.toContain('some trips only')
  })

  it('shows transfer chips linking to the other line, and none when there are no transfers', () => {
    const w = mountDiagram()
    const stops = w.findAll('.line-diagram__stop')
    const chip = stops[0]!.find('.line-diagram__transfer')
    expect(chip.text()).toBe('12')
    expect(chip.attributes('href')).toBe('/timetable/lines/feed_b:12')
    expect(stops[2]!.find('.line-diagram__transfers').exists()).toBe(false)
  })

  it('marks where a non-main variant ends away from the main end', () => {
    const w = mountDiagram()
    const stops = w.findAll('.line-diagram__stop')
    expect(stops[1]!.find('.line-diagram__marks').text()).toBe('ends here: depot run → Depot')
    expect(stops[0]!.find('.line-diagram__marks').exists()).toBe(false)
  })

  it('shows the wheelchair icon only for accessible stops', () => {
    const w = mountDiagram()
    const stops = w.findAll('.line-diagram__stop')
    expect(stops[0]!.find('.line-diagram__icon').exists()).toBe(true)
    expect(stops[1]!.find('.line-diagram__icon').exists()).toBe(false)
    expect(stops[2]!.find('.line-diagram__icon').exists()).toBe(false)
  })

  it('highlights the current stop', () => {
    const w = mountDiagram(route(), 'feed_a:s2')
    const current = w.findAll('.line-diagram__stop--current')
    expect(current).toHaveLength(1)
    expect(current[0]!.text()).toContain('Market Square')
  })
})

describe('ServiceDatePicker', () => {
  it('emits a valid date from the input and ignores an empty one', async () => {
    const w = mount(ServiceDatePicker, {
      props: { modelValue: '2026-11-16', today: '2026-11-14' },
      ...plugins(),
    })
    const input = w.find('input[type="date"]')
    await input.setValue('2026-12-24')
    expect(w.emitted('update:modelValue')).toEqual([['2026-12-24']])
    await input.setValue('')
    expect(w.emitted('update:modelValue')).toHaveLength(1)
  })

  it('resets the input to the current date when it is cleared', async () => {
    const w = mount(ServiceDatePicker, {
      props: { modelValue: '2026-11-16', today: '2026-11-14' },
      ...plugins(),
    })
    const input = w.find('input[type="date"]')
    await input.setValue('')
    expect(w.emitted('update:modelValue')).toBeUndefined()
    expect((input.element as HTMLInputElement).value).toBe('2026-11-16')
  })

  it('"today" button jumps to today and is disabled when already on today', async () => {
    const w = mount(ServiceDatePicker, {
      props: { modelValue: '2026-11-16', today: '2026-11-14' },
      ...plugins(),
    })
    const button = w.find('button')
    expect(button.attributes('disabled')).toBeUndefined()
    await button.trigger('click')
    expect(w.emitted('update:modelValue')).toEqual([['2026-11-14']])
    await w.setProps({ modelValue: '2026-11-14' })
    expect(w.find('button').attributes('disabled')).toBeDefined()
  })

  it('spells the date out in the UI language', async () => {
    const w = mount(ServiceDatePicker, {
      props: { modelValue: '2026-11-16', today: '2026-11-14' },
      ...plugins(),
    })
    expect(w.find('.date-picker__long').text()).toContain('November')
    applyLocale('pl')
    await w.vm.$nextTick()
    expect(w.find('.date-picker__long').text()).toContain('listopada')
  })
})

describe('TimetableGrid', () => {
  const NOW_TODAY = '2026-11-16'

  function mountGrid(tt = timetable(), now = 8 * 60, today = NOW_TODAY) {
    return mount(TimetableGrid, { props: { timetable: tt, today, nowMinutes: now }, ...plugins() })
  }

  const baseWeekday = [dep('05:10'), dep('05:40'), dep('08:00'), dep('09:15')]

  it('renders three columns in the order weekday, saturday, sunday', () => {
    const w = mountGrid(
      timetable({ weekday: baseWeekday, saturday: [dep('06:00')], sunday: [dep('07:00')] }),
    )
    const heads = w.findAll('.tt-grid__col-head')
    expect(heads).toHaveLength(3)
    expect(heads.map((h) => h.find('.tt-grid__day').text())).toEqual([
      'Weekdays',
      'Saturdays',
      'Sundays & holidays',
    ])
  })

  it('highlights only the column of the selected day type', () => {
    const w = mountGrid(
      timetable({
        day_type: 'sunday',
        date: '2026-11-22',
        weekday: baseWeekday,
        sunday: [dep('07:00')],
      }),
      0,
    )
    const heads = w.findAll('.tt-grid__col-head')
    expect(heads.map((h) => h.classes('tt-grid__active'))).toEqual([false, false, true])
    const cells = w.findAll('tbody tr')[0]!.findAll('td')
    expect(cells.map((c) => c.classes('tt-grid__active'))).toEqual([false, false, true])
  })

  it('shows minutes as two digits grouped under their hour row', () => {
    const w = mountGrid(timetable({ weekday: [dep('05:05'), dep('05:40')] }))
    const row = w.findAll('tbody tr')[0]!
    expect(row.find('th').text()).toBe('05')
    expect(
      row
        .findAll('td')[0]!
        .findAll('.tt-grid__mm')
        .map((m) => m.text()),
    ).toEqual(['05', '40'])
  })

  it('highlights the next departure and dims past ones when the date is today', () => {
    const w = mountGrid(timetable({ weekday: baseWeekday }), 8 * 60)
    const all = w.findAll('.tt-grid__minute')
    expect(all.map((b) => b.classes('tt-grid__minute--past'))).toEqual([true, true, false, false])
    expect(all.map((b) => b.classes('tt-grid__minute--next'))).toEqual([false, false, true, false])
    expect(w.find('.tt-grid__next').text()).toContain('08:00')
  })

  it('treats a departure at exactly the current minute as next, not past', () => {
    const w = mountGrid(timetable({ weekday: baseWeekday }), 8 * 60)
    const at = w.findAll('.tt-grid__minute')[2]!
    expect(at.classes('tt-grid__minute--next')).toBe(true)
    expect(at.classes('tt-grid__minute--past')).toBe(false)
  })

  it('has no next / past highlighting when the selected date is not today', () => {
    const w = mountGrid(timetable({ weekday: baseWeekday }), 8 * 60, '2026-11-14')
    expect(w.find('.tt-grid__minute--next').exists()).toBe(false)
    expect(w.find('.tt-grid__minute--past').exists()).toBe(false)
    expect(w.find('.tt-grid__next').exists()).toBe(false)
  })

  it('has no next departure after the last one of the day', () => {
    const w = mountGrid(timetable({ weekday: baseWeekday }), 23 * 60)
    expect(w.find('.tt-grid__minute--next').exists()).toBe(false)
    expect(w.findAll('.tt-grid__minute--past')).toHaveLength(4)
  })

  it('a next_day departure counts as later than any same-day departure', () => {
    const w = mountGrid(
      timetable({ weekday: [dep('23:50'), dep('00:15', { next_day: true })] }),
      23 * 60 + 55,
    )
    const next = w.find('.tt-grid__minute--next')
    expect(next.exists()).toBe(true)
    expect(next.attributes('aria-label')).toContain('00:15')
    expect(w.find('.tt-grid__minute--past').attributes('aria-label')).toContain('23:50')
  })

  it('orders after-midnight hours after hour 23', () => {
    const w = mountGrid(
      timetable({ weekday: [dep('23:50'), dep('00:15', { next_day: true }), dep('05:00')] }),
      0,
    )
    expect(w.findAll('tbody th').map((h) => h.text())).toEqual(['05', '23', '00'])
  })

  it('merges hours from all columns into one row set', () => {
    const w = mountGrid(timetable({ weekday: [dep('05:00')], saturday: [dep('07:00')] }))
    expect(w.findAll('tbody th').map((h) => h.text())).toEqual(['05', '07'])
    const row05 = w.findAll('tbody tr')[0]!.findAll('td')
    expect(row05.map((c) => c.findAll('button').length)).toEqual([1, 0, 0])
  })

  it('marks low-floor departures and lists them in the legend only when present', () => {
    const w = mountGrid(
      timetable({ weekday: [dep('05:00', { markers: ['low_floor'] }), dep('05:30')] }),
    )
    const buttons = w.findAll('.tt-grid__minute')
    expect(buttons.map((b) => b.classes('tt-grid__minute--low-floor'))).toEqual([true, false])
    expect(w.find('.tt-grid__legend').text()).toContain('low-floor')
    const none = mountGrid(timetable({ weekday: [dep('05:00')] }))
    expect(none.find('.tt-grid__legend').text()).not.toContain('low-floor')
  })

  it('shows variant letters and a legend entry naming the variant headsign', () => {
    const w = mountGrid(
      timetable({
        weekday: [dep('05:00'), dep('05:30', { markers: ['short_turn'], variant: 'v2' })],
        variants: [{ id: 'v2', kind: 'short_turn', headsign: 'Turnaround' }],
      }),
    )
    const letters = w.findAll('.tt-grid__letter')
    expect(letters).toHaveLength(1)
    expect(letters[0]!.text()).toBe('a')
    expect(w.find('.tt-grid__legend').text()).toContain('short turn → Turnaround')
  })

  it('emits select with the departure and the date of its column', async () => {
    const w = mountGrid(timetable({ weekday: [dep('05:00')], saturday: [dep('06:00')] }))
    const buttons = w.findAll('.tt-grid__minute')
    await buttons[1]!.trigger('click')
    const [departure, date] = w.emitted('select')![0] as [{ time: string }, string]
    expect(departure.time).toBe('06:00')
    expect(date).toBe('2026-11-21')
  })

  it('shows an empty state when no column has departures, and "no service" for empty columns', () => {
    const empty = mountGrid(timetable())
    expect(empty.text()).toContain('No departures in the next 14 days.')
    expect(empty.find('table').exists()).toBe(false)
    const partial = mountGrid(timetable({ weekday: [dep('05:00')] }))
    expect(partial.text().match(/no service/g)).toHaveLength(2)
  })

  it('uses fake timers consistently: the clock does not change a rendered grid by itself', async () => {
    vi.useFakeTimers()
    const w = mountGrid(timetable({ weekday: baseWeekday }), 8 * 60)
    vi.advanceTimersByTime(60 * 60 * 1000)
    await w.vm.$nextTick()
    expect(w.find('.tt-grid__minute--next').exists()).toBe(true)
  })
})

describe('TripDialog', () => {
  function stubFetch(handler: (url: string) => Response | Promise<Response>) {
    const fn = vi.fn(async (input: RequestInfo | URL) => handler(String(input)))
    vi.stubGlobal('fetch', fn)
    return fn
  }

  function mountDialog() {
    return mount(TripDialog, {
      props: {
        city: 'alpha',
        tripId: 'feed_a:trip_1',
        date: '2026-11-16',
        currentStopId: 'feed_a:s2',
        stopLink: (id: string) => ({
          name: 'timetable-stop',
          params: { lineId: 'feed_a:7', stopId: id },
        }),
      },
      attachTo: document.body,
      ...plugins(),
    })
  }

  beforeEach(() => {
    // jsdom does not implement <dialog> methods.
    HTMLDialogElement.prototype.showModal ??= function (this: HTMLDialogElement) {
      this.setAttribute('open', '')
    }
    HTMLDialogElement.prototype.close ??= function (this: HTMLDialogElement) {
      this.removeAttribute('open')
    }
  })

  it('requests the trip with an encoded id and the date, then lists all stops', async () => {
    const fn = stubFetch(() => jsonResponse(trip()))
    const w = mountDialog()
    await flushPromises()
    expect(fn.mock.calls[0]![0]).toBe('/api/v1/cities/alpha/trips/feed_a%3Atrip_1/?date=2026-11-16')
    expect(w.findAll('.trip-dialog__name').map((a) => a.text())).toEqual([
      'Old Mill',
      'Market Square',
      'River Bridge',
    ])
    w.unmount()
  })

  it('highlights the current stop, dims earlier ones and shows a dash for missing times', async () => {
    stubFetch(() => jsonResponse(trip()))
    const w = mountDialog()
    await flushPromises()
    const stops = w.findAll('.trip-dialog__stop')
    expect(stops.map((s) => s.classes('trip-dialog__stop--before'))).toEqual([true, false, false])
    expect(stops.map((s) => s.classes('trip-dialog__stop--current'))).toEqual([false, true, false])
    expect(stops[2]!.find('.trip-dialog__time').text()).toBe('–')
    expect(stops[1]!.find('.trip-dialog__time').text()).toBe('05:12')
    w.unmount()
  })

  it('shows the accessibility note only when the vehicle is accessible', async () => {
    stubFetch(() => jsonResponse(trip({ wheelchair_accessible: false })))
    const w = mountDialog()
    await flushPromises()
    expect(w.find('.trip-dialog__meta').text()).not.toContain('wheelchair')
    w.unmount()
  })

  it('shows the not-found text on 404 and offers a retry that refetches', async () => {
    let calls = 0
    const fn = stubFetch(() => {
      calls++
      return calls === 1
        ? jsonResponse({ error: { code: 'not_found', message: 'x' } }, 404)
        : jsonResponse(trip())
    })
    const w = mountDialog()
    await flushPromises()
    expect(w.find('[role="alert"]').text()).toContain('This trip does not run on the selected day.')
    await w.find('[role="alert"] button').trigger('click')
    await flushPromises()
    expect(fn).toHaveBeenCalledTimes(2)
    expect(w.find('[role="alert"]').exists()).toBe(false)
    expect(w.findAll('.trip-dialog__stop')).toHaveLength(3)
    w.unmount()
  })

  it('emits close from the close button and on Escape (cancel)', async () => {
    stubFetch(() => jsonResponse(trip()))
    const w = mountDialog()
    await flushPromises()
    await w.find('.trip-dialog__close').trigger('click')
    expect(w.emitted('close')).toHaveLength(1)
    await w.find('dialog').trigger('cancel')
    expect(w.emitted('close')).toHaveLength(2)
    w.unmount()
  })
})

describe('LoadStatus', () => {
  const mountStatus = (props: Record<string, unknown>) => mount(LoadStatus, { props, ...plugins() })

  it('renders nothing when neither loading nor error', () => {
    expect(mountStatus({}).html()).toBe('<!--v-if-->')
  })

  it('shows a loading status, with custom text when given', () => {
    expect(mountStatus({ loading: true }).find('[role="status"]').text()).toBe('Loading…')
    expect(mountStatus({ loading: true, loadingText: 'Wait' }).text()).toBe('Wait')
  })

  it.each([
    [new ApiError(404, 'not_found', 'x'), 'Not found.'],
    [
      new ApiError(0, 'network_error', 'x'),
      'Cannot reach the server. Check your connection and try again.',
    ],
    [new ApiError(429, 'rate_limited', 'x'), 'Too many requests. Wait a moment and try again.'],
    [new ApiError(500, 'server_error', 'x'), 'Something went wrong. Please try again.'],
    [new Error('boom'), 'Something went wrong. Please try again.'],
  ])('maps %o to its translated text', (error, text) => {
    expect(mountStatus({ error }).find('[role="alert"]').text()).toContain(text)
  })

  it('uses notFoundText for 404 and emits retry', async () => {
    const w = mountStatus({
      error: new ApiError(404, 'not_found', 'x'),
      notFoundText: 'Custom missing',
    })
    expect(w.text()).toContain('Custom missing')
    await w.find('button').trigger('click')
    expect(w.emitted('retry')).toHaveLength(1)
  })

  it('error text follows the UI language without a new request', async () => {
    const w = mountStatus({ error: new ApiError(500, 'server_error', 'x') })
    applyLocale('pl')
    await w.vm.$nextTick()
    expect(w.find('.load-status__text').text()).not.toBe('Something went wrong. Please try again.')
    expect(w.find('button').text()).toBe(i18n.global.t('errors.retry'))
  })
})
