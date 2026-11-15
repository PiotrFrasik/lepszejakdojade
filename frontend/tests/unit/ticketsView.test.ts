import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'

import JourneyResults from '@/components/journey/JourneyResults.vue'
import { applyLocale, i18n } from '@/i18n'
import en from '@/locales/en.json'
import pl from '@/locales/pl.json'
import { routes } from '@/router'
import { useCityStore } from '@/stores/city'
import { useJourneyStore } from '@/stores/journey'
import { useTicketsStore } from '@/stores/tickets'
import type { CityDetail } from '@/types/api'
import TicketsView from '@/views/TicketsView.vue'

import { cityDetail, cityList } from './citiesFixtures'
import { jsonResponse, resetEnvironment } from './helpers'
import { journeyItinerary, journeyResponse } from './journeyFixtures'
import { catalogue, suggestion, ticket } from './ticketsFixtures'

const norm = (s: string) => s.replace(/[  ]/g, ' ')
const never = () => new Promise<Response>(() => {})

interface Call {
  method: string
  path: string
  search: string
  body: unknown
  lang: string | null
  signal: AbortSignal | null | undefined
}

type Handler = (call: Call) => Response | Promise<Response> | undefined

const mounted: { unmount: () => void }[] = []
let calls: Call[]
let handler: Handler
let journeyItineraries = journeyResponse().itineraries

beforeEach(() => {
  resetEnvironment()
  calls = []
  handler = () => undefined
  journeyItineraries = journeyResponse().itineraries
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), 'http://localhost')
      const call: Call = {
        method: init?.method ?? 'GET',
        path: url.pathname,
        search: url.search,
        body: init?.body ? JSON.parse(String(init.body)) : undefined,
        lang: new Headers(init?.headers).get('Accept-Language'),
        signal: init?.signal,
      }
      calls.push(call)
      const custom = handler(call)
      if (custom) return custom
      if (call.path.endsWith('/tickets/suggest/')) return jsonResponse(suggestion())
      if (call.path.endsWith('/tickets/')) return jsonResponse(catalogue())
      if (call.method === 'POST') {
        return jsonResponse(journeyResponse({ itineraries: journeyItineraries }))
      }
      return jsonResponse([])
    }),
  )
})
afterEach(() => {
  // Wrappers stay attached to the shared i18n instance, so unmount them to stop stale refetches.
  for (const wrapper of mounted.splice(0)) wrapper.unmount()
  vi.unstubAllGlobals()
})

async function setup(component: object, cityId = 'alpha') {
  const pinia = createPinia()
  setActivePinia(pinia)
  const city = useCityStore()
  city.cityId = cityId
  city.cities = cityList('pl')
  city.details = cityDetail(cityId, 'pl') as CityDetail
  const router = createRouter({ history: createMemoryHistory(), routes })
  await router.push('/tickets')
  await router.isReady()
  const wrapper = mount(component, {
    global: { plugins: [pinia, i18n, router], stubs: { CityMap: true, JourneyMap: true } },
    attachTo: document.body,
  })
  mounted.push(wrapper)
  await flushPromises()
  return { wrapper, city, router }
}

const ticketCalls = () => calls.filter((c) => c.path.endsWith('/tickets/') && c.method === 'GET')
const suggestCalls = () => calls.filter((c) => c.path.endsWith('/tickets/suggest/'))
const isCatalogue = (c: Call) => c.path.endsWith('/tickets/') && c.method === 'GET'
const isSuggest = (c: Call) => c.path.endsWith('/tickets/suggest/')

