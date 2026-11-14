import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'

import { useFormat } from '@/composables/useFormat'
import { applyLocale } from '@/i18n'
import {
  formatDate,
  formatDateLong,
  formatDateTime,
  formatDistance,
  formatDuration,
  formatPrice,
  formatTime,
} from '@/i18n/format'
import { useCityStore } from '@/stores/city'

import { cityDetail } from './citiesFixtures'
import { resetEnvironment } from './helpers'

/** Replaces non-breaking and narrow no-break spaces so assertions can use plain spaces. */
const norm = (s: string) => s.replace(/[  ]/g, ' ')

const ISO = '2026-07-01T06:14:00Z'

beforeEach(() => resetEnvironment())

describe('time formatting', () => {
  it('shows Warsaw wall-clock time (24h) in both locales', () => {
    expect(formatTime(ISO, 'Europe/Warsaw')).toBe('08:14')
    applyLocale('en')
    expect(formatTime(ISO, 'Europe/Warsaw')).toBe('08:14')
  })

  it('uses the given time zone, not the browser one', () => {
    expect(formatTime(ISO, 'UTC')).toBe('06:14')
  })

  it('uses 24h clock for afternoon times in English', () => {
    applyLocale('en')
    expect(formatTime('2026-07-01T15:05:00Z', 'UTC')).toBe('15:05')
  })

  it('accepts Date, epoch ms and ISO string', () => {
    const d = new Date(ISO)
    expect(formatTime(d, 'UTC')).toBe('06:14')
    expect(formatTime(d.getTime(), 'UTC')).toBe('06:14')
  })

  it('handles winter time (UTC+1) and the DST boundary', () => {
    expect(formatTime('2026-01-15T06:14:00Z', 'Europe/Warsaw')).toBe('07:14')
    expect(formatTime('2026-03-29T00:59:00Z', 'Europe/Warsaw')).toBe('01:59')
    expect(formatTime('2026-03-29T01:00:00Z', 'Europe/Warsaw')).toBe('03:00')
  })

  it('shows midnight as 00:xx, not 24:xx', () => {
    expect(formatTime('2026-06-30T22:30:00Z', 'Europe/Warsaw')).toBe('00:30')
  })

  it('returns an empty string for invalid dates', () => {
    expect(formatTime('not a date', 'UTC')).toBe('')
    expect(formatTime(NaN, 'UTC')).toBe('')
    expect(formatTime(new Date('x'), 'UTC')).toBe('')
    expect(formatTime('', 'UTC')).toBe('')
  })

  it('falls back to Europe/Warsaw for unknown, empty or missing zones', () => {
    expect(formatTime(ISO, 'Mars/Olympus')).toBe('08:14')
    expect(formatTime(ISO, '')).toBe('08:14')
    expect(formatTime(ISO, null)).toBe('08:14')
    expect(formatTime(ISO)).toBe('08:14')
  })
})

describe('date formatting', () => {
  it('formats a date in Polish and English', () => {
    expect(norm(formatDate(ISO, 'Europe/Warsaw'))).toMatch(/1.*lip.*2026/)
    applyLocale('en')
    expect(norm(formatDate(ISO, 'Europe/Warsaw'))).toMatch(/Jul.*1.*2026/)
  })

  it('respects the zone when the date differs across zones', () => {
    const late = '2026-07-01T23:30:00Z'
    expect(norm(formatDate(late, 'UTC'))).toMatch(/\b1\b/)
    expect(norm(formatDate(late, 'Europe/Warsaw'))).toMatch(/\b2\b/)
  })

  it('formats a long date with weekday per locale', () => {
    expect(norm(formatDateLong(ISO, 'Europe/Warsaw')).toLowerCase()).toContain('środa')
    applyLocale('en')
    expect(formatDateLong(ISO, 'Europe/Warsaw')).toContain('Wednesday')
  })

  it('formats date and time together', () => {
    const pl = norm(formatDateTime(ISO, 'Europe/Warsaw'))
    expect(pl).toContain('08:14')
    expect(pl).toContain('2026')
    applyLocale('en')
    const en = norm(formatDateTime(ISO, 'UTC'))
    expect(en).toContain('06:14')
    expect(en).toContain('2026')
  })

  it('returns empty strings for invalid input', () => {
    expect(formatDate('bad')).toBe('')
    expect(formatDateLong('bad')).toBe('')
    expect(formatDateTime('bad')).toBe('')
  })
})

