<script setup lang="ts">
import 'maplibre-gl/dist/maplibre-gl.css'
import {
  Map as MapLibreMap,
  NavigationControl,
  type GeoJSONSource,
  type MapMouseEvent,
  type MapOptions,
  type PaddingOptions,
} from 'maplibre-gl'
import { onBeforeUnmount, onMounted, ref, shallowRef, useTemplateRef, watch } from 'vue'

import { prefersReducedMotion, useMapI18n } from '@/composables/useMapI18n'
import { toLngLat, type City } from '@/config/cities'
import { MAP_MAX_ZOOM, buildBaseStyle } from '@/config/map'
import '@/config/mapWorker'
import type { Itinerary } from '@/types/api'
import { boundsOf, endpointsToGeoJson, legsToGeoJson } from '@/utils/journey'

/**
 * Full-screen map of the journey planner: the selected itinerary (walking dashed, transit in
 * the line colour) and the from / to markers. While `picking` is set, a click emits `pick`.
 * The list of connections is the accessible representation; the map is supplementary.
 */
const props = defineProps<{
  city: City
  itinerary: Itinerary | null
  from: { lat: number; lon: number } | null
  to: { lat: number; lon: number } | null
  picking: boolean
  /** Space covered by the floating panel, so fitted routes stay visible. */
  padding?: Partial<PaddingOptions>
}>()

const emit = defineEmits<{ pick: [lat: number, lon: number] }>()

const LEGS_SOURCE = 'journey-legs'
const POINTS_SOURCE = 'journey-points'

const { t, locale, attributionHtml, mapLocale } = useMapI18n()
const container = useTemplateRef<HTMLDivElement>('container')
const map = shallowRef<MapLibreMap | null>(null)
const unavailable = ref(false)
let loaded = false

function addLayers(instance: MapLibreMap): void {
  instance.addSource(LEGS_SOURCE, { type: 'geojson', data: legsToGeoJson(props.itinerary) })
  instance.addSource(POINTS_SOURCE, {
    type: 'geojson',
    data: endpointsToGeoJson(props.from, props.to),
  })
  instance.addLayer({
    id: 'journey-transit-casing',
    type: 'line',
    source: LEGS_SOURCE,
    filter: ['!=', ['get', 'mode'], 'walk'],
    layout: { 'line-join': 'round', 'line-cap': 'round' },
    paint: { 'line-color': '#ffffff', 'line-width': 9 },
  })
  instance.addLayer({
    id: 'journey-transit',
    type: 'line',
    source: LEGS_SOURCE,
    filter: ['!=', ['get', 'mode'], 'walk'],
    layout: { 'line-join': 'round', 'line-cap': 'round' },
    paint: { 'line-color': ['get', 'colour'], 'line-width': 6 },
  })
  instance.addLayer({
    id: 'journey-walk',
    type: 'line',
    source: LEGS_SOURCE,
    filter: ['==', ['get', 'mode'], 'walk'],
    layout: { 'line-join': 'round', 'line-cap': 'round' },
    paint: { 'line-color': '#4f5a6b', 'line-width': 4, 'line-dasharray': [0.5, 2] },
  })
  instance.addLayer({
    id: 'journey-points',
    type: 'circle',
    source: POINTS_SOURCE,
    paint: {
      'circle-radius': 8,
      'circle-color': ['match', ['get', 'role'], 'from', '#1e8e3e', '#c62828'],
      'circle-stroke-color': '#ffffff',
      'circle-stroke-width': 3,
    },
  })
}

function fit(animate: boolean): void {
  const instance = map.value
  if (!instance) return
  const points: [number, number][] = []
  for (const feature of legsToGeoJson(props.itinerary).features) {
    points.push(...(feature.geometry.coordinates as [number, number][]))
  }
  for (const feature of endpointsToGeoJson(props.from, props.to).features) {
    points.push(feature.geometry.coordinates as [number, number])
  }
  const bounds = boundsOf(points)
  if (!bounds) return
  const padding = { top: 48, right: 48, bottom: 48, left: 48, ...props.padding }
  instance.fitBounds(bounds, { padding, maxZoom: 16, animate: animate && !prefersReducedMotion() })
}

function setCursor(): void {
  const canvas = map.value?.getCanvas?.()
  if (canvas) canvas.style.cursor = props.picking ? 'crosshair' : ''
}

function createMap(): void {
  if (!container.value) return
  const previous = map.value
  const camera: Pick<MapOptions, 'center' | 'zoom'> = previous
    ? { center: previous.getCenter(), zoom: previous.getZoom() }
    : { center: toLngLat(props.city.map.center), zoom: props.city.map.zoom }
  previous?.remove()
  map.value = null
  loaded = false

  let instance: MapLibreMap
  try {
    instance = new MapLibreMap({
      container: container.value,
      style: buildBaseStyle(attributionHtml()),
      maxZoom: MAP_MAX_ZOOM,
      locale: mapLocale(),
      ...camera,
    })
  } catch {
    // No WebGL 2 (old browser, some test environments): the panel still works without the map.
    unavailable.value = true
    return
  }
  unavailable.value = false
  instance.addControl(new NavigationControl({ showCompass: false }), 'bottom-right')
  instance.on('load', () => {
    if (map.value !== instance) return
    loaded = true
    addLayers(instance)
    setCursor()
    if (!previous && (props.itinerary || props.from || props.to)) fit(false)
  })
  instance.on('click', (event: MapMouseEvent) => {
    if (props.picking) emit('pick', event.lngLat.lat, event.lngLat.lng)
  })
  map.value = instance
}

function updateData(refit: boolean): void {
  const instance = map.value
  if (!instance || !loaded) return
  ;(instance.getSource(LEGS_SOURCE) as GeoJSONSource | undefined)?.setData(
    legsToGeoJson(props.itinerary),
  )
  ;(instance.getSource(POINTS_SOURCE) as GeoJSONSource | undefined)?.setData(
    endpointsToGeoJson(props.from, props.to),
  )
  if (refit) fit(true)
}

onMounted(createMap)

onBeforeUnmount(() => {
  map.value?.remove()
  map.value = null
})

watch(
  () => props.itinerary,
  () => updateData(true),
)
watch(
  () => [props.from, props.to],
  () => updateData(!props.itinerary),
)
watch(() => props.picking, setCursor)
watch(
  () => props.city.id,
  () => {
    const instance = map.value
    if (!instance) return
    const target = { center: toLngLat(props.city.map.center), zoom: props.city.map.zoom }
    if (prefersReducedMotion()) instance.jumpTo(target)
    else instance.flyTo({ ...target, essential: false })
  },
)
// MapLibre UI strings and attribution are fixed at construction, so rebuild on language change.
watch(locale, createMap)
</script>

<template>
  <div class="journey-map">
    <div
      ref="container"
      class="journey-map__canvas"
      role="region"
      :aria-label="t('map.label', { city: city.name })"
      :data-city="city.id"
    ></div>
    <p v-if="unavailable" class="journey-map__unavailable">{{ t('journey.mapUnavailable') }}</p>
  </div>
</template>

<style scoped>
.journey-map {
  background: var(--color-surface-alt);
}

.journey-map__canvas {
  width: 100%;
  height: 100%;
}

.journey-map__unavailable {
  position: absolute;
  right: var(--space-4);
  bottom: var(--space-4);
  max-width: 24rem;
  margin: 0;
  padding: var(--space-3);
  border-radius: 12px;
  background: var(--color-surface);
  color: var(--color-text-muted);
  font-size: 0.875rem;
  box-shadow: 0 4px 12px rgb(15 23 42 / 15%);
}
</style>
