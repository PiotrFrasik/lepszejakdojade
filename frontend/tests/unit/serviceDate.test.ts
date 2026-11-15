import {
  isServiceDate,
  parseDate,
  parseDirection,
  serviceDateToDate,
  serviceMinutes,
  todayIn,
  zonedNow,
} from '@/utils/serviceDate'

describe('serviceDate utils', () => {
  it('validates real calendar dates only', () => {
    expect(isServiceDate('2026-11-16')).toBe(true)
    expect(isServiceDate('2028-02-29')).toBe(true)
    expect(isServiceDate('2026-02-29')).toBe(false)
    expect(isServiceDate('2026-13-01')).toBe(false)
    expect(isServiceDate('2026-1-1')).toBe(false)
    expect(isServiceDate('16-11-2026')).toBe(false)
    expect(isServiceDate(null)).toBe(false)
    expect(isServiceDate(20261116)).toBe(false)
  })

  it('computes the calendar date in the city time zone, not the UTC date', () => {
    const instant = new Date('2026-11-16T23:30:00Z')
    expect(todayIn('Europe/Warsaw', instant)).toBe('2026-11-17')
    expect(todayIn('UTC', instant)).toBe('2026-11-16')
    expect(todayIn('America/New_York', instant)).toBe('2026-11-16')
  })

  it('computes minutes since local midnight, with a 24 h clock', () => {
    expect(zonedNow('Europe/Warsaw', new Date('2026-11-16T23:30:00Z')).minutes).toBe(30)
    expect(zonedNow('Europe/Warsaw', new Date('2026-07-16T10:05:00Z')).minutes).toBe(12 * 60 + 5)
    expect(zonedNow('UTC', new Date('2026-11-16T00:00:00Z')).minutes).toBe(0)
  })

  it('does not throw for an invalid time zone name', () => {
    expect(() => zonedNow('Not/AZone')).not.toThrow()
  })

  it('keeps the calendar day when converting a service date for display', () => {
    expect(serviceDateToDate('2026-11-16').toISOString()).toBe('2026-11-16T12:00:00.000Z')
  })

  it('treats next_day departures as past 24:00 of the service day', () => {
    expect(serviceMinutes('05:12', false)).toBe(312)
    expect(serviceMinutes('00:15', true)).toBe(24 * 60 + 15)
    expect(serviceMinutes('23:59', false)).toBeLessThan(serviceMinutes('00:00', true))
  })

  it('parses direction: only "1" means 1', () => {
    expect(parseDirection('1')).toBe(1)
    expect(parseDirection(['1', '0'])).toBe(1)
    expect(parseDirection('0')).toBe(0)
    expect(parseDirection('2')).toBe(0)
    expect(parseDirection(undefined)).toBe(0)
  })

  it('parses date: invalid or missing gives null', () => {
    expect(parseDate('2026-11-16')).toBe('2026-11-16')
    expect(parseDate(['2026-11-16'])).toBe('2026-11-16')
    expect(parseDate('nope')).toBeNull()
    expect(parseDate(undefined)).toBeNull()
  })
})
