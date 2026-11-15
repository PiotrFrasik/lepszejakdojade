import { polishPluralRule } from '@/i18n'
import { departureTiming, effectiveTime, minutesUntil } from '@/utils/departures'

import { at, departure, liveDeparture, NOW } from './departuresFixtures'

describe('departureTiming', () => {
  it('classifies a delay under one minute (either way) as on time', () => {
    expect(departureTiming(liveDeparture(0), true)).toEqual({ kind: 'on_time' })
    expect(departureTiming(liveDeparture(59), true)).toEqual({ kind: 'on_time' })
    expect(departureTiming(liveDeparture(-59), true)).toEqual({ kind: 'on_time' })
  })

  it('classifies a positive delay of a minute or more as late, rounded to minutes', () => {
    expect(departureTiming(liveDeparture(60), true)).toEqual({ kind: 'late', minutes: 1 })
    expect(departureTiming(liveDeparture(89), true)).toEqual({ kind: 'late', minutes: 1 })
    expect(departureTiming(liveDeparture(90), true)).toEqual({ kind: 'late', minutes: 2 })
    expect(departureTiming(liveDeparture(300), true)).toEqual({ kind: 'late', minutes: 5 })
  })

  it('classifies a negative delay as early with a positive minute count', () => {
    expect(departureTiming(liveDeparture(-120), true)).toEqual({ kind: 'early', minutes: 2 })
    expect(departureTiming(liveDeparture(-60), true)).toEqual({ kind: 'early', minutes: 1 })
  })

  it('classifies a canceled departure as canceled', () => {
    expect(departureTiming(departure({ status: 'canceled' }), true)).toEqual({ kind: 'canceled' })
  })

  it('treats a departure without live data as scheduled', () => {
    expect(departureTiming(departure(), true)).toEqual({ kind: 'scheduled' })
  })

  it('never shows live data when realtime is unavailable, even for malformed live rows', () => {
    expect(departureTiming(liveDeparture(300), false)).toEqual({ kind: 'scheduled' })
    expect(departureTiming(departure({ status: 'canceled' }), false)).toEqual({ kind: 'scheduled' })
  })

  it('does not show live for a live row missing expected or delay', () => {
    expect(departureTiming(departure({ status: 'live', delay_seconds: 120 }), true).kind).toBe(
      'scheduled',
    )
    expect(
      departureTiming(departure({ status: 'live', expected: at(12), delay_seconds: null }), true)
        .kind,
    ).toBe('scheduled')
  })
})

describe('effectiveTime', () => {
  it('uses the expected time for live rows and the scheduled one otherwise', () => {
    const live = liveDeparture(180)
    expect(effectiveTime(live, true)).toBe(live.expected)
    expect(effectiveTime(live, false)).toBe(live.scheduled)
    const plain = departure()
    expect(effectiveTime(plain, true)).toBe(plain.scheduled)
  })
})

describe('minutesUntil', () => {
  it('returns whole minutes, rounding down', () => {
    expect(minutesUntil(departure({ scheduled: at(5, 59) }), true, NOW)).toBe(5)
    expect(minutesUntil(departure({ scheduled: at(5) }), true, NOW)).toBe(5)
  })

  it('returns 0 (now) for under a minute and for slightly past departures', () => {
    expect(minutesUntil(departure({ scheduled: at(0, 30) }), true, NOW)).toBe(0)
    expect(minutesUntil(departure({ scheduled: at(-1) }), true, NOW)).toBe(0)
  })

  it('returns null beyond 30 minutes, for canceled and for unparsable times', () => {
    expect(minutesUntil(departure({ scheduled: at(30) }), true, NOW)).toBe(30)
    expect(minutesUntil(departure({ scheduled: at(31) }), true, NOW)).toBeNull()
    expect(minutesUntil(departure({ status: 'canceled', scheduled: at(5) }), true, NOW)).toBeNull()
    expect(minutesUntil(departure({ scheduled: 'garbage' }), true, NOW)).toBeNull()
    expect(minutesUntil(departure(), true, Number.NaN)).toBeNull()
  })

  it('counts down to the expected time of a live departure', () => {
    expect(minutesUntil(liveDeparture(300, { scheduled: at(10) }), true, NOW)).toBe(15)
    expect(minutesUntil(liveDeparture(300, { scheduled: at(10) }), false, NOW)).toBe(10)
  })
})

describe('polishPluralRule', () => {
  const pick = (n: number) => polishPluralRule(n, 3)

  it('uses the "one" form only for 1', () => {
    expect(pick(1)).toBe(0)
  })

  it.each([2, 3, 4, 22, 23, 24, 102, 132])('uses the "few" form for %i', (n) => {
    expect(pick(n)).toBe(1)
  })

  it.each([0, 5, 11, 12, 13, 14, 21, 25, 100, 111, 112, 113, 114])(
    'uses the "many" form for %i',
    (n) => {
      expect(pick(n)).toBe(2)
    },
  )

  it('falls back to one|other for two choices', () => {
    expect(polishPluralRule(1, 2)).toBe(0)
    expect(polishPluralRule(2, 2)).toBe(1)
  })
})
