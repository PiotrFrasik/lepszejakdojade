/**
 * Pure helpers for the stop departures board: how one departure's time should be shown.
 * Nothing here is user-facing text; components turn the results into i18n strings.
 */
import type { StopDeparture } from '@/types/api'

/** Departures closer than this many minutes also show a countdown ("in 5 min"). */
export const COUNTDOWN_MAX_MINUTES = 30

/** A live delay smaller than this (in either direction) counts as "on time". */
export const ON_TIME_THRESHOLD_SECONDS = 60

export type DepartureTiming =
  /** No live data: the timetable time only. */
  | { kind: 'scheduled' }
  | { kind: 'canceled' }
  | { kind: 'on_time' }
  /** `minutes` ≥ 1, rounded. */
  | { kind: 'late'; minutes: number }
  /** `minutes` ≥ 1, rounded. */
  | { kind: 'early'; minutes: number }

/**
 * Classifies a departure. With `realtimeAvailable === false` nothing is shown as live, even if a
 * malformed response carried live fields.
 */
export function departureTiming(
  departure: StopDeparture,
  realtimeAvailable: boolean,
): DepartureTiming {
  if (!realtimeAvailable) return { kind: 'scheduled' }
  if (departure.status === 'canceled') return { kind: 'canceled' }
  const delay = departure.delay_seconds
  if (departure.status !== 'live' || !departure.expected || typeof delay !== 'number') {
    return { kind: 'scheduled' }
  }
  if (Math.abs(delay) < ON_TIME_THRESHOLD_SECONDS) return { kind: 'on_time' }
  const minutes = Math.max(1, Math.round(Math.abs(delay) / 60))
  return delay > 0 ? { kind: 'late', minutes } : { kind: 'early', minutes }
}

/** The time the vehicle is expected to leave: expected when shown as live, otherwise scheduled. */
export function effectiveTime(departure: StopDeparture, realtimeAvailable: boolean): string {
  const timing = departureTiming(departure, realtimeAvailable)
  return (timing.kind === 'late' || timing.kind === 'early' || timing.kind === 'on_time') &&
    departure.expected
    ? departure.expected
    : departure.scheduled
}

/** Departures whose effective time is further in the past than this are dropped from the board. */
export const DEPARTED_GRACE_MS = 60_000

/**
 * Whether the departure has left: its effective time is more than `DEPARTED_GRACE_MS` before
 * `nowMs` (same window as the API). Lets a board that cannot refresh drop old rows.
 */
export function hasDeparted(
  departure: StopDeparture,
  realtimeAvailable: boolean,
  nowMs: number,
): boolean {
  const at = Date.parse(effectiveTime(departure, realtimeAvailable))
  if (Number.isNaN(at) || !Number.isFinite(nowMs)) return false
  return at < nowMs - DEPARTED_GRACE_MS
}

/**
 * Whole minutes until the departure (`0` = now, including slightly past departures still on
 * the board), or `null` when no countdown applies: cancelled, further than
 * `COUNTDOWN_MAX_MINUTES`, or an unparsable time.
 */
export function minutesUntil(
  departure: StopDeparture,
  realtimeAvailable: boolean,
  nowMs: number,
): number | null {
  if (departureTiming(departure, realtimeAvailable).kind === 'canceled') return null
  const at = Date.parse(effectiveTime(departure, realtimeAvailable))
  if (Number.isNaN(at) || !Number.isFinite(nowMs)) return null
  const diff = at - nowMs
  if (diff < 60_000) return 0
  const minutes = Math.floor(diff / 60_000)
  return minutes <= COUNTDOWN_MAX_MINUTES ? minutes : null
}
