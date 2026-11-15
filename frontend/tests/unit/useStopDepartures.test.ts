import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, ref } from 'vue'

import { getStopDepartures } from '@/api/client'
import { DEPARTURES_REFRESH_MS, useStopDepartures } from '@/composables/useStopDepartures'
import type { StopDepartures } from '@/types/api'

import { board, departure } from './departuresFixtures'
import { jsonResponse, resetEnvironment } from './helpers'

interface Pending {
  url: string
  signal: AbortSignal | null | undefined
  resolve: (r: Response) => void
}

let pending: Pending[] = []
let visibility: 'visible' | 'hidden' = 'visible'
const mounted: { unmount: () => void }[] = []

function stubFetch(auto?: () => Response) {
  pending = []
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      if (auto) return Promise.resolve(auto())
      return new Promise<Response>((resolve) =>
        pending.push({ url: String(input), signal: init?.signal, resolve }),
      )
    }),
  )
}

function setVisibility(value: 'visible' | 'hidden') {
  visibility = value
  document.dispatchEvent(new Event('visibilitychange'))
}

function mountBoard(initialStop: string | null = 'feed_a:stop_1') {
  const stop = ref<string | null>(initialStop)
  let api!: ReturnType<typeof useStopDepartures>
  const wrapper = mount(
    defineComponent({
      setup() {
        api = useStopDepartures(() => (stop.value ? { city: 'alpha', stop: stop.value } : null))
        return () => h('div')
      },
    }),
  )
  mounted.push(wrapper)
  return { wrapper, stop, api: () => api }
}

const named = (name: string): StopDepartures =>
  board({ stop: { id: 'x', name, stop_ids: ['x'] } })

