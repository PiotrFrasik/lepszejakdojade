import { getStopOverview } from '@/api/client'
import { applyLocale } from '@/i18n'

import { jsonResponse, resetEnvironment } from './helpers'
import { stopOverview } from './stopOverviewFixtures'

const fetchMock = vi.fn()

beforeEach(() => {
  resetEnvironment()
  fetchMock.mockReset()
  fetchMock.mockImplementation(async () => jsonResponse(stopOverview()))
  vi.stubGlobal('fetch', fetchMock)
})
afterEach(() => vi.unstubAllGlobals())

const lastUrl = () => String(fetchMock.mock.calls[fetchMock.mock.calls.length - 1]![0])
const lastInit = () => fetchMock.mock.calls[fetchMock.mock.calls.length - 1]![1] as RequestInit

describe('getStopOverview', () => {
  it('requests the stop endpoint and returns the parsed body', async () => {
    const result = await getStopOverview('alpha', 'feed_a:stop_1')
    expect(lastUrl()).toBe('/api/v1/cities/alpha/stops/feed_a%3Astop_1/')
    expect(result.stop.name).toBe('Northgate')
    expect(result.lines).toHaveLength(1)
  })

  it('URL-encodes ids with spaces and slashes', async () => {
    await getStopOverview('alpha', 'feed b:stop/1')
    expect(lastUrl()).toBe('/api/v1/cities/alpha/stops/feed%20b%3Astop%2F1/')
  })

  it('sends Accept-Language matching the current locale', async () => {
    applyLocale('en')
    await getStopOverview('alpha', 'x')
    expect(new Headers(lastInit().headers).get('Accept-Language')).toBe('en')
    applyLocale('pl')
    await getStopOverview('alpha', 'x')
    expect(new Headers(lastInit().headers).get('Accept-Language')).toBe('pl')
  })

  it('passes the abort signal through', async () => {
    const controller = new AbortController()
    await getStopOverview('alpha', 'x', controller.signal)
    expect(lastInit().signal).toBe(controller.signal)
  })

  it('rejects with a 404 ApiError for an unknown stop', async () => {
    fetchMock.mockImplementation(async () =>
      jsonResponse({ error: { code: 'not_found', message: 'nope' } }, 404),
    )
    await expect(getStopOverview('alpha', 'nope')).rejects.toMatchObject({
      status: 404,
      code: 'not_found',
    })
  })
})
