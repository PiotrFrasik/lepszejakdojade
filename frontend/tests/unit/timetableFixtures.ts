import type {
  DepartureMarker,
  Line,
  LineGroup,
  LineRoute,
  LineSummary,
  StopTimetable,
  TimetableDeparture,
  Trip,
} from '@/types/api'

/** Fictional timetable data (no real-city names). */

export const GROUPS: LineGroup[] = [
  { id: 'day', name: 'Day lines', colour: '#112233' },
  { id: 'night', name: 'Night lines', colour: '#445566' },
]

export function summary(over: Partial<LineSummary> = {}): LineSummary {
  return {
    id: 'feed_a:7',
    short_name: '7',
    vehicle_type: 'tram',
    group: 'day',
    colour: '#1f6feb',
    text_colour: '#ffffff',
    ...over,
  }
}

export function line(over: Partial<Line> = {}): Line {
  return { ...summary(), long_name: 'Northgate - Southfield', notice: null, ...over }
}

export function dep(
  time: string,
  over: Partial<TimetableDeparture> & { markers?: DepartureMarker[] } = {},
): TimetableDeparture {
  const [h, m] = time.split(':').map(Number) as [number, number]
  return {
    minute: m,
    time: `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`,
    next_day: false,
    trip_id: `feed_a:trip_${time}${over.next_day ? 'n' : ''}`,
    headsign: 'Southfield',
    markers: [],
    variant: 'v1',
    ...over,
  }
}

function hoursOf(deps: TimetableDeparture[]) {
  const map = new Map<number, TimetableDeparture[]>()
  for (const d of deps) {
    const hour = Number(d.time.slice(0, 2))
    map.set(hour, [...(map.get(hour) ?? []), d])
  }
  return [...map.entries()].map(([hour, departures]) => ({ hour, departures }))
}

export function timetable(
  over: Partial<StopTimetable> & {
    weekday?: TimetableDeparture[]
    saturday?: TimetableDeparture[]
    sunday?: TimetableDeparture[]
  } = {},
): StopTimetable {
  const { weekday = [], saturday = [], sunday = [], ...rest } = over
  return {
    line: summary(),
    stop: { stop_id: 'feed_a:s2', name: 'Market Square', code: '02' },
    direction: 0,
    headsign: 'Southfield',
    date: '2026-11-16',
    day_type: 'weekday',
    previous_stop: { stop_id: 'feed_a:s1', name: 'Old Mill' },
    next_stop: { stop_id: 'feed_a:s3', name: 'River Bridge' },
    columns: [
      { day_type: 'weekday', date: '2026-11-16', hours: hoursOf(weekday) },
      { day_type: 'saturday', date: '2026-11-21', hours: hoursOf(saturday) },
      { day_type: 'sunday', date: '2026-11-22', hours: hoursOf(sunday) },
    ],
    variants: [],
    ...rest,
  }
}

export function route(over: Partial<LineRoute> = {}): LineRoute {
  const transfer = summary({ id: 'feed_b:12', short_name: '12', vehicle_type: 'bus' })
  return {
    line: summary(),
    direction: 0,
    date: '2026-11-16',
    directions: [
      { direction: 0, headsign: 'Southfield' },
      { direction: 1, headsign: 'Northgate' },
    ],
    stops: [
      {
        stop_id: 'feed_a:s1',
        name: 'Old Mill',
        code: '01',
        lat: 1,
        lon: 2,
        wheelchair_boarding: true,
        variant_only: false,
        transfers: [transfer],
      },
      {
        stop_id: 'feed_a:s_depot',
        name: 'Depot Gate',
        code: null,
        lat: 1.1,
        lon: 2.1,
        wheelchair_boarding: null,
        variant_only: true,
        transfers: [],
      },
      {
        stop_id: 'feed_a:s2',
        name: 'Market Square',
        code: null,
        lat: 1.2,
        lon: 2.2,
        wheelchair_boarding: false,
        variant_only: false,
        transfers: [],
      },
    ],
    variants: [
      {
        id: 'v1',
        kind: 'main',
        headsign: 'Southfield',
        trip_count: 100,
        stop_ids: ['feed_a:s1', 'feed_a:s2'],
      },
      {
        id: 'v2',
        kind: 'depot',
        headsign: 'Depot',
        trip_count: 3,
        stop_ids: ['feed_a:s1', 'feed_a:s_depot'],
      },
    ],
    shape: {
      type: 'LineString',
      coordinates: [
        [2, 1],
        [2.2, 1.2],
      ],
    },
    ...over,
  }
}

export function trip(over: Partial<Trip> = {}): Trip {
  return {
    trip_id: 'feed_a:trip_1',
    date: '2026-11-16',
    line: summary(),
    direction: 0,
    headsign: 'Southfield',
    wheelchair_accessible: true,
    stops: [
      {
        stop_id: 'feed_a:s1',
        name: 'Old Mill',
        arrival: '2026-11-16T05:10:00+01:00',
        departure: '2026-11-16T05:10:00+01:00',
      },
      {
        stop_id: 'feed_a:s2',
        name: 'Market Square',
        arrival: '2026-11-16T05:12:00+01:00',
        departure: '2026-11-16T05:12:00+01:00',
      },
      { stop_id: 'feed_a:s3', name: 'River Bridge', arrival: null, departure: null },
    ],
    ...over,
  }
}
