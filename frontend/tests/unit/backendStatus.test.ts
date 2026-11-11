import { flushPromises } from '@vue/test-utils'

import BackendStatus from '@/components/BackendStatus.vue'
import { applyLocale } from '@/i18n'
import en from '@/locales/en.json'
import pl from '@/locales/pl.json'

import { jsonResponse, mountApp, resetEnvironment } from './helpers'

beforeEach(() => resetEnvironment())
afterEach(() => vi.unstubAllGlobals())

describe('BackendStatus', () => {
  it('shows the checking state before the response arrives', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => new Promise(() => {})),
    )
    const { wrapper } = await mountApp(BackendStatus)
    expect(wrapper.attributes('data-status')).toBe('checking')
    expect(wrapper.text()).toContain(pl.status.checking)
  })

  it('shows ok with the version', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse({ status: 'ok', checks: { database: 'ok' }, version: '1.2.3' }),
      ),
    )
    const { wrapper } = await mountApp(BackendStatus)
    await flushPromises()
    expect(wrapper.attributes('data-status')).toBe('ok')
    expect(wrapper.text()).toContain(pl.status.ok)
    expect(wrapper.text()).toContain('1.2.3')
  })

  it('shows degraded for a 503 health body', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse({ status: 'error', checks: { database: 'error' }, version: '1.2.3' }, 503),
      ),
    )
    const { wrapper } = await mountApp(BackendStatus)
    await flushPromises()
    expect(wrapper.attributes('data-status')).toBe('degraded')
    expect(wrapper.text()).toContain(pl.status.degraded)
  })

  it('shows unavailable when the request fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    const { wrapper } = await mountApp(BackendStatus)
    await flushPromises()
    expect(wrapper.attributes('data-status')).toBe('unavailable')
    expect(wrapper.text()).toContain(pl.status.unavailable)
    expect(wrapper.text()).not.toContain('(')
  })

  it('shows unavailable on a non-JSON error response', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('Bad Gateway', { status: 502 })),
    )
    const { wrapper } = await mountApp(BackendStatus)
    await flushPromises()
    expect(wrapper.attributes('data-status')).toBe('unavailable')
  })

  it('translates the label when the locale changes', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('x')))
    const { wrapper } = await mountApp(BackendStatus)
    await flushPromises()
    applyLocale('en')
    await flushPromises()
    expect(wrapper.text()).toContain(en.status.unavailable)
  })
})