describe('TicketsView', () => {
  it('requests the catalogue of the selected city', async () => {
    await setup(TicketsView)
    expect(ticketCalls()).toHaveLength(1)
    expect(ticketCalls()[0]!.path).toBe('/api/v1/cities/alpha/tickets/')
  })

  it('shows the loading state first', async () => {
    let release!: (r: Response) => void
    handler = (c) =>
      isCatalogue(c) ? new Promise<Response>((resolve) => (release = resolve)) : undefined
    const { wrapper } = await setup(TicketsView)
    expect(wrapper.find('[role="status"]').text()).toContain(pl.tickets.loading)
    release(jsonResponse(catalogue()))
    await flushPromises()
    expect(wrapper.find('[role="status"]').exists()).toBe(false)
  })

  it('groups standard tickets by kind in order, with headings', async () => {
    const { wrapper } = await setup(TicketsView)
    const headings = wrapper.findAll('.tickets__group h2').map((h) => h.text())
    expect(headings).toEqual([
      pl.tickets.kinds.single,
      pl.tickets.kinds.time,
      pl.tickets.kinds.daily,
      pl.tickets.kinds.period,
    ])
    const names = wrapper.findAll('.ticket-card__name').map((n) => n.text())
    expect(names).toEqual([
      'Single ride',
      'Short ticket',
      'Hourly ticket',
      'Day ticket',
      'Week pass',
    ])
  })

  it('formats prices for Polish from the decimal string', async () => {
    const { wrapper } = await setup(TicketsView)
    const prices = wrapper.findAll('.ticket-card__price').map((p) => norm(p.text()))
    expect(prices).toEqual(['4,20 zł', '3,10 zł', '6,00 zł', '17,50 zł', '48,00 zł'])
  })

  it('switches to reduced tickets with the toggle and back, without a new request', async () => {
    const { wrapper } = await setup(TicketsView)
    const [standard, reduced] = wrapper.findAll('.fare-toggle__option')
    expect(standard!.attributes('aria-pressed')).toBe('true')
    await reduced!.trigger('click')
    expect(reduced!.attributes('aria-pressed')).toBe('true')
    expect(wrapper.findAll('.ticket-card__name').map((n) => n.text())).toEqual([
      'Single ride reduced',
      'Hourly reduced',
    ])
    expect(useTicketsStore().reduced).toBe(true)
    await standard!.trigger('click')
    expect(wrapper.findAll('.ticket-card')).toHaveLength(5)
    expect(ticketCalls()).toHaveLength(1)
  })

  it('remembers the reduced fare in the browser', async () => {
    const { wrapper } = await setup(TicketsView)
    await wrapper.findAll('.fare-toggle__option')[1]!.trigger('click')
    expect(window.localStorage.getItem('ljd.tickets.reduced')).toBe('true')
  })

  it('shows a message when the chosen fare has no tickets', async () => {
    handler = (c) =>
      isCatalogue(c) ? jsonResponse(catalogue({ tickets: [ticket({ reduced: false })] })) : undefined
    const { wrapper } = await setup(TicketsView)
    await wrapper.findAll('.fare-toggle__option')[1]!.trigger('click')
    expect(wrapper.text()).toContain(pl.tickets.emptyReduced)
    expect(wrapper.findAll('.ticket-card')).toHaveLength(0)
  })

  it('shows the empty state for a catalogue without tickets but keeps the zones', async () => {
    handler = (c) => (isCatalogue(c) ? jsonResponse(catalogue({ tickets: [] })) : undefined)
    const { wrapper } = await setup(TicketsView)
    expect(wrapper.text()).toContain(pl.tickets.empty)
    expect(wrapper.find('.tickets__zones').exists()).toBe(true)
    expect(wrapper.find('.tickets__meta').exists()).toBe(false)
  })

  it('renders the zone legend and the zone names on tickets', async () => {
    const { wrapper } = await setup(TicketsView)
    const zones = wrapper.findAll('.tickets__zone').map((z) => z.text())
    expect(zones).toEqual(['1Zone A', '2Zone B'])
    expect(wrapper.text()).toContain('Strefy: Zone A, Zone B')
  })

  it('omits the zone legend when there are no zones', async () => {
    handler = (c) => (isCatalogue(c) ? jsonResponse(catalogue({ zones: [] })) : undefined)
    const { wrapper } = await setup(TicketsView)
    expect(wrapper.find('.tickets__zones').exists()).toBe(false)
  })

  it('falls back to the zone id for an unknown zone', async () => {
    handler = (c) =>
      isCatalogue(c) ? jsonResponse(catalogue({ tickets: [ticket({ zones: ['9'] })] })) : undefined
    const { wrapper } = await setup(TicketsView)
    expect(wrapper.text()).toContain('Strefy: 9')
  })

  it('shows the latest prices-as-of date and a safe source link', async () => {
    const { wrapper } = await setup(TicketsView)
    const meta = wrapper.find('.tickets__meta')
    expect(norm(meta.text())).toContain('Ceny z dnia 5 lis 2026')
    const links = wrapper.findAll('a.tickets__source')
    expect(links.map((l) => l.attributes('href'))).toEqual([
      'https://tickets.example.org/prices',
      'https://www.pass.example.net/list',
    ])
    expect(links[0]!.attributes('target')).toBe('_blank')
    expect(links[0]!.attributes('rel')).toContain('noopener')
    expect(links[1]!.text()).toContain('pass.example.net')
  })

  it('does not render a link for an unsafe source URL', async () => {
    handler = (c) =>
      isCatalogue(c)
        ? jsonResponse(catalogue({ tickets: [ticket({ source_url: 'javascript:alert(1)' })] }))
        : undefined
    const { wrapper } = await setup(TicketsView)
    expect(wrapper.find('a.tickets__source').exists()).toBe(false)
  })

  it('describes validity: single ride, minutes, hours, days', async () => {
    const { wrapper } = await setup(TicketsView)
    const text = norm(wrapper.text())
    expect(text).toContain(pl.tickets.validity.single)
    expect(text).toContain('Ważny 20 min')
    expect(text).toContain('Ważny 1 h')
    expect(text).toContain('Ważny 24 h')
    expect(text).toContain('Ważny 7 dni')
  })

  it('shows an error with retry that reloads the catalogue', async () => {
    let fail = true
    handler = (c) =>
      isCatalogue(c) && fail
        ? jsonResponse({ error: { code: 'server_error', message: 'x' } }, 500)
        : undefined
    const { wrapper } = await setup(TicketsView)
    const alert = wrapper.find('[role="alert"]')
    expect(alert.text()).toContain(pl.errors.generic)
    expect(wrapper.findAll('.ticket-card')).toHaveLength(0)
    fail = false
    await alert.find('button').trigger('click')
    await flushPromises()
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.findAll('.ticket-card')).toHaveLength(5)
  })

  it('shows the city-specific message on 404', async () => {
    handler = (c) =>
      isCatalogue(c) ? jsonResponse({ error: { code: 'not_found', message: 'x' } }, 404) : undefined
    const { wrapper } = await setup(TicketsView)
    expect(wrapper.find('[role="alert"]').text()).toContain(pl.tickets.cityNotFound)
  })

  it('shows the network message when the server cannot be reached', async () => {
    handler = (c) => {
      if (isCatalogue(c)) throw new TypeError('offline')
      return undefined
    }
    const { wrapper } = await setup(TicketsView)
    expect(wrapper.find('[role="alert"]').text()).toContain(pl.errors.network)
  })

  it('refetches when the city changes and shows the new city list', async () => {
    const { wrapper, city } = await setup(TicketsView)
    handler = (c) =>
      c.path.includes('/beta/tickets/')
        ? jsonResponse(catalogue({ tickets: [ticket({ id: 'beta-1', name: 'Beta ticket' })] }))
        : undefined
    city.cityId = 'beta'
    await flushPromises()
    expect(ticketCalls().map((c) => c.path)).toEqual([
      '/api/v1/cities/alpha/tickets/',
      '/api/v1/cities/beta/tickets/',
    ])
    expect(wrapper.findAll('.ticket-card__name').map((n) => n.text())).toEqual(['Beta ticket'])
  })

  it('does not show the previous city list while the new city loads', async () => {
    const { wrapper, city } = await setup(TicketsView)
    handler = (c) => (c.path.includes('/beta/tickets/') ? never() : undefined)
    city.cityId = 'beta'
    await nextTick()
    await flushPromises()
    expect(wrapper.findAll('.ticket-card')).toHaveLength(0)
  })

  it('refetches with the new Accept-Language on language change and shows English text', async () => {
    const { wrapper } = await setup(TicketsView)
    expect(ticketCalls()[0]!.lang).toBe('pl')
    handler = (c) =>
      isCatalogue(c)
        ? jsonResponse(
            catalogue({
              zones: [{ id: '1', name: 'Zone A' }],
              tickets: [ticket({ name: 'Hourly ticket (en)' })],
            }),
          )
        : undefined
    applyLocale('en')
    await flushPromises()
    expect(ticketCalls()).toHaveLength(2)
    expect(ticketCalls()[1]!.lang).toBe('en')
    expect(wrapper.find('h1').text()).toBe(en.tickets.title)
    expect(wrapper.text()).toContain(en.tickets.kinds.time)
    expect(wrapper.text()).toContain('Hourly ticket (en)')
    expect(norm(wrapper.text())).toContain('PLN 6.00')
    expect(norm(wrapper.text())).toContain('Prices as of Nov 1, 2026')
    expect(wrapper.text()).not.toContain(pl.tickets.title)
  })

  it('keeps the old list on screen while the language refetch is pending', async () => {
    const { wrapper } = await setup(TicketsView)
    handler = (c) => (isCatalogue(c) ? never() : undefined)
    applyLocale('en')
    await flushPromises()
    expect(wrapper.findAll('.ticket-card')).toHaveLength(5)
    expect(wrapper.find('.tickets__content').attributes('aria-busy')).toBe('true')
  })

  it('translates the intro with the city name, the notice and the fare toggle', async () => {
    const { wrapper } = await setup(TicketsView)
    expect(wrapper.text()).toContain('Cennik biletów komunikacji miejskiej w mieście Alfa.')
    expect(wrapper.text()).toContain(pl.tickets.notice)
    expect(wrapper.findAll('.fare-toggle__option').map((b) => b.text())).toEqual([
      pl.tickets.fare.standard,
      pl.tickets.fare.reduced,
    ])
  })

  it('treats an unknown ticket kind as "other tickets"', async () => {
    handler = (c) =>
      isCatalogue(c)
        ? jsonResponse(catalogue({ tickets: [ticket({ kind: 'mystery' as never })] }))
        : undefined
    const { wrapper } = await setup(TicketsView)
    expect(wrapper.find('.tickets__group h2').text()).toBe(pl.tickets.kinds.other)
  })
})

