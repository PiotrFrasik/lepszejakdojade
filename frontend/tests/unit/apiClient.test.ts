import { ApiError, apiGet, apiRequest, buildUrl, getHealth } from '@/api/client'
import { applyLocale } from '@/i18n'

import { jsonResponse, resetEnvironment } from './helpers'

const fetchMock = vi.fn()

beforeEach(() => {
  resetEnvironment()
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
})
afterEach(() => vi.unstubAllGlobals())

function lastCall(): { url: string; init: RequestInit & { headers: Record<string, string> } } {
  const [url, init] = fetchMock.mock.calls[fetchMock.mock.calls.length - 1]!
  return { url, init }
}

describe('api client', () => {
  it('uses relative /api/v1/ paths', async () => {
    fetchMock.mockImplementation(async () => jsonResponse({}))
    await apiGet('/cities/')
    expect(lastCall().url).toBe('/api/v1/cities/')
    await apiGet('cities/krakow/')
    expect(lastCall().url).toBe('/api/v1/cities/krakow/')
    expect(lastCall().url.startsWith('http')).toBe(false)
  })

  it('builds a query string and skips null and undefined values', () => {
    expect(buildUrl('/x/', { a: 1, b: null, c: undefined, d: 'q r' })).toBe('/api/v1/x/?a=1&d=q+r')
    expect(buildUrl('/x/', {})).toBe('/api/v1/x/')
  })

  it('sends Accept-Language matching the current locale', async () => {
    fetchMock.mockImplementation(async () => jsonResponse({}))
    await apiGet('/x/')
    expect(lastCall().init.headers['Accept-Language']).toBe('pl')
    applyLocale('en')
    await apiGet('/x/')
    expect(lastCall().init.headers['Accept-Language']).toBe('en')
  })

  it('sends a JSON body with a content type', async () => {
    fetchMock.mockImplementation(async () => jsonResponse({ ok: true }, 201))
    await apiRequest('/x/', { method: 'POST', body: { a: 1 } })
    const { init } = lastCall()
    expect(init.method).toBe('POST')
    expect(init.body).toBe('{"a":1}')
    expect(init.headers['Content-Type']).toBe('application/json')
  })

  it('parses {error:{code,message}} into ApiError', async () => {
    fetchMock.mockImplementation(async () =>
      jsonResponse({ error: { code: 'not_found', message: 'No such city' } }, 404),
    )
    const err = await apiGet<unknown>('/cities/x/').then(
      () => null,
      (e: unknown) => e as ApiError,
    )
    expect(err).toBeInstanceOf(ApiError)
    if (!err) return
    expect(err.status).toBe(404)
    expect(err.code).toBe('not_found')
    expect(err.message).toBe('No such city')
  })

  it('wraps a non-API error body as ApiError', async () => {
    fetchMock.mockImplementation(async () => new Response('<html>oops</html>', { status: 500 }))
    const err = await apiGet<unknown>('/x/').then(
      () => null,
      (e: unknown) => e as ApiError,
    )
    expect(err).toBeInstanceOf(ApiError)
    if (!err) return
    expect(err.status).toBe(500)
  })

  it('wraps network failures as ApiError with status 0', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'))
    const err = await apiGet<unknown>('/x/').then(
      () => null,
      (e: unknown) => e as ApiError,
    )
    expect(err).toBeInstanceOf(ApiError)
    if (!err) return
    expect(err.status).toBe(0)
    expect(err.code).toBe('network_error')
  })

  it('rethrows abort errors unchanged', async () => {
    const abort = new DOMException('aborted', 'AbortError')
    fetchMock.mockRejectedValue(abort)
    await expect(apiGet('/x/')).rejects.toBe(abort)
  })

  it('returns undefined for 204', async () => {
    fetchMock.mockImplementation(async () => new Response(null, { status: 204 }))
    await expect(apiRequest('/x/', { method: 'DELETE' })).resolves.toBeUndefined()
  })

  it('treats health 503 as a normal response', async () => {
    const body = { status: 'error', checks: { database: 'error' }, version: '0.1.0' }
    fetchMock.mockImplementation(async () => jsonResponse(body, 503))
    await expect(getHealth()).resolves.toEqual(body)
    expect(lastCall().url).toBe('/api/v1/health/')
  })

  it('still throws on other health failures', async () => {
    fetchMock.mockImplementation(async () =>
      jsonResponse({ error: { code: 'x', message: 'y' } }, 500),
    )
    await expect(getHealth()).rejects.toBeInstanceOf(ApiError)
  })
})
