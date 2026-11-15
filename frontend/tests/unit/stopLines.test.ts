import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'

import StopLines from '@/components/timetable/StopLines.vue'
import { applyLocale, i18n } from '@/i18n'
import { routes } from '@/router'
import type { StopLine, VehicleType } from '@/types/api'

import { resetEnvironment } from './helpers'
import { stopLine } from './stopOverviewFixtures'
import { summary } from './timetableFixtures'

const tram7 = stopLine()
const bus100 = stopLine({
  line: summary({ id: 'feed_a:100', short_name: '100', vehicle_type: 'bus' }),
  directions: [{ direction: 0, headsign: 'Westend', platform_id: 'feed_a:stop_1' }],
})

async function mountLines(lines: StopLine[], typeOrder?: VehicleType[]) {
  const router = createRouter({ history: createMemoryHistory(), routes })
  await router.push('/')
  await router.isReady()
  return mount(StopLines, {
    props: { lines, ...(typeOrder ? { typeOrder } : {}) },
    global: { plugins: [i18n, router] },
  })
}

beforeEach(() => {
  resetEnvironment()
  applyLocale('en')
})

describe('StopLines', () => {
  it('shows tabs only for the vehicle types present at the stop', async () => {
    const wrapper = await mountLines([tram7, bus100], ['tram', 'bus'])
    const tabs = wrapper.findAll('[role="tab"]')
    expect(tabs.map((t) => t.text())).toEqual(['Trams', 'Buses'])
  })

  it('follows the city type order, then appends unlisted types', async () => {
    const wrapper = await mountLines([tram7, bus100], ['bus'])
    expect(wrapper.findAll('[role="tab"]').map((t) => t.text())).toEqual(['Buses', 'Trams'])
  })

  it('shows only the lines of the first tab and switches on click', async () => {
    const wrapper = await mountLines([tram7, bus100], ['tram', 'bus'])
    expect(wrapper.findAll('[data-testid="stop-line"]')).toHaveLength(1)
    expect(wrapper.text()).toContain('Southfield')
    expect(wrapper.text()).not.toContain('Westend')
    await wrapper.findAll('[role="tab"]')[1]!.trigger('click')
    expect(wrapper.findAll('[data-testid="stop-line"]')).toHaveLength(1)
    expect(wrapper.text()).toContain('Westend')
    expect(wrapper.text()).not.toContain('Southfield')
    expect(wrapper.findAll('[role="tab"]')[1]!.attributes('aria-selected')).toBe('true')
  })

  it('renders a line badge with the short name', async () => {
    const wrapper = await mountLines([tram7])
    expect(wrapper.find('[data-testid="stop-line"]').text()).toContain('7')
  })

  it('gives each direction link an accessible name with line and headsign (en)', async () => {
    const wrapper = await mountLines([tram7])
    const links = wrapper.findAll('[data-testid="stop-line-direction"]')
    expect(links).toHaveLength(2)
    expect(links[0]!.text().replace(/\s+/g, ' ')).toContain('Line 7 towards Southfield')
    expect(links[1]!.text().replace(/\s+/g, ' ')).toContain('Line 7 towards Eastbrook')
  })

  it('gives each direction link an accessible name in Polish', async () => {
    applyLocale('pl')
    const wrapper = await mountLines([tram7])
    const link = wrapper.find('[data-testid="stop-line-direction"]')
    expect(link.text().replace(/\s+/g, ' ')).toContain('Linia 7 w kierunku Southfield')
    expect(wrapper.find('[role="tablist"]').attributes('aria-label')).toBe('Rodzaj pojazdu')
    expect(wrapper.findAll('[role="tab"]')[0]!.text()).toBe('Tramwaje')
  })

  it('links direction 0 to the stop timetable without a query', async () => {
    const wrapper = await mountLines([tram7])
    const href = wrapper.findAll('[data-testid="stop-line-direction"]')[0]!.attributes('href')
    expect(href).toBe('/timetable/lines/feed_a:7/stops/feed_a:stop_1')
  })

  it('links direction 1 with ?direction=1 and the encoded platform id', async () => {
    const wrapper = await mountLines([tram7])
    const href = wrapper.findAll('[data-testid="stop-line-direction"]')[1]!.attributes('href')
    expect(href).toBe('/timetable/lines/feed_a:7/stops/feed_b:stop%202?direction=1')
  })

  it('renders nothing (no tabs, no lines) for an empty list', async () => {
    const wrapper = await mountLines([])
    expect(wrapper.find('[role="tablist"]').exists()).toBe(false)
    expect(wrapper.findAll('[data-testid="stop-line"]')).toHaveLength(0)
  })

  it('falls back to the first tab when the selected type disappears', async () => {
    const wrapper = await mountLines([tram7, bus100], ['tram', 'bus'])
    await wrapper.findAll('[role="tab"]')[1]!.trigger('click')
    await wrapper.setProps({ lines: [tram7] })
    expect(wrapper.findAll('[role="tab"]')).toHaveLength(1)
    expect(wrapper.text()).toContain('Southfield')
  })
})
