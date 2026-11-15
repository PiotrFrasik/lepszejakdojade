import type { StopLine, StopOverview } from '@/types/api'

import { summary } from './timetableFixtures'

/** Fictional stop overview data. */

export function stopLine(over: Partial<StopLine> = {}): StopLine {
  return {
    line: summary({ id: 'feed_a:7', short_name: '7', vehicle_type: 'tram' }),
    directions: [
      { direction: 0, headsign: 'Southfield', platform_id: 'feed_a:stop_1' },
      { direction: 1, headsign: 'Eastbrook', platform_id: 'feed_b:stop 2' },
    ],
    ...over,
  }
}

export function stopOverview(over: Partial<StopOverview> = {}): StopOverview {
  return {
    stop: {
      id: 'feed_a:stop_1',
      name: 'Northgate',
      lat: 50.1,
      lon: 19.9,
      vehicle_types: ['tram'],
      stop_ids: ['feed_a:stop_1', 'feed_b:stop 2'],
    },
    lines: [stopLine()],
    ...over,
  }
}
