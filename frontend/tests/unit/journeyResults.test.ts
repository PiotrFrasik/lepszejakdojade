import { flushPromises } from '@vue/test-utils'
import { nextTick } from 'vue'

import { ApiError } from '@/api/client'
import BottomTabBar from '@/components/BottomTabBar.vue'
import ItineraryCard from '@/components/journey/ItineraryCard.vue'
import JourneyResults from '@/components/journey/JourneyResults.vue'
import { applyLocale } from '@/i18n'
import en from '@/locales/en.json'
import pl from '@/locales/pl.json'
import { useCityStore } from '@/stores/city'
import { useJourneyStore } from '@/stores/journey'
import HomeView from '@/views/HomeView.vue'

import { jsonResponse, mountApp, resetEnvironment } from './helpers'
import { journeyItinerary, journeyResponse } from './journeyFixtures'

const fetchMock = vi.fn()

beforeEach(() => {
  resetEnvironment()
  fetchMock.mockReset()
  fetchMock.mockImplementation(async () => jsonResponse([]))
  vi.stubGlobal('fetch', fetchMock)
})
afterEach(() => vi.unstubAllGlobals())

const fromPlace = { source: 'map', name: null, lat: 50.06, lon: 19.93 } as const
const toPlace = { source: 'map', name: null, lat: 50.02, lon: 19.89 } as const

async function mountResults(searchResponse: Response | Error) {
  fetchMock.mockImplementation(async () => {
    if (searchResponse instanceof Error) throw searchResponse
    return searchResponse.clone()
  })
  const mounted = await mountApp(JourneyResults)
  useCityStore().cityId = 'alpha'
  const journey = useJourneyStore()
  journey.setPlace('from', fromPlace)
  journey.setPlace('to', toPlace)
  await journey.search()
  await flushPromises()
  return { ...mounted, journey }
}

