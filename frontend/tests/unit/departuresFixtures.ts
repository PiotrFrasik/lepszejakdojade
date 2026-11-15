import type { StopDeparture, StopDepartures } from '@/types/api'

import { summary } from './timetableFixtures'

/** Fictional departures data. All times use a fixed +01:00 offset (winter). */
export const NOW = Date.parse('2026-11-16T10:00:00+01:00')
export const GENERATED_AT = '2026-11-16T10:00:00+01:00'

/** ISO time `minutes` (+ `seconds`) after NOW, with a +01:00 offset. */
export function at(minutes: number, seconds = 0): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  const local = new Date(NOW + minutes * 60_000 + seconds * 1000 + 3_600_000)
  return (
    `${local.getUTCFullYear()}-${pad(local.getUTCMonth() + 1)}-${pad(local.getUTCDate())}` +
    `T${pad(local.getUTCHours())}:${pad(local.getUTCMinutes())}:${pad(local.getUTCSeconds())}+01:00`
  )
}

export function departure(over: Partial<StopDeparture> = {}): StopDeparture {
  return {
    line: summary({ short_name: '7' }),
    trip_id: 'feed_a:trip_1',
    headsign: 'Southfield',
    platform_id: 'feed_a:stop_1',
    platform_code: null,
    scheduled: at(10),
    expected: null,
    delay_seconds: null,
    status: 'scheduled',
    ...over,
  }
}

export function liveDeparture(delaySeconds: number, over: Partial<StopDeparture> = {}) {
  const scheduled = over.scheduled ?? at(10)
  return departure({
    scheduled,
    expected: new Date(Date.parse(scheduled) + delaySeconds * 1000).toISOString(),
    delay_seconds: delaySeconds,
    status: 'live',
    ...over,
  })
}

export function board(over: Partial<StopDepartures> = {}): StopDepartures {
  return {
    stop: { id: 'feed_a:stop_1', name: 'Northgate', stop_ids: ['feed_a:stop_1', 'feed_b:stop_2'] },
    generated_at: GENERATED_AT,
    realtime_available: true,
    departures: [departure()],
    ...over,
  }
}
