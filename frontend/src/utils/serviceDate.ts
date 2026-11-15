/**
 * Helpers for service dates (`YYYY-MM-DD`) and clock times in the city's time zone.
 * Nothing here is user-facing text; formatting for display goes through `useFormat()`.
 */
import type { DirectionId, ServiceDate } from '@/types/api'

const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})$/

/** Whether `value` is a real calendar date in `YYYY-MM-DD` form. */
export function isServiceDate(value: unknown): value is ServiceDate {
  if (typeof value !== 'string') return false
  const match = ISO_DATE.exec(value)
  if (!match) return false
  const [, y, m, d] = match.map(Number) as [number, number, number, number]
  const date = new Date(Date.UTC(y, m - 1, d))
  return date.getUTCFullYear() === y && date.getUTCMonth() === m - 1 && date.getUTCDate() === d
}

interface ZonedParts {
  date: ServiceDate
  minutes: number
}

/** Calendar date and minutes since midnight of `now` in `timeZone`. */
export function zonedNow(timeZone: string, now: Date = new Date()): ZonedParts {
  let parts: Intl.DateTimeFormatPart[]
  try {
    parts = new Intl.DateTimeFormat('en-GB', {
      timeZone,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hourCycle: 'h23',
    }).formatToParts(now)
  } catch {
    parts = new Intl.DateTimeFormat('en-GB', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hourCycle: 'h23',
    }).formatToParts(now)
  }
  const get = (type: Intl.DateTimeFormatPartTypes): string =>
    parts.find((part) => part.type === type)?.value ?? '00'
  return {
    date: `${get('year')}-${get('month')}-${get('day')}`,
    minutes: Number(get('hour')) * 60 + Number(get('minute')),
  }
}

/** Today's date in `timeZone`. */
export function todayIn(timeZone: string, now: Date = new Date()): ServiceDate {
  return zonedNow(timeZone, now).date
}

/**
 * A service date as a `Date` at noon UTC, for display with `useFormat().date*()`: noon keeps the
 * calendar day the same in every European time zone.
 */
export function serviceDateToDate(date: ServiceDate): Date {
  return new Date(`${date}T12:00:00Z`)
}

/** Minutes since midnight of the service day for an `HH:MM` time (`next_day` adds 24 h). */
export function serviceMinutes(time: string, nextDay: boolean): number {
  const [h = 0, m = 0] = time.split(':').map(Number)
  return (nextDay ? 24 * 60 : 0) + h * 60 + m
}

/** Parses the `direction` query value; anything other than `1` means `0`. */
export function parseDirection(value: unknown): DirectionId {
  const raw = Array.isArray(value) ? value[0] : value
  return raw === '1' || raw === 1 ? 1 : 0
}

/** Parses the `date` query value; invalid or missing gives `null` (API default: today). */
export function parseDate(value: unknown): ServiceDate | null {
  const raw = Array.isArray(value) ? value[0] : value
  return isServiceDate(raw) ? raw : null
}