describe('JourneyResults', () => {
  it('lists connections and announces the count', async () => {
    const { wrapper } = await mountResults(jsonResponse(journeyResponse()))
    expect(wrapper.findAll('.itinerary')).toHaveLength(2)
    expect(wrapper.find('[role="status"]').text()).toBe(
      pl.journey.results.count.replace('{count}', '2'),
    )
  })

  it('shows the empty state for a 200 with no itineraries', async () => {
    const { wrapper } = await mountResults(jsonResponse(journeyResponse({ itineraries: [] })))
    expect(wrapper.text()).toContain(pl.journey.results.empty)
    expect(wrapper.findAll('.itinerary')).toHaveLength(0)
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  })

  it('shows the planner-unavailable message on 503 and offers a retry', async () => {
    const { wrapper } = await mountResults(
      jsonResponse({ error: { code: 'journey_planner_unavailable', message: 'Server text' } }, 503),
    )
    const alert = wrapper.find('[role="alert"]')
    expect(alert.text()).toContain(pl.journey.results.unavailable)
    expect(alert.text()).not.toContain('Server text')
    expect(alert.text()).toContain(pl.errors.retry)
    const before = fetchMock.mock.calls.length
    await alert.find('button').trigger('click')
    await flushPromises()
    expect(fetchMock.mock.calls.length).toBe(before + 1)
  })

  it('shows the network message when the server cannot be reached', async () => {
    const { wrapper } = await mountResults(new TypeError('offline'))
    expect(wrapper.find('[role="alert"]').text()).toContain(pl.errors.network)
  })

  it('shows the rate limit and generic messages', async () => {
    const { wrapper, journey } = await mountResults(jsonResponse({}, 429))
    expect(wrapper.find('[role="alert"]').text()).toContain(pl.errors.rateLimited)
    journey.error = new ApiError(500, 'http_error', 'boom')
    await nextTick()
    expect(wrapper.find('[role="alert"]').text()).toContain(pl.errors.generic)
  })

  it('shows the API message on 400 (already translated by the backend)', async () => {
    const { wrapper } = await mountResults(
      jsonResponse({ error: { code: 'validation_error', message: 'Punkt poza miastem.' } }, 400),
    )
    expect(wrapper.find('[role="alert"]').text()).toContain('Punkt poza miastem.')
  })

  it('renders walk and bike comparison values', async () => {
    const { wrapper } = await mountResults(jsonResponse(journeyResponse()))
    const text = wrapper.find('.journey-results__comparison').text()
    expect(text).toContain(pl.journey.comparison.walk)
    expect(text).toContain(pl.journey.comparison.bike)
    expect(text).toMatch(/1 h 5 min/)
    expect(text).toMatch(/21 min/)
  })

  it('shows "not available" for a null walk or bike comparison', async () => {
    const { wrapper } = await mountResults(
      jsonResponse(journeyResponse({ comparison: { walk: null, bike: null } })),
    )
    const values = wrapper.findAll('.journey-results__comparison dd').map((d) => d.text())
    expect(values).toEqual([pl.journey.comparison.unavailable, pl.journey.comparison.unavailable])
  })

  it('does not break when the comparison object is missing', async () => {
    const body = journeyResponse() as unknown as Record<string, unknown>
    delete body.comparison
    const { wrapper } = await mountResults(jsonResponse(body))
    expect(wrapper.findAll('.itinerary')).toHaveLength(2)
    expect(wrapper.find('.journey-results__comparison').exists()).toBe(false)
  })

  it('selects and expands a connection on click, collapsing it on a second click', async () => {
    const { wrapper, journey } = await mountResults(jsonResponse(journeyResponse()))
    const summaries = wrapper.findAll('.itinerary__summary')
    await summaries[1]!.trigger('click')
    expect(journey.selectedItinerary?.id).toBe('i2')
    expect(wrapper.findAll('.itinerary__legs')).toHaveLength(1)
    await summaries[1]!.trigger('click')
    expect(wrapper.findAll('.itinerary__legs')).toHaveLength(0)
  })

  it('goes back to the search panel with the close button', async () => {
    const { wrapper, journey } = await mountResults(jsonResponse(journeyResponse()))
    await wrapper.find('.journey-results__close').trigger('click')
    expect(journey.status).toBe('idle')
    expect(journey.result).toBeNull()
  })

  it('switches visible text to English', async () => {
    const { wrapper } = await mountResults(jsonResponse(journeyResponse()))
    applyLocale('en')
    await nextTick()
    expect(wrapper.text()).toContain(en.journey.results.title)
    expect(wrapper.text()).toContain(en.journey.comparison.title)
    expect(wrapper.text()).not.toContain(pl.journey.comparison.title)
  })
})

