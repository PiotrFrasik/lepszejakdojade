import { jsonResponse } from './helpers'

/** Test fixtures: fictional cities, so tests do not depend on real-city constants. */
const NAMES: Record<string, Record<string, string>> = {
  alpha: { pl: 'Alfa', en: 'Alpha' },
  beta: { pl: 'Beta', en: 'Betaville' },
}
const MAPS: Record<string, { center: { lat: number; lon: number }; zoom: number }> = {
  alpha: { center: { lat: 10.5, lon: 20.25 }, zoom: 11 },
  beta: { center: { lat: -5.5, lon: 40.75 }, zoom: 12 },
}

export function cityList(lang = 'pl') {
  return Object.keys(NAMES).map((id) => ({ id, name: NAMES[id]![lang]!, map: MAPS[id]! }))
}

export function cityDetail(id: string, lang = 'pl') {
  return {
    id,
    name: NAMES[id]![lang]!,
    map: MAPS[id]!,
    timezone: 'Europe/Warsaw',
    vehicle_types: ['tram', 'bus'],
    line_groups: [{ id: 'g1', name: 'Group', colour: '#112233' }],
    realtime: { departures: true, vehicles: false },
  }
}

export interface FetchCall {
  url: string
  acceptLanguage: string | null
  signal: AbortSignal | null | undefined
}

/**
 * Fetch mock serving the cities endpoints (and health). `calls` records requests.
 * Override `list` / `detail` to return custom responses.
 */
export function makeCitiesFetch(
  overrides: {
    list?: (lang: string) => Response | Promise<Response>
    detail?: (id: string, lang: string) => Response | Promise<Response>
  } = {},
) {
  const calls: FetchCall[] = []
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const headers = new Headers(init?.headers)
    const lang = headers.get('Accept-Language') ?? 'pl'
    calls.push({ url, acceptLanguage: headers.get('Accept-Language'), signal: init?.signal })
    if (url.endsWith('/cities/')) {
      return overrides.list ? overrides.list(lang) : jsonResponse(cityList(lang))
    }
    const m = /\/cities\/([^/]+)\/$/.exec(url)
    if (m) {
      const id = decodeURIComponent(m[1]!)
      if (overrides.detail) return overrides.detail(id, lang)
      if (!NAMES[id]) {
        return jsonResponse({ error: { code: 'not_found', message: 'Not found' } }, 404)
      }
      return jsonResponse(cityDetail(id, lang))
    }
    return jsonResponse({ status: 'ok', checks: {}, version: '1' })
  })
  return { fn, calls }
}

/** Waits until pending promises and timers settle. */
export async function settle(): Promise<void> {
  for (let i = 0; i < 5; i++) await new Promise((r) => setTimeout(r, 0))
}
