import { nextTick } from 'vue'

import AppFooter from '@/components/AppFooter.vue'
import CityPicker from '@/components/CityPicker.vue'
import LanguageToggle from '@/components/LanguageToggle.vue'
import { applyLocale } from '@/i18n'
import en from '@/locales/en.json'
import pl from '@/locales/pl.json'
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

describe('LanguageToggle', () => {
  it('marks the active locale with aria-pressed', async () => {
    const { wrapper } = await mountApp(LanguageToggle)
    const [plBtn, enBtn] = wrapper.findAll('button')
    expect(plBtn!.attributes('aria-pressed')).toBe('true')
    expect(enBtn!.attributes('aria-pressed')).toBe('false')
  })

  it('switches locale, updates html lang, persists and flips aria-pressed', async () => {
    const { wrapper } = await mountApp(LanguageToggle)
    const [plBtn, enBtn] = wrapper.findAll('button')
    await enBtn!.trigger('click')
    await nextTick()
    expect(document.documentElement.lang).toBe('en')
    expect(window.localStorage.getItem(STORAGE_KEYS.locale)).toBe('en')
    expect(enBtn!.attributes('aria-pressed')).toBe('true')
    expect(plBtn!.attributes('aria-pressed')).toBe('false')
    await plBtn!.trigger('click')
    expect(document.documentElement.lang).toBe('pl')
    expect(window.localStorage.getItem(STORAGE_KEYS.locale)).toBe('pl')
  })

  it('has a translated group label', async () => {
    const { wrapper } = await mountApp(LanguageToggle)
    expect(wrapper.find('[role="group"]').attributes('aria-label')).toBe(pl.language.label)
    await wrapper.findAll('button')[1]!.trigger('click')
    expect(wrapper.find('[role="group"]').attributes('aria-label')).toBe(en.language.label)
  })
})

describe('rendered text follows the locale', () => {
  it('AppFooter text changes between pl and en', async () => {
    const { wrapper } = await mountApp(AppFooter)
    expect(wrapper.text()).toContain(pl.footer.demoNotice)
    expect(wrapper.text()).toContain(pl.footer.dataSources)
    applyLocale('en')
    await nextTick()
    expect(wrapper.text()).toContain(en.footer.demoNotice)
    expect(wrapper.text()).toContain(en.footer.dataSources)
    expect(wrapper.text()).not.toContain(pl.footer.demoNotice)
  })

  it('CityPicker text changes between pl and en', async () => {
    const { wrapper } = await mountApp(CityPicker)
    expect(wrapper.find('h2').text()).toBe(pl.city.pickerTitle)
    applyLocale('en')
    await nextTick()
    expect(wrapper.find('h2').text()).toBe(en.city.pickerTitle)
    expect(wrapper.find('p').text()).toBe(en.city.pickerDescription)
  })
})