describe('ItineraryCard', () => {
  const mountCard = (props: Record<string, unknown> = {}) =>
    mountApp(ItineraryCard, {
      props: { itinerary: journeyItinerary(), index: 0, selected: false, expanded: true, ...props },
    })

  it('summarises times, duration, transfers and walking', async () => {
    const { wrapper } = await mountCard({ expanded: false })
    const text = wrapper.find('.itinerary__summary').text()
    expect(text).toContain('08:03 – 08:20')
    expect(text).toContain('17 min')
    expect(text).toContain(pl.journey.itinerary.noTransfers)
    expect(text).toContain('300 m')
    expect(wrapper.find('.line-badge').text()).toBe('52')
    expect(wrapper.find('article').attributes('aria-label')).toBe(
      'Połączenie 1: od 08:03 do 08:20, 17 min',
    )
  })

  it('shows the transfer count when there are transfers', async () => {
    const { wrapper } = await mountCard({
      itinerary: journeyItinerary({ transfers: 2 }),
      expanded: false,
    })
    expect(wrapper.find('.itinerary__meta').text()).toContain(
      pl.journey.itinerary.transfers.replace('{count}', '2'),
    )
  })

  it('links a transit leg to the line timetable', async () => {
    const { wrapper } = await mountCard()
    const link = wrapper.find('a.itinerary__line-link')
    expect(link.attributes('href')).toBe('/timetable/lines/feed_a:52')
    expect(link.attributes('aria-label')).toBe(pl.journey.leg.lineLink.replace('{line}', '52'))
  })

  it('navigates to the line timetable when the link is clicked', async () => {
    const { wrapper, router } = await mountCard()
    await wrapper.find('a.itinerary__line-link').trigger('click')
    await vi.waitFor(() =>
      expect(router.currentRoute.value.path).toBe('/timetable/lines/feed_a:52'),
    )
  })

  it('lists walking, transit leg details, intermediate stops and the end place', async () => {
    const { wrapper } = await mountCard()
    const legs = wrapper.findAll('.itinerary__leg')
    expect(legs).toHaveLength(3)
    expect(legs[0]!.text()).toContain('Northgate')
    expect(legs[0]!.text()).toContain('300 m')
    expect(legs[1]!.text()).toContain(pl.journey.leg.modes.tram)
    expect(legs[1]!.text()).toContain('Southfield')
    expect(legs[1]!.find('summary').text()).toBe(pl.journey.leg.stops.replace('{count}', '1'))
    expect(legs[1]!.text()).toContain('Midtown')
    expect(legs[2]!.text()).toContain('08:20')
  })

  it('does not render legs when collapsed and reports aria-expanded', async () => {
    const { wrapper } = await mountCard({ expanded: false })
    expect(wrapper.find('.itinerary__legs').exists()).toBe(false)
    expect(wrapper.find('.itinerary__summary').attributes('aria-expanded')).toBe('false')
  })

  it('uses a placeholder for a leg place without a name', async () => {
    const itinerary = journeyItinerary()
    itinerary.legs[0]!.from.name = null
    const { wrapper } = await mountCard({ itinerary })
    expect(wrapper.findAll('.itinerary__leg')[0]!.text()).toContain(pl.journey.leg.unnamed)
  })

  it('renders a transit leg without a line (no link, no crash)', async () => {
    const itinerary = journeyItinerary()
    itinerary.legs[1]!.line = null
    const { wrapper } = await mountCard({ itinerary })
    expect(wrapper.find('a.itinerary__line-link').exists()).toBe(false)
    expect(wrapper.findAll('.itinerary__leg')[1]!.text()).toContain(pl.journey.leg.modes.tram)
  })

  it('emits toggle when the summary is clicked', async () => {
    const { wrapper } = await mountCard()
    await wrapper.find('.itinerary__summary').trigger('click')
    expect(wrapper.emitted('toggle')).toHaveLength(1)
  })

  it('formats times in the English locale too', async () => {
    applyLocale('en')
    const { wrapper } = await mountCard({ expanded: false })
    expect(wrapper.find('.itinerary__summary').text()).toContain('08:03 – 08:20')
    expect(wrapper.find('article').attributes('aria-label')).toBe(
      'Connection 1: 08:03 to 08:20, 17 min',
    )
  })
})

describe('BottomTabBar', () => {
  it('shows the four sections with translated labels', async () => {
    const { wrapper } = await mountApp(BottomTabBar)
    const labels = wrapper.findAll('.tab-bar__link').map((l) => l.text())
    expect(labels).toEqual([pl.nav.journey, pl.nav.timetable, pl.nav.tickets, pl.nav.assistant])
    expect(wrapper.find('nav').attributes('aria-label')).toBe(pl.nav.tabsLabel)
  })

  it('links to the section routes', async () => {
    const { wrapper } = await mountApp(BottomTabBar)
    const hrefs = wrapper.findAll('.tab-bar__link').map((l) => l.attributes('href'))
    expect(hrefs).toEqual(['/', '/timetable', '/tickets', '/assistant'])
  })

  it('marks the journey tab current on home only', async () => {
    const { wrapper, router } = await mountApp(BottomTabBar)
    await router.push('/')
    await nextTick()
    let current = wrapper.findAll('[aria-current="page"]')
    expect(current).toHaveLength(1)
    expect(current[0]!.text()).toBe(pl.nav.journey)
    await router.push('/timetable/lines/feed_a:7')
    await nextTick()
    current = wrapper.findAll('[aria-current="page"]')
    expect(current).toHaveLength(1)
    expect(current[0]!.text()).toBe(pl.nav.timetable)
  })

  it('switches labels to English', async () => {
    const { wrapper } = await mountApp(BottomTabBar)
    applyLocale('en')
    await nextTick()
    expect(wrapper.findAll('.tab-bar__link').map((l) => l.text())).toEqual([
      en.nav.journey,
      en.nav.timetable,
      en.nav.tickets,
      en.nav.assistant,
    ])
  })
})

