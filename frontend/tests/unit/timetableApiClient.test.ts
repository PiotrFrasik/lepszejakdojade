import { getLineRoute, getLines, getStopTimetable, getTrip } from '@/api/client'

import { jsonResponse, resetEnvironment } from './helpers'

const fetchMock = vi.fn()

beforeEach(() => {
  resetEnvironment()
  fetchMock.mockReset()
  fetchMock.mockImplementation(async () => jsonResponse([]))
  vi.stubGlobal('fetch', fetchMock)
})
afterEach(() => vi.unstubAllGlobals())

const last = <T>(items: T[]): T | undefined => items[items.length - 1]
const lastUrl = (): string => last(fetchMock.mock.calls)![0] as string

describe('timetable API client', () => {
  it('builds the lines URL, with and without a vehicle type filter', async () => {
    await getLines('alpha')
    expect(lastUrl()).toBe('/api/v1/cities/alpha/lines/')
    await getLines('alpha', null)
    expect(lastUrl()).toBe('/api/v1/cities/alpha/lines/')
    await getLines('alpha', 'tram')
    expect(lastUrl()).toBe('/api/v1/cities/alpha/lines/?vehicle_type=tram')
  })

  it('URL-encodes ids containing a colon in the route path', async () => {
    await getLineRoute('alpha', 'feed_a:52', { direction: 1, date: '2026-11-16' })
    expect(lastUrl()).toBe(
      '/api/v1/cities/alpha/lines/feed_a%3A52/route/?direction=1&date=2026-11-16',
    )
  })

  it('omits direction and date when not given (API defaults)', async () => {
    await getLineRoute('alpha', 'feed_a:52')
    expect(lastUrl()).toBe('/api/v1/cities/alpha/lines/feed_a%3A52/route/')
    await getLineRoute('alpha', 'feed_a:52', { date: null })
    expect(lastUrl()).toBe('/api/v1/cities/alpha/lines/feed_a%3A52/route/')
  })

  it('keeps direction 0 in the query (0 is not "missing")', async () => {
    await getLineRoute('alpha', 'feed_a:52', { direction: 0 })
    expect(lastUrl()).toContain('direction=0')
  })

  it('builds the stop timetable URL with both ids encoded', async () => {
    await getStopTimetable('alpha', 'feed_a:52', 'feed_a:stop/1 x', { direction: 1 })
    expect(lastUrl()).toBe(
      '/api/v1/cities/alpha/lines/feed_a%3A52/stops/feed_a%3Astop%2F1%20x/timetable/?direction=1',
    )
  })

  it('builds the trip URL with the date', async () => {
    await getTrip('alpha', 'feed_a:trip_3', '2026-11-16')
    expect(lastUrl()).toBe('/api/v1/cities/alpha/trips/feed_a%3Atrip_3/?date=2026-11-16')
  })

  it('passes the abort signal through', async () => {
    const controller = new AbortController()
    await getLines('alpha', 'bus', controller.signal)
    expect((last(fetchMock.mock.calls)![1] as RequestInit).signal).toBe(controller.signal)
  })
})
