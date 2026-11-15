/**
 * Pure helpers of the journey planner: form values → API request, time zone handling for the
 * "depart at / arrive by" input, and itinerary → GeoJSON for the map. No user-facing text here.
 */
import type { Feature, FeatureCollection, LineString, Point } from 'geojson'

import type {
  Itinerary,
  JourneyLeg,
  JourneyPlaceInput,
  JourneyPreferences,
  JourneySearchRequest,
  StopId,
} from '@/types/api'

/** How an end point was chosen. */
export type PlaceSource = 'stop' | 'map' | 'location'

/** A "from" or "to" value of the form. `stopId` is set only for `source: 'stop'`. */
export interface PlaceValue {
  source: PlaceSource
  /** Stop name for stops; `null` for map points and "my location" (label comes from i18n). */
  name: string | null
  lat: number
  lon: number
  stopId?: StopId | null
}

/** Time selector: leave now, depart at a given time, or arrive by a given time. */
export type TimeChoice = 'now' | 'depart' | 'arrive'

export type PreferenceKey = 'fewer_transfers' | 'less_walking' | 'wheelchair'
export const PREFERENCE_KEYS: readonly PreferenceKey[] = [
  'fewer_transfers',
  'less_walking',
  'wheelchair',
]

export interface JourneyFormValues {
  from: PlaceValue | null
  to: PlaceValue | null
  timeChoice: TimeChoice
  /** Wall-clock `YYYY-MM-DDTHH:mm` in the city time zone (value of `<input type="datetime-local">`). */
  localTime: string
  preferences: Required<JourneyPreferences>
}

export type FormProblem = 'missing_from' | 'missing_to' | 'same_place' | 'invalid_time'

/** Converts a form place to the request shape (stop id when known, otherwise coordinates). */
export function placeToInput(place: PlaceValue): JourneyPlaceInput {
  if (place.source === 'stop' && place.stopId) {
    return place.name ? { stop_id: place.stopId, name: place.name } : { stop_id: place.stopId }
  }
  return { lat: place.lat, lon: place.lon }
}

/** Whether two places are the same stop or (practically) the same point. */
export function samePlace(a: PlaceValue, b: PlaceValue): boolean {
  if (a.stopId && b.stopId) return a.stopId === b.stopId
  return Math.abs(a.lat - b.lat) < 1e-5 && Math.abs(a.lon - b.lon) < 1e-5
}

const LOCAL_DATE_TIME = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/

/** Wall-clock parts of `date` in `timeZone` as a UTC timestamp (used to find the zone offset). */
function wallClockAsUtc(date: Date, timeZone: string): number {
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(date)
  const get = (type: Intl.DateTimeFormatPartTypes): number =>
    Number(parts.find((part) => part.type === type)?.value ?? 0)
  return Date.UTC(
    get('year'),
    get('month') - 1,
    get('day'),
    get('hour'),
    get('minute'),
    get('second'),
  )
}

/** Offset of `timeZone` from UTC at `date`, in minutes (e.g. `60` for CET). */
export function timeZoneOffsetMinutes(date: Date, timeZone: string): number {
  return Math.round((wallClockAsUtc(date, timeZone) - date.getTime()) / 60_000)
}

function pad(value: number): string {
  return String(value).padStart(2, '0')
}

/**
 * `YYYY-MM-DDTHH:mm` wall-clock time in `timeZone` → ISO 8601 with that zone's offset, e.g.
 * `2026-11-16T08:00` in `Europe/Warsaw` → `2026-11-16T08:00:00+01:00`. `null` if malformed.
 */
export function zonedLocalToIso(local: string, timeZone: string): string | null {
  const match = LOCAL_DATE_TIME.exec(local)
  if (!match) return null
  const [, y, mo, d, h, mi] = match.map(Number) as [number, number, number, number, number, number]
  const guess = Date.UTC(y, mo - 1, d, h, mi)
  if (Number.isNaN(guess)) return null
  let offset: number
  try {
    offset = timeZoneOffsetMinutes(new Date(guess), timeZone)
    const corrected = timeZoneOffsetMinutes(new Date(guess - offset * 60_000), timeZone)
    if (corrected !== offset) offset = corrected
  } catch {
    return null
  }
  const sign = offset < 0 ? '-' : '+'
  const abs = Math.abs(offset)
  return `${local}:00${sign}${pad(Math.floor(abs / 60))}:${pad(abs % 60)}`
}

