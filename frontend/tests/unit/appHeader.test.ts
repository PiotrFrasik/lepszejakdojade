import { nextTick } from 'vue'

import AppHeader from '@/components/AppHeader.vue'
import { applyLocale } from '@/i18n'
import en from '@/locales/en.json'
import pl from '@/locales/pl.json'

import { mountApp, resetEnvironment } from './helpers'

beforeEach(() => resetEnvironment())

describe('AppHeader', () => {
  it('renders the navigation labels, city switcher and language toggle', async () => {
    const { wrapper } = await mountApp(AppHeader)
    const links = wrapper.findAll('.app-header__link').map((l) => l.text())
    expect(links).toEqual([pl.nav.journey, pl.nav.timetable, pl.nav.tickets, pl.nav.assistant])
    expect(wrapper.find('select').exists()).toBe(true)
    expect(wrapper.find('.language-toggle').exists()).toBe(true)
  })

  it('changes navigation text between pl and en', async () => {
    const { wrapper } = await mountApp(AppHeader)
    applyLocale('en')
    await nextTick()
    const links = wrapper.findAll('.app-header__link').map((l) => l.text())
    expect(links).toEqual([en.nav.journey, en.nav.timetable, en.nav.tickets, en.nav.assistant])
    expect(wrapper.find('nav').attributes('aria-label')).toBe(en.nav.label)
  })

  it('switches language through the embedded toggle', async () => {
    const { wrapper } = await mountApp(AppHeader)
    await wrapper.findAll('.language-toggle button')[1]!.trigger('click')
    expect(wrapper.find('nav').attributes('aria-label')).toBe(en.nav.label)
  })
})
