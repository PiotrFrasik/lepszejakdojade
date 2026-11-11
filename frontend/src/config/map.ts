import type { StyleSpecification } from 'maplibre-gl'

/** Free OpenStreetMap raster tiles; no API key needed. Attribution is required by the licence. */
export const OSM_TILE_URL = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'
export const OSM_COPYRIGHT_URL = 'https://www.openstreetmap.org/copyright'
export const MAP_MAX_ZOOM = 19

/** Builds the base map style. `attribution` is HTML provided by i18n. */
export function buildBaseStyle(attribution: string): StyleSpecification {
  return {
    version: 8,
    sources: {
      osm: {
        type: 'raster',
        tiles: [OSM_TILE_URL],
        tileSize: 256,
        maxzoom: MAP_MAX_ZOOM,
        attribution,
      },
    },
    layers: [{ id: 'osm', type: 'raster', source: 'osm' }],
  }
}
