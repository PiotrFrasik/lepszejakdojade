import { nextTick } from 'vue'

import App from '@/App.vue'
import CityPicker from '@/components/CityPicker.vue'
import CitySwitcher from '@/components/CitySwitcher.vue'
import pl from '@/locales/pl.json'
import { useCityStore } from '@/stores/city'
import { STORAGE_KEYS } from '@/utils/storage'

import { jsonResponse, mountApp, resetEnvironment } from './helpers'

beforeEach(() => {
  resetEnvironment()
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => jsonResponse({ status: 'ok', checks: {}, version: '1' })),
  )
})
afterEach(() => vi.unstubAllGlobals())

describe('CityPicker in App', () => {
  it('is shown when no city is stored', async () => {
    const { wrapper } = await mountApp(App)
    expect(wrapper.find('[role="dialog"]').exists()).toBe(true)
    expect(wrapper.findAll('button[data-city]')).toHaveLength(2)
    wrapper.unmount()
  })

  it('is not shown when a city is stored', async () => {
    window.localStorage.setItem(STORAGE_KEYS.city, 'krakow')
    const { wrapper } = await mountApp(App)
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('stores the choice and closes after choosing a city', async () => {
    const { wrapper } = await mountApp(App)
    await wrapper.find('button[data-city="warszawa"]').trigger('click')
    await nextTick()
    expect(window.localStorage.getItem(STORAGE_KEYS.city)).toBe('warszawa')
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('makes the app shell inert while no city is chosen', async () => {
    const { wrapper } = await mountApp(App)
    expect(wrapper.find('.app-shell').attributes('inert')).toBeDefined()
    await wrapper.find('button[data-city="krakow"]').trigger('click')
    expect(wrapper.find('.app-shell').attributes('inert')).toBeUndefined()
    wrapper.unmount()
  })
})

describe('CityPicker alone', () => {
  it('lists cities by their proper names', async () => {
    const { wrapper } = await mountApp(CityPicker)
    const names = wrapper.findAll('button[data-city]').map((b) => b.text())
    expect(names).toEqual(['Kraków', 'Warszawa'])
  })
})

describe('CitySwitcher', () => {
  it('changes the selected city and persists it', async () => {
    window.localStorage.setItem(STORAGE_KEYS.city, 'krakow')
    const { wrapper, pinia } = await mountApp(CitySwitcher)
    const select = wrapper.find('select')
    expect((select.element as HTMLSelectElement).value).toBe('krakow')
    await select.setValue('warszawa')
    expect(useCityStore(pinia).cityId).toBe('warszawa')
    expect(window.localStorage.getItem(STORAGE_KEYS.city)).toBe('warszawa')
  })

  it('has an accessible translated label', async () => {
    const { wrapper } = await mountApp(CitySwitcher)
    const id = wrapper.find('select').attributes('id')
    expect(wrapper.find(`label[for="${id}"]`).text()).toBe(pl.city.label)
  })
})
