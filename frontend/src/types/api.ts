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

// ---------------------------------------------------------------------------
// Stop search (#59) and journeys (#12)
// ---------------------------------------------------------------------------

/** Item of `GET /api/v1/cities/{city}/stops/?q=` (platforms grouped by name, at most 20). */
export interface StopSearchResult {
  /** Representative platform (closest to the group centroid). */
  stop_id: StopId
  name: string
  /** Group centroid. */
  lat: number
  lon: number
  vehicle_types: VehicleType[]
  /** All platforms of the group. */
  stop_ids: StopId[]
}

/** Journey end point: exactly one of a stop id or a coordinate pair. `name` is echoed back. */
export type JourneyPlaceInput =
  { stop_id: StopId; name?: string } | { lat: number; lon: number; name?: string }

export type JourneyTimeMode = 'depart' | 'arrive'

export interface JourneyPreferences {
  fewer_transfers?: boolean
  less_walking?: boolean
  wheelchair?: boolean
}

/** Body of `POST /api/v1/cities/{city}/journeys/search/`. */
export interface JourneySearchRequest {
  from: JourneyPlaceInput
  to: JourneyPlaceInput
  /** ISO 8601 with offset; omitted = now. */
  time?: string
  time_mode?: JourneyTimeMode
  preferences?: JourneyPreferences
}

export interface JourneyPlace {
  name: string | null
  lat: number
  lon: number
}

export interface LegPlace extends JourneyPlace {
  stop_id: StopId | null
}

export type LegMode = 'walk' | VehicleType

export interface LegStop {
  name: string
  stop_id: StopId
}

export interface JourneyLeg {
  mode: LegMode
  /** ISO 8601 with offset. */
  start: string
  end: string
  /** Seconds. */
  duration: number
  /** Metres. */
  distance: number
  from: LegPlace
  to: LegPlace
  /** `null` for walking legs. */
  line: LineSummary | null
  headsign: string | null
  trip_id: TripId | null
  intermediate_stops: LegStop[]
  geometry: GeoLineString
}

export interface Itinerary {
  id: string
  start: string
  end: string
  /** Seconds. */
  duration: number
  transfers: number
  /** Metres. */
  walk_distance: number
  /** Seconds. */
  walk_duration: number
  legs: JourneyLeg[]
}

export interface DirectTrip {
  /** Seconds. */
  duration: number
  /** Metres. */
  distance: number
}

export interface JourneyComparison {
  walk: DirectTrip | null
  bike: DirectTrip | null
}

/** `POST /api/v1/cities/{city}/journeys/search/` → `200`. */
export interface JourneySearchResponse {
  from: JourneyPlace
  to: JourneyPlace
  itineraries: Itinerary[]
  comparison: JourneyComparison
}

/** One licence attribution of a city (from city config). Proper names and URLs are not translated. */
export interface DataSource {
  name: string
  url: string
  /** Licence name, e.g. `CC BY 4.0`; `null` when the config has none. */
  licence: string | null
  licence_url: string | null
  /** In the request language; `null` when the config has none. */
  description: string | null
}

/** One active static GTFS feed version: when the data was created, retrieved and imported. */
export interface DataFeed {
  feed_id: string
  /** From `feed_info.txt`; `null` when empty. */
  publisher_name: string | null
  /** Publisher's `Last-Modified` (ISO 8601 with offset); `null` when absent or unparsable. */
  last_modified: string | null
  /** ISO 8601 with offset. */
  downloaded_at: string
  imported_at: string | null
  service_start_date: ServiceDate | null
  service_end_date: ServiceDate | null
}

export interface DataSourcesCity {
  id: CityId
  /** In the request language. */
  name: string
  /** In city config order. */
  sources: DataSource[]
  /** Ordered by `feed_id`; empty when nothing has been imported yet. */
  feeds: DataFeed[]
}

/** `GET /api/v1/data-sources/` → `200`. */
export interface DataSourcesResponse {
  /** Every configured city, ordered by `id`. */
  cities: DataSourcesCity[]
}

// ---------------------------------------------------------------------------
// Stop departures board (#73)
// ---------------------------------------------------------------------------

/**
 * `live`: `expected` and `delay_seconds` are set (delay may be negative or 0); `canceled` and
 * `scheduled` (no live data): both are `null`.
 */
export type DepartureStatus = 'live' | 'canceled' | 'scheduled'

export interface StopDeparture {
  line: LineSummary
  trip_id: TripId
  headsign: string
  /** Platform (stop id) the vehicle departs from, within the stop group. */
  platform_id: StopId
  platform_code: string | null
  /** ISO 8601 with offset. */
  scheduled: string
  /** ISO 8601 with offset; only for `live`. */
  expected: string | null
  /** Only for `live`; negative = early. */
  delay_seconds: number | null
  status: DepartureStatus
}

/** The stop group the board covers (same grouping as stop search). */
export interface DeparturesStop {
  /** The requested platform id. */
  id: StopId
  name: string
  stop_ids: StopId[]
}

/** `GET /api/v1/cities/{city}/stops/{stop_id}/departures/?limit=`. */
export interface StopDepartures {
  stop: DeparturesStop
  /** ISO 8601 with offset. */
  generated_at: string
  /** `false`: no live data for the city or the feed is stale; every departure is `scheduled`. */
  realtime_available: boolean
  /** Sorted by effective time (expected, else scheduled), then scheduled. May be empty. */
  departures: StopDeparture[]
}

// ---------------------------------------------------------------------------
// Assistant (#18)
// ---------------------------------------------------------------------------

export type ChatRole = 'user' | 'assistant'

/** One message of the conversation; `text` is plain text (1–1000 characters after trimming). */
export interface ChatMessage {
  role: ChatRole
  text: string
}

/** Body of `POST /api/v1/assistant/chat/`: 1–20 messages, oldest first, the last one `user`. */
export interface ChatRequest {
  city: CityId
  messages: ChatMessage[]
}

/** `journey` card: one itinerary, shapes as in the journey search response. */
export interface JourneyChatCard {
  type: 'journey'
  from: JourneyPlace
  to: JourneyPlace
  itinerary: Itinerary
  comparison: JourneyComparison
}

/** One upcoming departure of a `departures` card (timetable ids). */
export interface ChatDeparture {
  /** Platform this departure leaves from (use it for the stop timetable link). */
  stop_id: StopId
  line: LineSummary
  direction: DirectionId
  headsign: string
  /** `HH:MM` local. */
  time: string
  next_day: boolean
  date: ServiceDate
  trip_id: TripId
}

/** `departures` card: up to 10 upcoming departures at one stop, ascending. */
export interface DeparturesChatCard {
  type: 'departures'
  stop: StopRef
  departures: ChatDeparture[]
}

/** `stops` card: up to 5 stops as in the stop search (ambiguous place names). */
export interface StopsChatCard {
  type: 'stops'
  stops: StopSearchResult[]
}

export type ChatCard = JourneyChatCard | DeparturesChatCard | StopsChatCard

/** `POST /api/v1/assistant/chat/` → `200`. */
export interface ChatResponse {
  message: ChatMessage
  /** 0–3 cards. Typed as `unknown` because clients must ignore card types they do not know. */
  cards: unknown[]
}
