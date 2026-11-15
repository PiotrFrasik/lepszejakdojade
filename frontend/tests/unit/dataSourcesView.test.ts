import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import { getDataSources } from '@/api/client'
import { applyLocale, i18n } from '@/i18n'
import { formatDate, formatDateTime } from '@/i18n/format'
import en from '@/locales/en.json'
import pl from '@/locales/pl.json'
import { routes } from '@/router'
import { useCityStore } from '@/stores/city'
import type { DataSourcesResponse } from '@/types/api'
import { serviceDateToDate } from '@/utils/serviceDate'
import DataSourcesView from '@/views/DataSourcesView.vue'

import { jsonResponse, resetEnvironment } from './helpers'

type Tree = { [key: string]: string | Tree }

function flatten(tree: Tree, prefix = ''): string[] {
  return Object.entries(tree).flatMap(([key, value]) => {
    const path = prefix ? `${prefix}.${key}` : key
    return typeof value === 'object' ? flatten(value, path) : [path]
  })
}

const FIXTURE: DataSourcesResponse = {
  cities: [
    {
      id: 'alpha',
      name: 'Alpha',
      sources: [
        {
          name: 'Alpha Transit Authority',
          url: 'https://data.alpha.example/gtfs/',
          licence: 'CC BY 4.0',
          licence_url: 'https://licences.example/by/4.0/',
          description: 'Trams and buses of Alpha.',
        },
        {
          name: 'Alpha Rail Open Data',
          url: 'https://rail.alpha.example/',
          licence: 'Custom Terms',
          licence_url: null,
          description: null,
        },
        {
          name: 'Alpha Mystery Source',
          url: 'https://mystery.alpha.example/',
          licence: null,
          licence_url: null,
          description: null,
        },
      ],
      feeds: [
        {
          feed_id: 'alpha_tram',
          publisher_name: 'Alpha Publisher',
          last_modified: '2026-11-13T22:10:00+01:00',
          downloaded_at: '2026-11-14T03:00:12+01:00',
          imported_at: '2026-11-14T03:02:40+01:00',
          service_start_date: '2026-11-14',
          service_end_date: '2026-12-31',
        },
        {
          feed_id: 'alpha_bus',
          publisher_name: null,
          last_modified: null,
          downloaded_at: '2026-11-14T03:00:12+01:00',
          imported_at: null,
          service_start_date: null,
          service_end_date: null,
        },
      ],
    },
    {
      id: 'beta',
      name: 'Beta',
      sources: [],
      feeds: [],
    },
  ],
}

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}

const fetchMock = vi.fn()
const mounted: { unmount: () => void }[] = []

