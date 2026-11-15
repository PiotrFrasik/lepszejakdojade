import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

import DepartureRow from '@/components/timetable/DepartureRow.vue'
import { applyLocale, i18n } from '@/i18n'
import en from '@/locales/en.json'
import pl from '@/locales/pl.json'

import { at, departure, liveDeparture, NOW } from './departuresFixtures'
import { resetEnvironment } from './helpers'

type Dep = ReturnType<typeof departure>

function render(d: Dep, realtime = true) {
  const pinia = createPinia()
  setActivePinia(pinia)
  return mount(DepartureRow, {
    props: { departure: d, realtimeAvailable: realtime, nowMs: NOW },
    global: { plugins: [pinia, i18n] },
  })
}

beforeEach(() => {
  resetEnvironment()
  applyLocale('en')
})

describe('DepartureRow', () => {
  it('shows line, headsign and platform; hides the platform when there is no code', () => {
    const w = render(departure({ platform_code: 'B2', headsign: 'Southfield' }))
    expect(w.text()).toContain('7')
    expect(w.text()).toContain('Southfield')
    expect(w.text()).toContain('Platform B2')
    expect(render(departure()).text()).not.toContain('Platform')
  })

  it('shows a scheduled row with a countdown and without any live marker', () => {
    const w = render(departure({ scheduled: at(5) }))
    expect(w.find('.departure__countdown').text()).toBe('in 5 min')
    expect(w.find('.departure__live').exists()).toBe(false)
    expect(w.find('.departure__badge').exists()).toBe(false)
  })

  it('shows "now" for a departure under a minute away', () => {
    expect(render(departure({ scheduled: at(0, 20) })).find('.departure__countdown').text()).toBe(
      'now',
    )
  })

  it('hides the countdown beyond 30 minutes', () => {
    expect(render(departure({ scheduled: at(45) })).find('.departure__countdown').exists()).toBe(
      false,
    )
  })

  it('shows a late departure with a +N min badge, struck-through scheduled time and live label', () => {
    const w = render(liveDeparture(300, { scheduled: at(10) }))
    expect(w.find('.departure__badge--late').text()).toBe('+5 min')
    expect(w.find('.departure__scheduled').exists()).toBe(true)
    expect(w.find('.departure__live').text()).toBe('live')
    expect(w.text()).toContain('delayed by 5 minutes')
    expect(w.text()).toContain('expected')
  })

  it('shows an early departure with a minus badge', () => {
    const w = render(liveDeparture(-120, { scheduled: at(10) }))
    expect(w.find('.departure__badge--early').text()).toBe('−2 min')
    expect(w.text()).toContain('2 minutes early')
  })

  it('shows an on-time live departure with an "on time" badge and no scheduled duplicate', () => {
    const w = render(liveDeparture(20, { scheduled: at(10) }))
    expect(w.find('.departure__badge--on-time').text()).toBe('on time')
    expect(w.find('.departure__scheduled').exists()).toBe(false)
    expect(w.find('.departure__live').exists()).toBe(true)
  })

  it('shows a canceled departure with a text badge, no countdown and no live label', () => {
    const w = render(departure({ status: 'canceled', scheduled: at(5) }))
    expect(w.find('.departure__badge--canceled').text()).toBe('Cancelled')
    expect(w.find('.departure__countdown').exists()).toBe(false)
    expect(w.find('.departure__live').exists()).toBe(false)
    expect(w.classes()).toContain('departure--canceled')
  })

  it('renders live rows as scheduled when realtime is unavailable', () => {
    const w = render(liveDeparture(300, { scheduled: at(10) }), false)
    expect(w.find('.departure__live').exists()).toBe(false)
    expect(w.find('.departure__badge').exists()).toBe(false)
    expect(w.find('.departure__countdown').text()).toBe('in 10 min')
  })

  it('conveys state in text, not only by colour (hidden labels present)', () => {
    const w = render(liveDeparture(300, { scheduled: at(10) }))
    expect(w.findAll('.visually-hidden').length).toBeGreaterThan(0)
    expect(w.find('.departure__headsign .visually-hidden').text()).toBe('towards')
  })

  it('uses Polish texts and plural forms in Polish', () => {
    applyLocale('pl')
    const late = render(liveDeparture(120, { scheduled: at(10) }))
    expect(late.find('.departure__live').text()).toBe('na żywo')
    expect(late.text()).toContain('opóźniony o 2 minuty')
    expect(render(liveDeparture(300, { scheduled: at(10) })).text()).toContain(
      'opóźniony o 5 minut',
    )
    expect(render(departure({ scheduled: at(5) })).find('.departure__countdown').text()).toBe(
      'za 5 min',
    )
    expect(render(departure({ scheduled: at(5) })).text()).toContain('odjazd za 5 minut')
    expect(render(departure({ scheduled: at(2) })).text()).toContain('odjazd za 2 minuty')
    expect(render(departure({ scheduled: at(1) })).text()).toContain('odjazd za 1 minutę')
    expect(render(departure({ scheduled: at(0, 10) })).find('.departure__countdown').text()).toBe(
      'teraz',
    )
    expect(render(departure({ status: 'canceled' })).text()).toContain('Odwołany')
    expect(render(liveDeparture(10)).text()).toContain('o czasie')
  })
})

describe('departures locale keys', () => {
  const plD = pl.timetable.departures as Record<string, string>
  const enD = en.timetable.departures as Record<string, string>

  it('has identical timetable.departures keys in pl and en', () => {
    expect(Object.keys(plD).sort()).toEqual(Object.keys(enD).sort())
  })

  it('has no empty texts and keeps placeholders consistent between languages', () => {
    const names = (s: string) => [...new Set(s.match(/\{\w+\}/g) ?? [])].sort()
    for (const key of Object.keys(enD)) {
      expect(plD[key]!.trim(), key).not.toBe('')
      expect(names(plD[key]!), key).toEqual(names(enD[key]!))
    }
  })

  it('gives the plural messages three choices in both languages', () => {
    for (const d of [plD, enD]) {
      for (const key of ['inMinutesLong', 'lateLong', 'earlyLong']) {
        expect(d[key]!.split('|'), key).toHaveLength(3)
      }
    }
  })
})
