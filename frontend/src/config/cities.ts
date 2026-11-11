/**
 * Temporary local city configuration.
 *
 * TODO(#5): replace with data from `GET /api/v1/cities/`. Keep the `CityConfig` shape close to
 * what the API returns so the switch is a data-source change only.
 */

export type CityId = 'krakow' | 'warszawa'

export interface CityConfig {
  /** Slug used in API paths: `/api/v1/cities/{id}/…`. */
  id: CityId
  /** Proper name, never translated. */
  name: string
  /** Map centre as `[longitude, latitude]`. */
  center: [number, number]
  /** Initial map zoom level. */
  zoom: number
}

export const CITIES: readonly CityConfig[] = [
  { id: 'krakow', name: 'Kraków', center: [19.9383, 50.0614], zoom: 12 },
  { id: 'warszawa', name: 'Warszawa', center: [21.0122, 52.2297], zoom: 11 },
]

export function findCity(id: string | null | undefined): CityConfig | undefined {
  return CITIES.find((city) => city.id === id)
}