async function mountView(cityId = 'alpha') {
  const pinia = createPinia()
  setActivePinia(pinia)
  useCityStore().cityId = cityId
  const router = createRouter({ history: createMemoryHistory(), routes })
  await router.push('/data-sources')
  await router.isReady()
  const wrapper = mount(DataSourcesView, {
    global: { plugins: [pinia, i18n, router] },
    attachTo: document.body,
  })
  mounted.push(wrapper)
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  resetEnvironment()
  applyLocale('en')
  fetchMock.mockReset()
  fetchMock.mockImplementation(async () => jsonResponse(clone(FIXTURE)))
  vi.stubGlobal('fetch', fetchMock)
})
afterEach(() => {
  // Unmount first: live views would otherwise react to later locale changes.
  mounted.splice(0).forEach((w) => w.unmount())
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

describe('getDataSources client', () => {
  it('requests /api/v1/data-sources/ with Accept-Language of the UI locale', async () => {
    await getDataSources()
    expect(fetchMock.mock.calls[0]![0]).toBe('/api/v1/data-sources/')
    const headers = fetchMock.mock.calls[0]![1].headers as Record<string, string>
    expect(headers['Accept-Language']).toBe('en')
  })
})

describe('DataSourcesView', () => {
  it('shows the static intro and processed-data statement while loading', async () => {
    fetchMock.mockImplementation(() => new Promise(() => {}))
    const wrapper = await mountView()
    expect(wrapper.find('h1').text()).toBe(en.dataSources.title)
    expect(wrapper.text()).toContain(en.dataSources.processed)
    expect(wrapper.find('[role="status"]').text()).toBe(en.dataSources.loading)
    expect(wrapper.find('.data-sources__city').exists()).toBe(false)
  })

  it('renders every city with its sources and licences after loading', async () => {
    const wrapper = await mountView()
    expect(wrapper.find('[role="status"]').exists()).toBe(false)
    expect(wrapper.findAll('.data-sources__city')).toHaveLength(2)
    expect(wrapper.text()).toContain('Alpha Transit Authority')
    expect(wrapper.text()).toContain('Trams and buses of Alpha.')

    const link = wrapper.findAll('a').find((a) => a.text().includes('CC BY 4.0'))!
    expect(link.attributes('href')).toBe('https://licences.example/by/4.0/')
    expect(link.attributes('target')).toBe('_blank')
    expect(link.attributes('rel')).toContain('noopener')

    const source = wrapper.findAll('a').find((a) => a.text().includes('Alpha Transit Authority'))!
    expect(source.attributes('href')).toBe('https://data.alpha.example/gtfs/')
    expect(source.attributes('rel')).toContain('noopener')
  })

  it('shows a licence without a URL as plain text, not a link', async () => {
    const wrapper = await mountView()
    expect(wrapper.text()).toContain('Custom Terms')
    expect(wrapper.findAll('a').some((a) => a.text().includes('Custom Terms'))).toBe(false)
  })

  it('shows "unknown" for a null licence and omits a null description', async () => {
    const wrapper = await mountView()
    const list = wrapper.findAll('.data-sources__city')[0]!.findAll('.data-sources__list')[0]!
    const mystery = list.findAll('li')[2]!
    expect(mystery.text()).toContain('Alpha Mystery Source')
    expect(mystery.find('.data-sources__licence').text()).toContain(en.dataSources.unknown)
    expect(mystery.find('.data-sources__description').exists()).toBe(false)
  })

  it('falls back to the licence URL as link text when only the URL is known', async () => {
    const data = clone(FIXTURE)
    data.cities[0]!.sources = [
      {
        name: 'Url Only Source',
        url: 'https://u.alpha.example/',
        licence: null,
        licence_url: 'https://licences.example/custom',
        description: null,
      },
    ]
    fetchMock.mockImplementation(async () => jsonResponse(data))
    const wrapper = await mountView()
    const link = wrapper
      .findAll('a')
      .find((a) => a.attributes('href') === 'https://licences.example/custom')!
    expect(link.text()).toContain('https://licences.example/custom')
  })

  it('formats feed timestamps and the service period for the UI locale', async () => {
    const wrapper = await mountView()
    const feed = wrapper.findAll('.data-sources__facts')[0]!
    expect(feed.text()).toContain('Alpha Publisher')
    expect(feed.text()).toContain('alpha_tram')
    expect(feed.text()).toContain(formatDateTime('2026-11-13T22:10:00+01:00'))
    expect(feed.text()).toContain(formatDateTime('2026-11-14T03:02:40+01:00'))
    const start = formatDate(serviceDateToDate('2026-11-14'))
    const end = formatDate(serviceDateToDate('2026-12-31'))
    expect(feed.text()).toContain(`${start} – ${end}`)
  })

  it('shows "unknown" for null feed fields', async () => {
    const wrapper = await mountView()
    const feed = wrapper.findAll('.data-sources__facts')[1]!
    const values = feed.findAll('dd').map((dd) => dd.text())
    // Order: publisher, feed id, created, downloaded, imported, service period.
    expect(values[0]).toBe(en.dataSources.unknown)
    expect(values[1]).toBe('alpha_bus')
    expect(values[2]).toBe(en.dataSources.unknown)
    expect(values[3]).not.toBe(en.dataSources.unknown)
    expect(values[4]).toBe(en.dataSources.unknown)
    expect(values[5]).toBe(en.dataSources.unknown)
  })

  it('shows the empty-feeds and empty-sources messages for a city without data', async () => {
    const wrapper = await mountView()
    const beta = wrapper.findAll('.data-sources__city')[1]!
    expect(beta.text()).toContain('Beta')
    expect(beta.text()).toContain(en.dataSources.noFeeds)
    expect(beta.text()).toContain(en.dataSources.noSources)
  })

  it('shows a message when no cities are configured', async () => {
    fetchMock.mockImplementation(async () => jsonResponse({ cities: [] }))
    const wrapper = await mountView()
    expect(wrapper.text()).toContain(en.dataSources.noCities)
    expect(wrapper.find('.data-sources__city').exists()).toBe(false)
  })

  it('puts the selected city first and keeps API order for the rest', async () => {
    const wrapper = await mountView('beta')
    const names = wrapper.findAll('.data-sources__city h2').map((h) => h.text())
    expect(names).toEqual(['Beta', 'Alpha'])
  })

  it('keeps API order when the selected city is not in the response', async () => {
    const wrapper = await mountView('gamma')
    const names = wrapper.findAll('.data-sources__city h2').map((h) => h.text())
    expect(names).toEqual(['Alpha', 'Beta'])
  })

  it('shows an error with retry, then recovers on retry', async () => {
    fetchMock.mockImplementationOnce(async () =>
      jsonResponse({ error: { code: 'server_error', message: 'x' } }, 500),
    )
    const wrapper = await mountView()
    expect(wrapper.find('[role="alert"]').exists()).toBe(true)
    expect(wrapper.find('.data-sources__city').exists()).toBe(false)
    // The static statement stays visible on error.
    expect(wrapper.text()).toContain(en.dataSources.processed)

    await wrapper.find('[role="alert"] button').trigger('click')
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.findAll('.data-sources__city')).toHaveLength(2)
  })

  it('shows a network error when fetch rejects', async () => {
    fetchMock.mockImplementationOnce(async () => {
      throw new TypeError('Failed to fetch')
    })
    const wrapper = await mountView()
    expect(wrapper.find('[role="alert"]').text()).toContain(en.errors.network)
  })

  it('re-fetches with the new Accept-Language and re-renders when the locale changes', async () => {
    fetchMock.mockImplementation(async (_url: string, init: RequestInit) => {
      const lang = (init.headers as Record<string, string>)['Accept-Language']
      const data = clone(FIXTURE)
      data.cities[0]!.name = lang === 'pl' ? 'Alfa' : 'Alpha'
      data.cities[0]!.sources[0]!.description = lang === 'pl' ? 'Opis po polsku.' : 'English text.'
      return jsonResponse(data)
    })
    const wrapper = await mountView()
    expect(wrapper.text()).toContain('English text.')
    expect(fetchMock).toHaveBeenCalledTimes(1)

    applyLocale('pl')
    await flushPromises()

    expect(fetchMock).toHaveBeenCalledTimes(2)
    const headers = fetchMock.mock.calls[1]![1].headers as Record<string, string>
    expect(headers['Accept-Language']).toBe('pl')
    expect(wrapper.text()).toContain('Alfa')
    expect(wrapper.text()).toContain('Opis po polsku.')
    expect(wrapper.text()).toContain(pl.dataSources.processed)
    expect(wrapper.text()).not.toContain('English text.')
  })

  it('formats dates in the current UI locale after a language switch', async () => {
    const wrapper = await mountView()
    const before = wrapper.findAll('.data-sources__facts')[0]!.text()
    applyLocale('pl')
    await flushPromises()
    const after = wrapper.findAll('.data-sources__facts')[0]!.text()
    expect(after).toContain(formatDateTime('2026-11-14T03:00:12+01:00'))
    expect(after).not.toBe(before)
  })
})

describe('dataSources locale keys', () => {
  it('has identical keys in pl and en', () => {
    const only = (tree: Tree) =>
      flatten(tree)
        .filter((k) => k.startsWith('dataSources.'))
        .sort()
    expect(only(en as Tree)).toEqual(only(pl as Tree))
    expect(only(pl as Tree).length).toBeGreaterThan(15)
  })

  it('has no empty translations', () => {
    for (const locale of [pl, en]) {
      for (const value of Object.values(locale.dataSources)) {
        expect(String(value).trim()).not.toBe('')
      }
    }
  })
})
