/**
 * City helpers. The list of cities and their settings (names, map view, vehicle types, line
 * groups, realtime availability) come from `GET /api/v1/cities/`; nothing city-specific is
 * hard-coded in the frontend.
 */

import type { City, CityId, LatLon } from '@/types/api'

export type { City, CityDetail, CityId, CityMapConfig, LatLon } from '@/types/api'

/** Converts an API point to MapLibre's `[longitude, latitude]` order. */
export function toLngLat(point: LatLon): [number, number] {
  return [point.lon, point.lat]
}

/** Finds a city by id in a list loaded from the API. */
export function findCity(cities: readonly City[], id: CityId | null | undefined): City | undefined {
  if (!id) return undefined
  return cities.find((city) => city.id === id)
}
