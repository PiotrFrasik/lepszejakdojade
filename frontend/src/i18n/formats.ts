/**
 * Named date/time and number formats registered in vue-i18n (`datetimeFormats`, `numberFormats`).
 *
 * The time zone is deliberately not part of these definitions: it depends on the selected city
 * and is passed at call time (see `src/i18n/format.ts` and `useFormat()`), so the browser's own
 * time zone is never used for transit times.
 */
import type { IntlDateTimeFormat, IntlNumberFormat } from 'vue-i18n'

const dateTimeFormat = {
  /** Clock time, always 24-hour `HH:mm` (e.g. 08:14). */
  time: { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' },
  /** Calendar date with a short month name (e.g. "14 lis 2026" / "Nov 14, 2026"). */
  date: { day: 'numeric', month: 'short', year: 'numeric' },
  /** Long date with weekday, e.g. for the timetable date picker heading. */
  dateLong: { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' },
  /** Date and 24-hour time. */
  dateTime: {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  },
} satisfies IntlDateTimeFormat

const numberFormat = {
  /** Ticket prices; all supported cities use the Polish złoty. */
  price: {
    style: 'currency',
    currency: 'PLN',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  },
  /** Whole numbers (metres, counts). */
  integer: { maximumFractionDigits: 0 },
  /** Kilometres with at most one decimal place. */
  kilometres: { minimumFractionDigits: 0, maximumFractionDigits: 1 },
} satisfies IntlNumberFormat

export type DateTimeFormatKey = keyof typeof dateTimeFormat

export const datetimeFormats = { pl: dateTimeFormat, en: dateTimeFormat }
export const numberFormats = { pl: numberFormat, en: numberFormat }
