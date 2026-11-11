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