describe('router', () => {
  it('redirects /journey to the home route', async () => {
    const { router } = await mountApp(BottomTabBar)
    await router.push('/journey')
    expect(router.currentRoute.value.name).toBe('home')
    expect(router.currentRoute.value.path).toBe('/')
    expect(router.currentRoute.value.meta.fullscreen).toBe(true)
  })
})

describe('HomeView', () => {
  it('shows the planner form and the empty "Your journeys" panel initially', async () => {
    const { wrapper } = await mountApp(HomeView)
    expect(wrapper.find('form.journey-form').exists()).toBe(true)
    expect(wrapper.text()).toContain(pl.journey.yourJourneys.title)
    expect(wrapper.find('.journey-results').exists()).toBe(false)
  })

  it('shows the picking banner for the field being picked and hides the form', async () => {
    const { wrapper } = await mountApp(HomeView)
    const journey = useJourneyStore()
    journey.startPicking('from')
    await nextTick()
    const banner = wrapper.find('.home__picking')
    expect(banner.text()).toContain(pl.journey.pickingFrom)
    expect(wrapper.find('.home__panel-body').attributes('style')).toContain('display: none')
    journey.cancelPicking()
    journey.startPicking('to')
    await nextTick()
    expect(wrapper.find('.home__picking').text()).toContain(pl.journey.pickingTo)
  })

  it('cancels picking with the button and with Escape', async () => {
    const { wrapper } = await mountApp(HomeView, { attachTo: document.body })
    const journey = useJourneyStore()
    journey.startPicking('to')
    await nextTick()
    await wrapper.find('.home__picking button').trigger('click')
    expect(journey.picking).toBeNull()
    expect(wrapper.find('.home__picking').exists()).toBe(false)
    journey.startPicking('from')
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await nextTick()
    expect(journey.picking).toBeNull()
    wrapper.unmount()
  })

  it('translates the picking banner to English', async () => {
    const { wrapper } = await mountApp(HomeView)
    const journey = useJourneyStore()
    journey.startPicking('from')
    applyLocale('en')
    await nextTick()
    expect(wrapper.find('.home__picking').text()).toContain(en.journey.pickingFrom)
  })

  it('shows results instead of the "Your journeys" panel after a search', async () => {
    fetchMock.mockImplementation(async () => jsonResponse(journeyResponse()))
    const { wrapper } = await mountApp(HomeView)
    useCityStore().cityId = 'alpha'
    const journey = useJourneyStore()
    journey.setPlace('from', fromPlace)
    journey.setPlace('to', toPlace)
    await journey.search()
    await flushPromises()
    expect(wrapper.find('.journey-results').exists()).toBe(true)
    expect(wrapper.find('.home__yours').exists()).toBe(false)
  })

  it('resets the journey form when the city changes', async () => {
    await mountApp(HomeView)
    const city = useCityStore()
    city.cityId = 'alpha'
    await nextTick()
    const journey = useJourneyStore()
    journey.setPlace('from', fromPlace)
    city.cityId = 'beta'
    await nextTick()
    expect(journey.from).toBeNull()
  })
})
