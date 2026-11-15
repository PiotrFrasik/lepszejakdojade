/**
 * Locale-aware formatting of times, dates, prices, durations and distances.
 *
 * Every function uses the current vue-i18n locale (so templates re-render when the language
 * changes) and the named formats from `./formats`. Dates and times are always shown in the
 * given IANA time zone (the selected city's), never in the browser's. In components prefer
 * `useFormat()`, which fills in the city's time zone.
 */
import { i18n } from './index'
import type { DateTimeFormatKey } from './formats'

/**
 * Deliberate fallback, used only until the selected city's details (`CityDetail.timezone`)
 * are loaded or when that zone is unknown to the browser. The real time zone always comes
 * from the city config returned by the API.
 */
export const DEFAULT_TIME_ZONE = 'Europe/Warsaw'

/** A point in time: `Date`, epoch milliseconds or an ISO 8601 string (as returned by the API). */
export type DateInput = Date | number | string

function toDate(value: DateInput): Date | null {
  const date = value instanceof Date ? value : new Date(value)
  return Number.isNaN(date.getTime()) ? null : date
}

/** Falls back to the default zone when the given one is unknown to the browser's Intl. */
function safeTimeZone(timeZone: string | null | undefined): string {
  if (!timeZone) return DEFAULT_TIME_ZONE
  try {
    new Intl.DateTimeFormat('en', { timeZone })
    return timeZone
  } catch {
    return DEFAULT_TIME_ZONE
  }
}

function formatDateTimeKey(
  key: DateTimeFormatKey,
  value: DateInput,
  timeZone: string | null | undefined,
): string {
  const date = toDate(value)
  if (!date) return ''
  return i18n.global.d(date, { key, timeZone: safeTimeZone(timeZone) })
}

/** 24-hour clock time, e.g. `08:14`. Returns `''` for an invalid date. */
export function formatTime(value: DateInput, timeZone?: string | null): string {
  return formatDateTimeKey('time', value, timeZone)
}

/** 24-hour clock time with seconds, e.g. `21:04:10`. Returns `''` for an invalid date. */
export function formatTimeSeconds(value: DateInput, timeZone?: string | null): string {
  return formatDateTimeKey('timeSeconds', value, timeZone)
}

/** Calendar date, e.g. `14 lis 2026` / `Nov 14, 2026`. Returns `''` for an invalid date. */
export function formatDate(value: DateInput, timeZone?: string | null): string {
  return formatDateTimeKey('date', value, timeZone)
}

/** Long date with weekday, e.g. `sobota, 14 listopada 2026`. Returns `''` for an invalid date. */
export function formatDateLong(value: DateInput, timeZone?: string | null): string {
  return formatDateTimeKey('dateLong', value, timeZone)
}

/** Date and 24-hour time. Returns `''` for an invalid date. */
export function formatDateTime(value: DateInput, timeZone?: string | null): string {
  return formatDateTimeKey('dateTime', value, timeZone)
}

/** Price in Polish złoty, e.g. `4,60 zł` / `PLN 4.60`. Returns `''` for a non-finite amount. */
export function formatPrice(amount: number): string {
  if (!Number.isFinite(amount)) return ''
  return i18n.global.n(amount, 'price')
}

/** Decimal string as sent by the API for money (`"6.00"`, `"12.5"`, `"-1.00"`). */
const DECIMAL_STRING = /^-?\d+(\.\d+)?$/

/**
 * Price from an API decimal string and an ISO 4217 currency code, e.g. `"6.00"` + `PLN` →
 * `6,00 zł` / `PLN 6.00`. The string is passed to `Intl.NumberFormat` as is (ES2023 formats
 * decimal strings exactly), so no float arithmetic is ever done on the amount.
 * Returns `''` for a malformed amount or an unknown currency code.
 */
export function formatMoney(amount: string, currency: string): string {
  const value = typeof amount === 'string' ? amount.trim() : ''
  if (!DECIMAL_STRING.test(value)) return ''
  try {
    // Always 2 decimal places: all supported cities use PLN (contract: two-place decimal strings).
    const formatter = new Intl.NumberFormat(i18n.global.locale.value, {
      style: 'currency',
      currency,
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })
    // The app's TypeScript lib is ES2022, whose typings only allow numbers here. `format` is a
    // bound getter, so calling it detached is fine.
    return (formatter.format as unknown as (value: string) => string)(value)
  } catch {
    return ''
  }
}

/**
 * Duration from seconds, rounded to whole minutes: `45 min`, `2 h`, `1 h 5 min`; under half a
 * minute (but more than zero) gives `< 1 min`. Unit words come from the locale files.
 * Returns `''` for a negative or non-finite value.
 */
export function formatDuration(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return ''
  const { t, n } = i18n.global
  const totalMinutes = Math.round(seconds / 60)
  if (totalMinutes === 0) {
    return seconds > 0
      ? t('units.duration.lessThanMinute')
      : t('units.duration.minutes', { minutes: n(0, 'integer') })
  }
  const hours = Math.floor(totalMinutes / 60)
  const minutes = totalMinutes % 60
  if (hours === 0) return t('units.duration.minutes', { minutes: n(minutes, 'integer') })
  if (minutes === 0) return t('units.duration.hours', { hours: n(hours, 'integer') })
  return t('units.duration.hoursMinutes', {
    hours: n(hours, 'integer'),
    minutes: n(minutes, 'integer'),
  })
}

/**
 * Distance from metres: below 1 km in whole metres (`350 m`), from 1 km in kilometres with at
 * most one decimal (`1,2 km` / `1.2 km`, `2 km`). Returns `''` for a negative or non-finite value.
 */
export function formatDistance(metres: number): string {
  if (!Number.isFinite(metres) || metres < 0) return ''
  const { t, n } = i18n.global
  const rounded = Math.round(metres)
  if (rounded < 1000) return t('units.distance.metres', { value: n(rounded, 'integer') })
  return t('units.distance.kilometres', { value: n(rounded / 1000, 'kilometres') })
}
