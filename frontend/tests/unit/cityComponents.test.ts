import type { Component } from 'vue'
import { nextTick } from 'vue'

import App from '@/App.vue'
import CityPicker from '@/components/CityPicker.vue'
import CitySwitcher from '@/components/CitySwitcher.vue'
import { applyLocale } from '@/i18n'
import en from '@/locales/en.json'
import pl from '@/locales/pl.json'
import { useCityStore } from '@/stores/city'
import { STORAGE_KEYS } from '@/utils/storage'

import { cityList, makeCitiesFetch, settle } from './citiesFixtures'
import { jsonResponse, mountApp, resetEnvironment } from './helpers'

/** Mounts a component alone and starts the city load, as App.vue does. */
async function mountInited(component: Component) {
  const result = await mountApp(component)
  useCityStore(result.pinia).init()
  return result
}

beforeEach(() => {
  resetEnvironment()
  vi.stubGlobal('fetch', makeCitiesFetch().fn)
})
afterEach(() => vi.unstubAllGlobals())

describe('CityPicker in App', () => {
  it('is shown when no city is stored', async () => {
    const { wrapper } = await mountApp(App)
    await settle()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(true)
    expect(wrapper.findAll('button[data-city]')).toHaveLength(2)
    wrapper.unmount()
  })

  it('is not shown when a valid city is stored', async () => {
    window.localStorage.setItem(STORAGE_KEYS.city, 'alpha')
    const { wrapper } = await mountApp(App)
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    await settle()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('is shown again and the id removed when the stored city is not in the list', async () => {
    window.localStorage.setItem(STORAGE_KEYS.city, 'gotham')
    const { wrapper } = await mountApp(App)
    await settle()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(true)
    expect(window.localStorage.getItem(STORAGE_KEYS.city)).toBeNull()
    wrapper.unmount()
  })

  it('stores the choice and closes after choosing a city', async () => {
    const { wrapper } = await mountApp(App)
    await settle()
    await wrapper.find('button[data-city="beta"]').trigger('click')
    await settle()
    expect(window.localStorage.getItem(STORAGE_KEYS.city)).toBe('beta')
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('makes the app shell inert while no city is chosen', async () => {
    const { wrapper } = await mountApp(App)
    await settle()
    expect(wrapper.find('.app-shell').attributes('inert')).toBeDefined()
    await wrapper.find('button[data-city="alpha"]').trigger('click')
    await settle()
    expect(wrapper.find('.app-shell').attributes('inert')).toBeUndefined()
    wrapper.unmount()
  })
})

describe('CityPicker alone', () => {
  it('lists cities by the names returned by the API', async () => {
    const { wrapper } = await mountInited(CityPicker)
    await settle()
    expect(wrapper.findAll('button[data-city]').map((b) => b.text())).toEqual(['Alfa', 'Beta'])
  })

  it('shows a busy loading state while the list loads', async () => {
    vi.stubGlobal('fetch', makeCitiesFetch({ list: () => new Promise<Response>(() => {}) }).fn)
    const { wrapper } = await mountInited(CityPicker)
    await nextTick()
    expect(wrapper.find('[role="status"]').text()).toContain(pl.city.loading)
    expect(wrapper.find('[role="dialog"]').attributes('aria-busy')).toBe('true')
    expect(wrapper.find('button[data-city]').exists()).toBe(false)
  })

  it('shows an alert with a retry button on error and recovers after retry', async () => {
    let fail = true
    vi.stubGlobal(
      'fetch',
      makeCitiesFetch({
        list: (lang) => (fail ? jsonResponse({}, 500) : jsonResponse(cityList(lang))),
      }).fn,
    )
    const { wrapper } = await mountInited(CityPicker)
    await settle()
    expect(wrapper.find('[role="alert"]').text()).toContain(pl.city.loadError)
    const retry = wrapper.find('button.city-picker__retry')
    expect(retry.text()).toBe(pl.city.retry)
    fail = false
    await retry.trigger('click')
    await settle()
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.findAll('button[data-city]')).toHaveLength(2)
  })

  it('keeps the error visible while retrying, with a disabled busy retry button', async () => {
    let fail = true
    let release: () => void = () => {}
    vi.stubGlobal(
      'fetch',
      makeCitiesFetch({
        list: (lang) => {
          if (fail) return jsonResponse({}, 500)
          return new Promise<Response>((resolve) => {
            release = () => resolve(jsonResponse(cityList(lang)))
          })
        },
      }).fn,
    )
    const { wrapper } = await mountInited(CityPicker)
    await settle()
    fail = false
    await wrapper.find('button.city-picker__retry').trigger('click')
    await nextTick()
    const retry = wrapper.find('button.city-picker__retry')
    expect(wrapper.find('[role="alert"]').exists()).toBe(true)
    expect(retry.attributes('disabled')).toBeDefined()
    expect(retry.text()).toBe(pl.city.retrying)
    expect(wrapper.find('[role="dialog"]').attributes('aria-busy')).toBe('true')
    release()
    await settle()
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.findAll('button[data-city]')).toHaveLength(2)
    expect(wrapper.find('[role="dialog"]').attributes('aria-busy')).toBeUndefined()
  })

  it('shows an empty-list message', async () => {
    vi.stubGlobal('fetch', makeCitiesFetch({ list: () => jsonResponse([]) }).fn)
    const { wrapper } = await mountInited(CityPicker)
    await settle()
    expect(wrapper.find('[role="status"]').text()).toContain(pl.city.empty)
    expect(wrapper.find('button[data-city]').exists()).toBe(false)
  })

  it('shows the error message in English when the language is English', async () => {
    vi.stubGlobal('fetch', makeCitiesFetch({ list: () => jsonResponse({}, 500) }).fn)
    applyLocale('en')
    const { wrapper } = await mountInited(CityPicker)
    await settle()
    expect(wrapper.find('[role="alert"]').text()).toContain(en.city.loadError)
  })
})

describe('CitySwitcher', () => {
  it('is disabled while the list is empty', async () => {
    vi.stubGlobal('fetch', makeCitiesFetch({ list: () => new Promise<Response>(() => {}) }).fn)
    const { wrapper } = await mountInited(CitySwitcher)
    await nextTick()
    expect(wrapper.find('select').attributes('disabled')).toBeDefined()
  })

  it('changes the selected city and persists it', async () => {
    window.localStorage.setItem(STORAGE_KEYS.city, 'alpha')
    const { wrapper, pinia } = await mountInited(CitySwitcher)
    await settle()
    const select = wrapper.find('select')
    expect((select.element as HTMLSelectElement).value).toBe('alpha')
    await select.setValue('beta')
    expect(useCityStore(pinia).cityId).toBe('beta')
    expect(window.localStorage.getItem(STORAGE_KEYS.city)).toBe('beta')
  })

  it('has an accessible translated label', async () => {
    const { wrapper } = await mountInited(CitySwitcher)
    const id = wrapper.find('select').attributes('id')
    expect(wrapper.find(`label[for="${id}"]`).text()).toBe(pl.city.label)
  })
})
