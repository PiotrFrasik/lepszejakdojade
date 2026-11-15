import { getCurrentLocale } from '@/i18n'
import type {
  ApiErrorBody,
  City,
  CityDetail,
  CityId,
  DataSourcesResponse,
  DirectionId,
  HealthResponse,
  JourneySearchRequest,
  JourneySearchResponse,
  Line,
  LineId,
  LineRoute,
  ServiceDate,
  StopId,
  StopSearchResult,
  StopTimetable,
  Trip,
  TripId,
  VehicleType,
} from '@/types/api'

export const API_BASE = '/api/v1'

/** Error thrown for non-2xx responses and network failures. */
export class ApiError extends Error {
  /** HTTP status; `0` for network errors. */
  readonly status: number
  /** `error.code` from the API body, or a client-side code (`network_error`, `invalid_response`, `http_error`). */
  readonly code: string
  /** Parsed response body, if any. */
  readonly body: unknown

  constructor(status: number, code: string, message: string, body?: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.body = body
  }
}

export type QueryValue = string | number | boolean | null | undefined

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE'
  query?: Record<string, QueryValue>
  body?: unknown
  signal?: AbortSignal
  /** Non-2xx statuses whose JSON body should be returned instead of thrown. */
  acceptStatuses?: number[]
}

export function buildUrl(path: string, query?: Record<string, QueryValue>): string {
  const normalized = path.startsWith('/') ? path : `/${path}`
  let url = `${API_BASE}${normalized}`
  if (query) {
    const params = new URLSearchParams()
    for (const [key, value] of Object.entries(query)) {
      if (value !== null && value !== undefined) params.append(key, String(value))
    }
    const qs = params.toString()
    if (qs) url += `?${qs}`
  }
  return url
}

function isApiErrorBody(value: unknown): value is ApiErrorBody {
  if (typeof value !== 'object' || value === null || !('error' in value)) return false
  const error = (value as { error: unknown }).error
  return typeof error === 'object' && error !== null && 'code' in error && 'message' in error
}

function isAbortError(err: unknown): boolean {
  return (
    typeof err === 'object' && err !== null && (err as { name?: unknown }).name === 'AbortError'
  )
}

/**
 * Calls the backend at a relative `/api/v1/...` path. Always sends `Accept-Language`
 * with the current UI locale. Abort errors are re-thrown unchanged.
 */
export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', query, body, signal, acceptStatuses = [] } = options
  const headers: Record<string, string> = {
    Accept: 'application/json',
    'Accept-Language': getCurrentLocale(),
  }
  if (body !== undefined) headers['Content-Type'] = 'application/json'

  let response: Response
  try {
    response = await fetch(buildUrl(path, query), {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
      credentials: 'same-origin',
    })
  } catch (err) {
    if (isAbortError(err)) throw err
    throw new ApiError(0, 'network_error', err instanceof Error ? err.message : String(err))
  }

  let data: unknown = undefined
  if (response.status !== 204) {
    const text = await response.text()
    if (text) {
      try {
        data = JSON.parse(text)
      } catch {
        throw new ApiError(response.status, 'invalid_response', response.statusText, text)
      }
    }
  }

  if (!response.ok && !acceptStatuses.includes(response.status)) {
    if (isApiErrorBody(data)) {
      throw new ApiError(response.status, data.error.code, data.error.message, data)
    }
    throw new ApiError(response.status, 'http_error', response.statusText, data)
  }

  return data as T
}

export function apiGet<T>(
  path: string,
  options: Omit<RequestOptions, 'method' | 'body'> = {},
): Promise<T> {
  return apiRequest<T>(path, { ...options, method: 'GET' })
}

/** `GET /api/v1/health/`. A 503 still carries a valid body, so it is returned, not thrown. */
export function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return apiGet<HealthResponse>('/health/', { signal, acceptStatuses: [503] })
}

/** `GET /api/v1/cities/`: all cities, names in the current UI language. */
export function getCities(signal?: AbortSignal): Promise<City[]> {
  return apiGet<City[]>('/cities/', { signal })
}

/** `GET /api/v1/cities/{city}/`: city settings. Unknown city → `ApiError` with status 404. */
export function getCity(id: CityId, signal?: AbortSignal): Promise<CityDetail> {
  return apiGet<CityDetail>(`/cities/${encodeURIComponent(id)}/`, { signal })
}

/** `GET /api/v1/data-sources/`: licence attributions and data freshness of every city. */
export function getDataSources(signal?: AbortSignal): Promise<DataSourcesResponse> {
  return apiGet<DataSourcesResponse>('/data-sources/', { signal })
}

function cityPath(city: CityId, rest: string): string {
  return `/cities/${encodeURIComponent(city)}/${rest}`
}

/** `GET /api/v1/cities/{city}/lines/`: all lines (plain array), optionally of one vehicle type. */
export function getLines(
  city: CityId,
  vehicleType?: VehicleType | null,
  signal?: AbortSignal,
): Promise<Line[]> {
  return apiGet<Line[]>(cityPath(city, 'lines/'), {
    signal,
    query: { vehicle_type: vehicleType ?? undefined },
  })
}

/** `direction` / `date` query of the timetable endpoints; omitted values use the API defaults. */
export interface DirectionDateQuery {
  direction?: DirectionId
  date?: ServiceDate | null
}

/** `GET /api/v1/cities/{city}/lines/{line_id}/route/`: line diagram for one direction. */
export function getLineRoute(
  city: CityId,
  lineId: LineId,
  params: DirectionDateQuery = {},
  signal?: AbortSignal,
): Promise<LineRoute> {
  return apiGet<LineRoute>(cityPath(city, `lines/${encodeURIComponent(lineId)}/route/`), {
    signal,
    query: { direction: params.direction, date: params.date ?? undefined },
  })
}

/** `GET /api/v1/cities/{city}/lines/{line_id}/stops/{stop_id}/timetable/`. */
export function getStopTimetable(
  city: CityId,
  lineId: LineId,
  stopId: StopId,
  params: DirectionDateQuery = {},
  signal?: AbortSignal,
): Promise<StopTimetable> {
  return apiGet<StopTimetable>(
    cityPath(
      city,
      `lines/${encodeURIComponent(lineId)}/stops/${encodeURIComponent(stopId)}/timetable/`,
    ),
    { signal, query: { direction: params.direction, date: params.date ?? undefined } },
  )
}

/** `GET /api/v1/cities/{city}/trips/{trip_id}/?date=`: one trip on one service date. */
export function getTrip(
  city: CityId,
  tripId: TripId,
  date: ServiceDate,
  signal?: AbortSignal,
): Promise<Trip> {
  return apiGet<Trip>(cityPath(city, `trips/${encodeURIComponent(tripId)}/`), {
    signal,
    query: { date },
  })
}

/** `GET /api/v1/cities/{city}/stops/?q=`: stop name search (`q` of at least 2 characters). */
export function searchStops(
  city: CityId,
  q: string,
  signal?: AbortSignal,
): Promise<StopSearchResult[]> {
  return apiGet<StopSearchResult[]>(cityPath(city, 'stops/'), { signal, query: { q: q.trim() } })
}

/**
 * `POST /api/v1/cities/{city}/journeys/search/`. A missing or unreachable journey planner is an
 * `ApiError` with status 503 and code `journey_planner_unavailable`.
 */
export function searchJourneys(
  city: CityId,
  request: JourneySearchRequest,
  signal?: AbortSignal,
): Promise<JourneySearchResponse> {
  return apiRequest<JourneySearchResponse>(cityPath(city, 'journeys/search/'), {
    method: 'POST',
    body: request,
    signal,
  })
}
