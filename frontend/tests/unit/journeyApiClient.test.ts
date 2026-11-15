import { ApiError, searchJourneys, searchStops } from '@/api/client'
import { applyLocale } from '@/i18n'
import type { JourneySearchRequest } from '@/types/api'

import { journeyResponse, stopResult } from './journeyFixtures'
import { jsonResponse, resetEnvironment } from './helpers'

const fetchMock = vi.fn()

beforeEach(() => {
  resetEnvironment()
  fetchMock.mockReset()
  fetchMock.mockImplementation(async () => jsonResponse([]))
  vi.stubGlobal('fetch', fetchMock)
})
afterEach(() => vi.unstubAllGlobals())

const lastCall = () =>
  fetchMock.mock.calls[fetchMock.mock.calls.length - 1]! as [string, RequestInit]

const REQUEST: JourneySearchRequest = {
  from: { stop_id: 'feed_a:stop_1', name: 'Northgate' },
  to: { lat: 50.02, lon: 19.89 },
  time: '2026-11-16T08:00:00+01:00',
  time_mode: 'depart',
  preferences: { fewer_transfers: false, less_walking: true, wheelchair: false },
}

describe('searchStops', () => {
  it('calls the stop search endpoint with the trimmed query', async () => {
    await searchStops('alpha', '  plac  ')
    const [url, init] = lastCall()
    expect(url).toBe('/api/v1/cities/alpha/stops/?q=plac')
    expect(init.method).toBe('GET')
  })

  it('encodes special characters in the query and the city', async () => {
    await searchStops('a b', 'żab & co')
    expect(lastCall()[0]).toBe('/api/v1/cities/a%20b/stops/?q=%C5%BCab+%26+co')
  })

  it('returns the parsed list', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse([stopResult()]))
    expect(await searchStops('alpha', 'north')).toEqual([stopResult()])
  })

  it('sends Accept-Language of the current UI language', async () => {
    await searchStops('alpha', 'north')
    expect((lastCall()[1].headers as Record<string, string>)['Accept-Language']).toBe('pl')
    applyLocale('en')
    await searchStops('alpha', 'north')
    expect((lastCall()[1].headers as Record<string, string>)['Accept-Language']).toBe('en')
  })

  it('throws ApiError with the API code on 400', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ error: { code: 'validation_error', message: 'Too short.' } }, 400),
    )
    const err = await searchStops('alpha', 'a').catch((e: unknown) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err).toMatchObject({ status: 400, code: 'validation_error' })
  })
})

describe('searchJourneys', () => {
  it('POSTs the request as JSON to the journeys endpoint', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(journeyResponse()))
    const result = await searchJourneys('alpha', REQUEST)
    const [url, init] = lastCall()
    expect(url).toBe('/api/v1/cities/alpha/journeys/search/')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body as string)).toEqual(REQUEST)
    const headers = init.headers as Record<string, string>
    expect(headers['Content-Type']).toBe('application/json')
    expect(result.itineraries).toHaveLength(2)
  })

  it('sends Accept-Language of the current UI language', async () => {
    applyLocale('en')
    fetchMock.mockResolvedValueOnce(jsonResponse(journeyResponse()))
    await searchJourneys('alpha', REQUEST)
    expect((lastCall()[1].headers as Record<string, string>)['Accept-Language']).toBe('en')
  })

  it('maps 503 journey_planner_unavailable to an ApiError', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        { error: { code: 'journey_planner_unavailable', message: 'Planner is down.' } },
        503,
      ),
    )
    const err = await searchJourneys('alpha', REQUEST).catch((e: unknown) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err).toMatchObject({
      status: 503,
      code: 'journey_planner_unavailable',
      message: 'Planner is down.',
    })
  })

  it('maps a network failure to ApiError with status 0', async () => {
    fetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch'))
    const err = await searchJourneys('alpha', REQUEST).catch((e: unknown) => e)
    expect(err).toMatchObject({ status: 0, code: 'network_error' })
  })

  it('passes the abort signal through', async () => {
    const controller = new AbortController()
    fetchMock.mockResolvedValueOnce(jsonResponse(journeyResponse()))
    await searchJourneys('alpha', REQUEST, controller.signal)
    expect(lastCall()[1].signal).toBe(controller.signal)
  })
})