describe('price formatting', () => {
  it('formats PLN per locale', () => {
    expect(norm(formatPrice(4.6))).toBe('4,60 zł')
    applyLocale('en')
    expect(norm(formatPrice(4.6))).toBe('PLN 4.60')
  })

  it('formats zero and thousands', () => {
    expect(norm(formatPrice(0))).toBe('0,00 zł')
    expect(norm(formatPrice(12345.5))).toBe('12 345,50 zł')
  })

  it('returns an empty string for NaN and Infinity', () => {
    expect(formatPrice(NaN)).toBe('')
    expect(formatPrice(Infinity)).toBe('')
  })
})

describe('duration formatting', () => {
  it.each([
    [2700, '45 min'],
    [7200, '2 h'],
    [3900, '1 h 5 min'],
    [60, '1 min'],
    [0, '0 min'],
  ])('formats %s s as "%s" in both locales', (seconds, expected) => {
    expect(formatDuration(seconds)).toBe(expected)
    applyLocale('en')
    expect(formatDuration(seconds)).toBe(expected)
  })

  it('shows "< 1 min" for positive durations that round to zero minutes', () => {
    expect(formatDuration(1)).toBe('< 1 min')
    expect(formatDuration(29)).toBe('< 1 min')
  })

  it('rounds 30 s and above up to a minute', () => {
    expect(formatDuration(30)).toBe('1 min')
    expect(formatDuration(59)).toBe('1 min')
  })

  it('rolls 59m40s over to 1 h', () => {
    expect(formatDuration(3580)).toBe('1 h')
  })

  it('returns an empty string for negative, NaN and Infinity input', () => {
    expect(formatDuration(-5)).toBe('')
    expect(formatDuration(NaN)).toBe('')
    expect(formatDuration(Infinity)).toBe('')
  })
})

describe('distance formatting', () => {
  it('formats metres below 1 km as whole metres', () => {
    expect(formatDistance(347)).toBe('347 m')
    expect(formatDistance(0)).toBe('0 m')
    expect(formatDistance(346.6)).toBe('347 m')
  })

  it('uses a decimal comma in Polish and a point in English for km', () => {
    expect(norm(formatDistance(1200))).toBe('1,2 km')
    applyLocale('en')
    expect(formatDistance(1200)).toBe('1.2 km')
  })

  it('rounds 999.7 m up to 1000 m and shows it in km', () => {
    expect(norm(formatDistance(999.7))).toBe('1 km')
    applyLocale('en')
    expect(norm(formatDistance(999.7))).toBe('1 km')
  })

  it('shows 999.4 m as 999 m', () => {
    expect(formatDistance(999.4)).toBe('999 m')
  })

  it('returns an empty string for negative, NaN and Infinity input', () => {
    expect(formatDistance(-1)).toBe('')
    expect(formatDistance(NaN)).toBe('')
    expect(formatDistance(Infinity)).toBe('')
  })
})

describe('useFormat', () => {
  function setup(timezone?: string) {
    setActivePinia(createPinia())
    const store = useCityStore()
    if (timezone !== undefined) {
      store.cityId = 'alpha'
      store.details = { ...cityDetail('alpha'), timezone } as never
    }
    return { store, fmt: useFormat() }
  }

  it('defaults to Europe/Warsaw before city details are loaded', () => {
    const { fmt } = setup()
    expect(fmt.timeZone.value).toBe('Europe/Warsaw')
    expect(fmt.time(ISO)).toBe('08:14')
  })

  it('uses the selected city time zone', () => {
    const { fmt } = setup('UTC')
    expect(fmt.timeZone.value).toBe('UTC')
    expect(fmt.time(ISO)).toBe('06:14')
  })

  it('follows a city change', () => {
    const { store, fmt } = setup('UTC')
    expect(fmt.time(ISO)).toBe('06:14')
    store.details = { ...cityDetail('alpha'), timezone: 'Asia/Tokyo' } as never
    expect(fmt.time(ISO)).toBe('15:14')
  })

  it('ignores details belonging to a different city', () => {
    const { store, fmt } = setup('UTC')
    store.cityId = 'beta'
    expect(fmt.timeZone.value).toBe('Europe/Warsaw')
  })

  it('follows the locale switch for dates, prices, durations and distances', async () => {
    const { fmt } = setup()
    expect(norm(fmt.price(4.6))).toBe('4,60 zł')
    expect(norm(fmt.distance(1200))).toBe('1,2 km')
    expect(norm(fmt.dateLong(ISO)).toLowerCase()).toContain('środa')
    applyLocale('en')
    await nextTick()
    expect(norm(fmt.price(4.6))).toBe('PLN 4.60')
    expect(fmt.distance(1200)).toBe('1.2 km')
    expect(fmt.dateLong(ISO)).toContain('Wednesday')
    expect(fmt.duration(3900)).toBe('1 h 5 min')
    expect(fmt.date(ISO)).toContain('2026')
    expect(fmt.dateTime(ISO)).toContain('08:14')
  })
})