/** Current wall-clock time in `timeZone` as `YYYY-MM-DDTHH:mm` (for prefilling the time input). */
export function zonedLocalNow(timeZone: string, now: Date = new Date()): string {
  const wall = new Date(wallClockAsUtc(now, timeZone))
  return (
    `${wall.getUTCFullYear()}-${pad(wall.getUTCMonth() + 1)}-${pad(wall.getUTCDate())}` +
    `T${pad(wall.getUTCHours())}:${pad(wall.getUTCMinutes())}`
  )
}

/** First problem that blocks the search, or `null` when the form can be sent. */
export function validateForm(values: JourneyFormValues): FormProblem | null {
  if (!values.from) return 'missing_from'
  if (!values.to) return 'missing_to'
  if (samePlace(values.from, values.to)) return 'same_place'
  if (values.timeChoice !== 'now' && !LOCAL_DATE_TIME.test(values.localTime)) return 'invalid_time'
  return null
}

/** Builds the request body; `null` when the form is not valid (see `validateForm`). */
export function buildJourneyRequest(
  values: JourneyFormValues,
  timeZone: string,
): JourneySearchRequest | null {
  if (validateForm(values) || !values.from || !values.to) return null
  const request: JourneySearchRequest = {
    from: placeToInput(values.from),
    to: placeToInput(values.to),
    time_mode: values.timeChoice === 'arrive' ? 'arrive' : 'depart',
    preferences: { ...values.preferences },
  }
  if (values.timeChoice !== 'now') {
    const time = zonedLocalToIso(values.localTime, timeZone)
    if (!time) return null
    request.time = time
  }
  return request
}

/** Transit (non-walking) legs of an itinerary. */
export function transitLegs(itinerary: Itinerary): JourneyLeg[] {
  return itinerary.legs.filter((leg) => leg.mode !== 'walk')
}

/** Fallback colour of a transit leg without a line colour. */
export const DEFAULT_TRANSIT_COLOUR = '#0b5cad'

/** Legs of an itinerary as GeoJSON lines with `mode` and `colour` properties for styling. */
export function legsToGeoJson(itinerary: Itinerary | null): FeatureCollection<LineString> {
  const features: Feature<LineString>[] = (itinerary?.legs ?? [])
    .map((leg): Feature<LineString> => {
      const coordinates = leg.geometry?.coordinates?.length
        ? leg.geometry.coordinates
        : [
            [leg.from.lon, leg.from.lat],
            [leg.to.lon, leg.to.lat],
          ]
      return {
        type: 'Feature',
        properties: {
          mode: leg.mode,
          colour: leg.line?.colour ?? DEFAULT_TRANSIT_COLOUR,
        },
        geometry: { type: 'LineString', coordinates },
      }
    })
    .filter((feature) => feature.geometry.coordinates.length >= 2)
  return { type: 'FeatureCollection', features }
}

/** From / to markers as GeoJSON points with a `role` property. */
export function endpointsToGeoJson(
  from: { lat: number; lon: number } | null,
  to: { lat: number; lon: number } | null,
): FeatureCollection<Point> {
  const features: Feature<Point>[] = []
  if (from) {
    features.push({
      type: 'Feature',
      properties: { role: 'from' },
      geometry: { type: 'Point', coordinates: [from.lon, from.lat] },
    })
  }
  if (to) {
    features.push({
      type: 'Feature',
      properties: { role: 'to' },
      geometry: { type: 'Point', coordinates: [to.lon, to.lat] },
    })
  }
  return { type: 'FeatureCollection', features }
}

/** `[[minLon, minLat], [maxLon, maxLat]]` of the given `[lon, lat]` points, or `null`. */
export function boundsOf(
  points: readonly (readonly [number, number])[],
): [[number, number], [number, number]] | null {
  if (points.length === 0) return null
  let [minLon, minLat] = points[0]!
  let [maxLon, maxLat] = points[0]!
  for (const [lon, lat] of points) {
    minLon = Math.min(minLon, lon)
    minLat = Math.min(minLat, lat)
    maxLon = Math.max(maxLon, lon)
    maxLat = Math.max(maxLat, lat)
  }
  return [
    [minLon, minLat],
    [maxLon, maxLat],
  ]
}