beforeEach(() => {
  resetEnvironment()
  visibility = 'visible'
  Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => visibility })
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval', 'Date'] })
})
afterEach(() => {
  mounted.splice(0).forEach((w) => w.unmount())
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('getStopDepartures client', () => {
  it('URL-encodes the stop id and sends the limit only when given', async () => {
    stubFetch(() => jsonResponse(board()))
    await getStopDepartures('alpha', 'feed_a:stop/1 x')
    expect(vi.mocked(fetch).mock.calls[0]![0]).toBe(
      '/api/v1/cities/alpha/stops/feed_a%3Astop%2F1%20x/departures/',
    )
    await getStopDepartures('alpha', 'feed_a:stop_1', { limit: 5 })
    expect(vi.mocked(fetch).mock.calls[1]![0]).toBe(
      '/api/v1/cities/alpha/stops/feed_a%3Astop_1/departures/?limit=5',
    )
  })

  it('rejects with a 404 ApiError for an unknown stop', async () => {
    stubFetch(() => jsonResponse({ error: { code: 'not_found', message: 'nope' } }, 404))
    await expect(getStopDepartures('alpha', 'nope')).rejects.toMatchObject({ status: 404 })
  })
})

describe('useStopDepartures', () => {
  it('loads on mount and goes from loading to ready', async () => {
    stubFetch()
    const { api } = mountBoard()
    expect(api().status.value).toBe('loading')
    pending[0]!.resolve(jsonResponse(named('First')))
    await flushPromises()
    expect(api().status.value).toBe('ready')
    expect(api().data.value?.stop.name).toBe('First')
  })

  it('does not request anything without a stop', async () => {
    stubFetch()
    const { api } = mountBoard(null)
    await flushPromises()
    expect(pending).toHaveLength(0)
    expect(api().status.value).toBe('idle')
  })

  it('refreshes 30 s after the previous request finished, not on a fixed clock', async () => {
    stubFetch()
    mountBoard()
    await vi.advanceTimersByTimeAsync(10_000)
    pending[0]!.resolve(jsonResponse(named('A')))
    await flushPromises()
    await vi.advanceTimersByTimeAsync(DEPARTURES_REFRESH_MS - 1)
    expect(pending).toHaveLength(1)
    await vi.advanceTimersByTimeAsync(1)
    expect(pending).toHaveLength(2)
  })

  it('does not start a new timer while a request is in flight (no overlapping requests)', async () => {
    stubFetch()
    mountBoard()
    pending[0]!.resolve(jsonResponse(named('A')))
    await flushPromises()
    await vi.advanceTimersByTimeAsync(DEPARTURES_REFRESH_MS)
    expect(pending).toHaveLength(2)
    await vi.advanceTimersByTimeAsync(DEPARTURES_REFRESH_MS * 3)
    expect(pending).toHaveLength(2)
  })

  it('pauses while the document is hidden and refreshes at once when visible again', async () => {
    stubFetch()
    mountBoard()
    pending[0]!.resolve(jsonResponse(named('A')))
    await flushPromises()
    setVisibility('hidden')
    await vi.advanceTimersByTimeAsync(DEPARTURES_REFRESH_MS * 4)
    expect(pending).toHaveLength(1)
    setVisibility('visible')
    await flushPromises()
    expect(pending).toHaveLength(2)
  })

  it('aborts the in-flight request when a newer one starts and ignores its late result', async () => {
    stubFetch()
    const { api } = mountBoard()
    api().reload()
    await flushPromises()
    expect(pending).toHaveLength(2)
    expect(pending[0]!.signal?.aborted).toBe(true)
    expect(pending[1]!.signal?.aborted).toBe(false)
    pending[1]!.resolve(jsonResponse(named('New')))
    await flushPromises()
    pending[0]!.resolve(jsonResponse(named('Old')))
    await flushPromises()
    expect(api().data.value?.stop.name).toBe('New')
  })

  it('drops the old board and fetches the new stop when the stop changes', async () => {
    stubFetch()
    const { api, stop } = mountBoard()
    pending[0]!.resolve(jsonResponse(named('A')))
    await flushPromises()
    stop.value = 'feed_a:stop_9'
    await flushPromises()
    expect(api().data.value).toBeNull()
    expect(pending[1]!.url).toContain('feed_a%3Astop_9')
  })

  it('keeps the last board and records refreshError when a refresh fails', async () => {
    stubFetch()
    const { api } = mountBoard()
    pending[0]!.resolve(jsonResponse(named('A')))
    await flushPromises()
    await vi.advanceTimersByTimeAsync(DEPARTURES_REFRESH_MS)
    pending[1]!.resolve(jsonResponse({ error: { code: 'x', message: 'boom' } }, 500))
    await flushPromises()
    expect(api().data.value?.stop.name).toBe('A')
    expect(api().status.value).toBe('ready')
    expect(api().refreshError.value).not.toBeNull()
    expect(api().error.value).toBeNull()
    // It keeps trying, and a success clears the warning.
    await vi.advanceTimersByTimeAsync(DEPARTURES_REFRESH_MS)
    pending[2]!.resolve(jsonResponse(named('B')))
    await flushPromises()
    expect(api().refreshError.value).toBeNull()
    expect(api().data.value?.stop.name).toBe('B')
  })

  it('sets the error status when the first load fails and does not retry by itself', async () => {
    stubFetch()
    const { api } = mountBoard()
    pending[0]!.resolve(jsonResponse({ error: { code: 'x', message: 'boom' } }, 500))
    await flushPromises()
    expect(api().status.value).toBe('error')
    expect(api().data.value).toBeNull()
    await vi.advanceTimersByTimeAsync(DEPARTURES_REFRESH_MS * 3)
    expect(pending).toHaveLength(1)
    api().reload()
    await flushPromises()
    expect(pending).toHaveLength(2)
  })

  it('counts down from the server time, not from the device clock', async () => {
    vi.setSystemTime(new Date('2030-01-01T00:00:00Z'))
    stubFetch()
    const { api } = mountBoard()
    pending[0]!.resolve(jsonResponse(board({ generated_at: '2026-11-16T10:00:00+01:00' })))
    await flushPromises()
    const generated = Date.parse('2026-11-16T10:00:00+01:00')
    expect(api().nowMs.value).toBe(generated)
    await vi.advanceTimersByTimeAsync(20_000)
    expect(api().nowMs.value).toBeGreaterThanOrEqual(generated + 20_000 - 10_000)
    expect(api().nowMs.value).toBeLessThanOrEqual(generated + 20_000)
  })

  it('stops refreshing and aborts after unmount', async () => {
    stubFetch()
    const { wrapper } = mountBoard()
    pending[0]!.resolve(jsonResponse(named('A')))
    await flushPromises()
    wrapper.unmount()
    await vi.advanceTimersByTimeAsync(DEPARTURES_REFRESH_MS * 3)
    expect(pending).toHaveLength(1)
    // keep fixture helper referenced
    expect(departure().line.short_name).toBe('7')
  })
})
