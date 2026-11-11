import { getCurrentLocale } from '@/i18n'
import type { ApiErrorBody, HealthResponse } from '@/types/api'

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
