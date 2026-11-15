/**
 * Tells MapLibre where its web worker script is.
 *
 * maplibre-gl 6 looks for `maplibre-gl-worker.mjs` next to its own module (`import.meta.url`).
 * Vite moves the library (pre-bundled into `node_modules/.vite/deps/` in dev, hashed into
 * `assets/` in a build) but not the worker, so the worker fails to load and GeoJSON sources
 * (route lines, stops) never render. Importing the worker with `?url` makes Vite serve it in
 * dev and emit it as an asset in the build; its URL is then passed to `setWorkerUrl`.
 *
 * Import this module (for its side effect) in every component that creates a map.
 */
import * as maplibre from 'maplibre-gl'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'

try {
  maplibre.setWorkerUrl(workerUrl)
} catch {
  // Unit tests mock `maplibre-gl` without `setWorkerUrl`; there is no worker to configure.
}
