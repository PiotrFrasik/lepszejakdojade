/** Types mirroring `docs/api.md`. */

/** Error body returned by every endpoint on failure. */
export interface ApiErrorBody {
  error: {
    code: string
    message: string
  }
}

export type HealthCheckState = 'ok' | 'error'

/** `GET /api/v1/health/` (200 when all checks pass, 503 otherwise; same body). */
export interface HealthResponse {
  status: HealthCheckState
  checks: Record<string, HealthCheckState>
  version: string
}

/** City slug used in API paths: `/api/v1/cities/{city}/…`. Cities come from backend config. */
export type CityId = string

/** Geographic point as returned by the API. */
export interface LatLon {
  lat: number
  lon: number
}

/** Initial map view of a city. */
export interface CityMapConfig {
  center: LatLon
  zoom: number
}

/** Item of `GET /api/v1/cities/` (plain array, ordered by id). `name` is in the request language. */
export interface City {
  id: CityId
  name: string
  map: CityMapConfig
}

/** Vehicle types; `CityDetail.vehicle_types` lists them in display order. */
export type VehicleType = 'tram' | 'bus' | 'metro' | 'rail'

/** Line group used to group and colour line tiles. `name` is translated. */
export interface LineGroup {
  id: string
  name: string
  colour: string
}

/** Which live data the city provides. */
export interface CityRealtime {
  departures: boolean
  vehicles: boolean
}

/** `GET /api/v1/cities/{city}/`. Unknown city → `404` with code `not_found`. */
export interface CityDetail extends City {
  timezone: string
  vehicle_types: VehicleType[]
  line_groups: LineGroup[]
  realtime: CityRealtime
}

// ---------------------------------------------------------------------------
// Timetable (#10)
// ---------------------------------------------------------------------------

/** `{feed_id}:{gtfs_id}`; opaque, URL-encode in paths. */
export type LineId = string
/** `{feed_id}:{gtfs_id}`; opaque, URL-encode in paths. */
export type StopId = string
/** `{feed_id}:{gtfs_trip_id}`; opaque, URL-encode in paths. */
export type TripId = string

/** Service date `YYYY-MM-DD` in the city time zone. */
export type ServiceDate = string

/** Direction of a line (GTFS `direction_id`). */
export type DirectionId = 0 | 1

/** `weekday`, `saturday`, `sunday` (Sundays and public holidays). */
export type DayType = 'weekday' | 'saturday' | 'sunday'

/** Shared "line summary" object. */
export interface LineSummary {
  id: LineId
  short_name: string
  vehicle_type: VehicleType
  /** One of `CityDetail.line_groups[].id`. */
  group: string
  /** `#rrggbb`. */
  colour: string
  /** `#rrggbb`, readable on `colour`. */
  text_colour: string
}

/** Detour or timetable change warning. Always `null` until live alerts exist (#20). */
export interface LineNotice {
  kind: 'detour' | 'timetable_change'
  text: string
}

/** Item of `GET /api/v1/cities/{city}/lines/` (plain array, sorted by group, then naturally). */
export interface Line extends LineSummary {
  long_name: string
  notice: LineNotice | null
}

export interface LineDirection {
  direction: DirectionId
  headsign: string
}

export interface RouteStop {
  stop_id: StopId
  name: string
  code: string | null
  lat: number
  lon: number
  wheelchair_boarding: boolean | null
  variant_only: boolean
  transfers: LineSummary[]
}

export type VariantKind = 'main' | 'short_turn' | 'depot' | 'other'

export interface RouteVariant {
  /** Only meaningful within one response. */
  id: string
  kind: VariantKind
  headsign: string
  trip_count: number
  stop_ids: StopId[]
}

/** GeoJSON LineString, coordinates `[lon, lat]`. */
export interface GeoLineString {
  type: 'LineString'
  coordinates: [number, number][]
}

/** `GET /api/v1/cities/{city}/lines/{line_id}/route/?direction=&date=`. */
export interface LineRoute {
  line: LineSummary
  direction: DirectionId
  /** The date the diagram was built for (may be later than the requested one). */
  date: ServiceDate
  directions: LineDirection[]
  stops: RouteStop[]
  variants: RouteVariant[]
  shape: GeoLineString
}

export type DepartureMarker = 'low_floor' | 'short_turn' | 'variant'

export interface TimetableDeparture {
  minute: number
  /** `HH:MM` local. */
  time: string
  next_day: boolean
  trip_id: TripId
  headsign: string
  markers: DepartureMarker[]
  variant: string
}

export interface TimetableHour {
  hour: number
  departures: TimetableDeparture[]
}

export interface TimetableColumn {
  day_type: DayType
  date: ServiceDate
  hours: TimetableHour[]
}

export interface StopRef {
  stop_id: StopId
  name: string
}

export interface TimetableVariant {
  id: string
  kind: VariantKind
  headsign: string
}

/** `GET /api/v1/cities/{city}/lines/{line_id}/stops/{stop_id}/timetable/?direction=&date=`. */
export interface StopTimetable {
  line: LineSummary
  stop: StopRef & { code: string | null }
  direction: DirectionId
  headsign: string
  date: ServiceDate
  /** Day type of `date`; tells which column to highlight. */
  day_type: DayType
  previous_stop: StopRef | null
  next_stop: StopRef | null
  /** Always three, in the order `weekday`, `saturday`, `sunday`. */
  columns: TimetableColumn[]
  /** Non-main variants used in this timetable (for the legend). */
  variants: TimetableVariant[]
}

export interface TripStop {
  stop_id: StopId
  name: string
  /** ISO 8601 with offset, or `null`. */
  arrival: string | null
  /** ISO 8601 with offset, or `null`. */
  departure: string | null
}

/** `GET /api/v1/cities/{city}/trips/{trip_id}/?date=`. `404` if it does not run on `date`. */
export interface Trip {
  trip_id: TripId
  date: ServiceDate
  line: LineSummary
  direction: DirectionId
  headsign: string
  wheelchair_accessible: boolean | null
  stops: TripStop[]
}