describe('TicketHint in JourneyResults', () => {
  const fromPlace = { source: 'map', name: null, lat: 50.06, lon: 19.93 } as const
  const toPlace = { source: 'map', name: null, lat: 50.02, lon: 19.89 } as const

  async function mountResults() {
    const mounted = await setup(JourneyResults)
    const journey = useJourneyStore()
    journey.setPlace('from', fromPlace)
    journey.setPlace('to', toPlace)
    await journey.search()
    await flushPromises()
    return { ...mounted, journey }
  }

  it('posts duration, transfers and reduced for the selected connection', async () => {
    const { wrapper } = await mountResults()
    expect(suggestCalls()).toHaveLength(1)
    expect(suggestCalls()[0]!.method).toBe('POST')
    expect(suggestCalls()[0]!.path).toBe('/api/v1/cities/alpha/tickets/suggest/')
    expect(suggestCalls()[0]!.body).toEqual({
      duration_seconds: 1020,
      transfers: 0,
      reduced: false,
    })
    const hint = wrapper.find('.ticket-hint')
    expect(hint.text()).toContain(pl.journey.ticket.title.replace('{index}', '1'))
    expect(hint.text()).toContain('Hourly ticket')
    expect(norm(hint.text())).toContain('6,00 zł')
    expect(hint.text()).toContain('A 60-minute ticket covers this 17-minute journey in Zone A.')
    expect(hint.find('a').attributes('href')).toBe('/tickets')
  })

  it('asks again for another selected connection and aborts the superseded request', async () => {
    const { wrapper } = await mountResults()
    handler = (c) => (isSuggest(c) ? never() : undefined)
    await wrapper.findAll('.itinerary__summary')[1]!.trigger('click')
    await flushPromises()
    expect(suggestCalls()).toHaveLength(2)
    expect(suggestCalls()[1]!.body).toEqual({
      duration_seconds: 1020,
      transfers: 2,
      reduced: false,
    })
    await wrapper.findAll('.itinerary__summary')[0]!.trigger('click')
    await flushPromises()
    expect(suggestCalls()).toHaveLength(3)
    expect(suggestCalls()[1]!.signal!.aborted).toBe(true)
  })

  it('does not show a stale hint from the previous selection while the next loads', async () => {
    const { wrapper } = await mountResults()
    handler = (c) => (isSuggest(c) ? never() : undefined)
    await wrapper.findAll('.itinerary__summary')[1]!.trigger('click')
    await flushPromises()
    expect(wrapper.find('.ticket-hint').exists()).toBe(false)
  })

  it('sends reduced=true when the reduced fare is chosen', async () => {
    const { wrapper } = await mountResults()
    useTicketsStore().setReduced(true)
    await flushPromises()
    expect(suggestCalls()).toHaveLength(2)
    expect(suggestCalls()[1]!.body).toMatchObject({ reduced: true })
    expect(wrapper.find('.ticket-hint').exists()).toBe(true)
  })

  it('aborts and re-requests on language change, with the new Accept-Language', async () => {
    await mountResults()
    handler = (c) =>
      isSuggest(c) ? jsonResponse(suggestion({ reason: 'English reason.' })) : undefined
    applyLocale('en')
    await flushPromises()
    expect(suggestCalls()).toHaveLength(2)
    expect(suggestCalls()[0]!.lang).toBe('pl')
    expect(suggestCalls()[1]!.lang).toBe('en')
  })

  it('aborts the in-flight request on language change', async () => {
    await mountResults()
    handler = (c) => (isSuggest(c) ? never() : undefined)
    useTicketsStore().setReduced(true)
    await flushPromises()
    const pending = suggestCalls()[suggestCalls().length - 1]!
    applyLocale('en')
    await flushPromises()
    expect(pending.signal!.aborted).toBe(true)
  })

  it('shows the hint in English with an English price', async () => {
    const { wrapper } = await mountResults()
    handler = (c) =>
      isSuggest(c) ? jsonResponse(suggestion({ reason: 'English reason.' })) : undefined
    applyLocale('en')
    await flushPromises()
    const text = norm(wrapper.find('.ticket-hint').text())
    expect(text).toContain(en.journey.ticket.title.replace('{index}', '1'))
    expect(text).toContain('PLN 6.00')
    expect(text).toContain('English reason.')
    expect(text).toContain(en.journey.ticket.allTickets)
  })

  it('aborts the in-flight request when the city changes', async () => {
    const { city } = await mountResults()
    handler = (c) => (isSuggest(c) ? never() : undefined)
    useTicketsStore().setReduced(true)
    await flushPromises()
    const pending = suggestCalls()[suggestCalls().length - 1]!
    city.cityId = 'beta'
    await flushPromises()
    expect(pending.signal!.aborted).toBe(true)
  })

  it('shows a reduced-fare note for a reduced ticket', async () => {
    const { wrapper } = await mountResults()
    handler = (c) =>
      isSuggest(c)
        ? jsonResponse(suggestion({ ticket: ticket({ reduced: true, price: '3.00' }) }))
        : undefined
    useTicketsStore().setReduced(true)
    await flushPromises()
    expect(wrapper.find('.ticket-hint__fare').text()).toBe(pl.journey.ticket.reducedFare)
  })

  it('is hidden when the API answers ticket: null', async () => {
    handler = (c) =>
      isSuggest(c) ? jsonResponse({ ticket: null, reason: 'No match.' }) : undefined
    const { wrapper } = await mountResults()
    expect(suggestCalls()).toHaveLength(1)
    expect(wrapper.find('.ticket-hint').exists()).toBe(false)
  })

  it('is hidden when the request fails, without an error message', async () => {
    handler = (c) =>
      isSuggest(c) ? jsonResponse({ error: { code: 'server_error', message: 'x' } }, 500) : undefined
    const { wrapper } = await mountResults()
    expect(wrapper.find('.ticket-hint').exists()).toBe(false)
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  })

  it('is hidden when the network fails', async () => {
    handler = (c) => {
      if (isSuggest(c)) throw new TypeError('offline')
      return undefined
    }
    const { wrapper } = await mountResults()
    expect(wrapper.find('.ticket-hint').exists()).toBe(false)
  })

  it('is hidden for malformed responses', async () => {
    const bodies: unknown[] = [
      {},
      { reason: 'x' },
      { ticket: { id: 'a' }, reason: 'x' },
      { ticket: 'oops', reason: 'x' },
      { ticket: { ...ticket(), price: 6 }, reason: 'x' },
      { ticket: ticket() },
      [],
    ]
    for (const body of bodies) {
      handler = (c) => (isSuggest(c) ? jsonResponse(body) : undefined)
      const { wrapper } = await mountResults()
      expect(wrapper.find('.ticket-hint').exists(), JSON.stringify(body)).toBe(false)
    }
  })

  it('is not requested for a journey longer than 86400 seconds', async () => {
    journeyItineraries = [journeyItinerary({ id: 'long', duration: 86401 })]
    const { wrapper } = await mountResults()
    expect(suggestCalls()).toHaveLength(0)
    expect(wrapper.find('.ticket-hint').exists()).toBe(false)
  })

  it('is requested for exactly 86400 seconds', async () => {
    journeyItineraries = [journeyItinerary({ id: 'edge', duration: 86400 })]
    await mountResults()
    expect(suggestCalls()[0]!.body).toMatchObject({ duration_seconds: 86400 })
  })

  it('sends at least 1 second for a zero-length journey', async () => {
    journeyItineraries = [journeyItinerary({ id: 'zero', duration: 0 })]
    await mountResults()
    expect(suggestCalls()[0]!.body).toMatchObject({ duration_seconds: 1 })
  })
})
