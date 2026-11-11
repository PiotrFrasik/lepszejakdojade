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
