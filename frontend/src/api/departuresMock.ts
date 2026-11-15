/**
 * Development-only stand-ins for `GET /api/v1/cities/{city}/stops/{stop_id}/departures/` and
 * `GET /api/v1/cities/{city}/stops/{stop_id}/`, used only in the Vite dev server
 * (`import.meta.env.DEV`) started with `VITE_DEPARTURES_MOCK=true` (before the backend endpoints
 * exist). Production builds never use or bundle them, whatever the variable says. They follow the
 * contract shapes with fictional data; names are placeholders, not translated UI text.
 *
 * Keywords in the stop id pick the answer (both endpoints): `missing` → 404, `fail` → 500,
 * `offline` → network error. Departures only: `empty` → no departures, `static` →
 * `realtime_available: false`. Stop overview only: `nolines` → no lines, `brokenlines` → 500
 * (the departures board still loads). Any other id gives a mix of late, early, on-time,
 * cancelled and timetable-only departures; delays change on every call so the auto-refresh is
 * visible.
 */
import { ApiError } from '@/api/client'
import type {
  LineSummary,
  StopDeparture,
  StopDepartures,
  StopId,
  StopLine,
  StopOverview,
} from '@/types/api'

const STOP_NAME = 'Northgate Sq (mock)'

const LINES: LineSummary[] = [
  {
    id: 'mock:52',
    short_name: '52',
    vehicle_type: 'tram',
    group: 'tram_day',
    colour: '#1f6feb',
    text_colour: '#ffffff',
  },
  {
    id: 'mock:179',
    short_name: '179',
    vehicle_type: 'bus',
    group: 'bus_day',
    colour: '#0b7a3e',
    text_colour: '#ffffff',
  },
  {
    id: 'mock:N1',
    short_name: 'N1',
    vehicle_type: 'bus',
    group: 'bus_night',
    colour: '#222222',
    text_colour: '#ffd166',
  },
]

const HEADSIGNS = ['Southfield', 'Airport', 'Old Town', 'Northgate Depot']

let calls = 0

function wait(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(resolve, ms)
    signal?.addEventListener('abort', () => {
      clearTimeout(timer)
      reject(new DOMException('Aborted', 'AbortError'))
    })
  })
}

/** ISO 8601 with a `+01:00`-style offset of the browser (the API uses the city offset). */
function iso(ms: number): string {
  const date = new Date(ms)
  const offset = -date.getTimezoneOffset()
  const local = new Date(ms + offset * 60_000).toISOString().slice(0, 19)
  const sign = offset >= 0 ? '+' : '-'
  const abs = Math.abs(offset)
  const hh = String(Math.floor(abs / 60)).padStart(2, '0')
  const mm = String(abs % 60).padStart(2, '0')
  return `${local}${sign}${hh}:${mm}`
}

export async function mockGetStopDepartures(
  _city: string,
  stopId: StopId,
  params: { limit?: number } = {},
  signal?: AbortSignal,
): Promise<StopDepartures> {
  await wait(500, signal)
  calls += 1
  const id = stopId.toLowerCase()
  if (id.includes('missing')) throw new ApiError(404, 'not_found', 'Not found.')
  if (id.includes('fail')) throw new ApiError(500, 'server_error', 'Server error.')
  if (id.includes('offline')) throw new ApiError(0, 'network_error', 'Failed to fetch')

  const now = Date.now()
  const minute = Math.floor(now / 60_000) * 60_000
  const realtime = !id.includes('static')
  const limit = params.limit ?? 15
  const departures: StopDeparture[] = []

  if (!id.includes('empty')) {
    // Offsets in minutes from now and live delays in seconds (`null` = no live data).
    const plan: [number, number | null | 'canceled'][] = [
      [0, 30],
      [2, 180 + (calls % 3) * 60],
      [5, 0],
      [7, -90],
      [9, 'canceled'],
      [12, null],
      [16, 45],
      [21, 720],
      [28, 0],
      [34, null],
      [41, 120],
      [55, 0],
      [70, null],
      [95, 60],
      [130, null],
    ]
    plan.forEach(([offset, delay], i) => {
      const scheduled = minute + offset * 60_000
      const line = LINES[i % LINES.length]!
      const live = realtime && typeof delay === 'number'
      const canceled = realtime && delay === 'canceled'
      departures.push({
        line,
        trip_id: `mock:trip_${i}`,
        headsign: HEADSIGNS[i % HEADSIGNS.length]!,
        platform_id: `mock:platform_${i % 3}`,
        platform_code: i % 3 === 2 ? null : `0${(i % 3) + 1}`,
        scheduled: iso(scheduled),
        expected: live ? iso(scheduled + (delay as number) * 1000) : null,
        delay_seconds: live ? (delay as number) : null,
        status: live ? 'live' : canceled ? 'canceled' : 'scheduled',
      })
    })
    const effective = (d: StopDeparture) => Date.parse(d.expected ?? d.scheduled)
    departures.sort(
      (a, b) => effective(a) - effective(b) || Date.parse(a.scheduled) - Date.parse(b.scheduled),
    )
  }

  return {
    stop: {
      id: stopId,
      name: STOP_NAME,
      stop_ids: [stopId, 'mock:platform_1', 'mock:platform_2'],
    },
    generated_at: iso(now),
    realtime_available: realtime,
    departures: departures.slice(0, limit),
  }
}

export async function mockGetStopOverview(
  _city: string,
  stopId: StopId,
  signal?: AbortSignal,
): Promise<StopOverview> {
  await wait(700, signal)
  const id = stopId.toLowerCase()
  if (id.includes('missing')) throw new ApiError(404, 'not_found', 'Not found.')
  if (id.includes('fail')) throw new ApiError(500, 'server_error', 'Server error.')
  if (id.includes('offline')) throw new ApiError(0, 'network_error', 'Failed to fetch')
  if (id.includes('brokenlines')) throw new ApiError(500, 'server_error', 'Server error.')

  const lines: StopLine[] = id.includes('nolines')
    ? []
    : LINES.map((line, i) => ({
        line,
        directions:
          i === 2
            ? [{ direction: 0, headsign: HEADSIGNS[3]!, platform_id: 'mock:platform_2' }]
            : [
                { direction: 0, headsign: HEADSIGNS[i]!, platform_id: 'mock:platform_0' },
                { direction: 1, headsign: HEADSIGNS[i + 2]!, platform_id: 'mock:platform_1' },
              ],
      }))
  return {
    stop: {
      id: stopId,
      name: STOP_NAME,
      lat: 50.06,
      lon: 19.94,
      vehicle_types: [...new Set(lines.map((entry) => entry.line.vehicle_type))],
      stop_ids: [stopId, 'mock:platform_1', 'mock:platform_2'],
    },
    lines,
  }
}
