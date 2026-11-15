<script setup lang="ts">
import 'maplibre-gl/dist/maplibre-gl.css'
import {
  Map as MapLibreMap,
  NavigationControl,
  Popup,
  type GeoJSONSource,
  type LngLatBoundsLike,
  type MapLayerMouseEvent,
} from 'maplibre-gl'
// `@types/geojson` comes with maplibre-gl.
import type { Feature, FeatureCollection, LineString, Point } from 'geojson'
import { onBeforeUnmount, onMounted, shallowRef, useTemplateRef, watch } from 'vue'

import { prefersReducedMotion, useMapI18n } from '@/composables/useMapI18n'
import { toLngLat, type City } from '@/config/cities'
import { MAP_MAX_ZOOM, buildBaseStyle } from '@/config/map'
import '@/config/mapWorker'
import type { LineRoute, StopId } from '@/types/api'

/**
 * Map of one line direction: the shape and the stops. Clicking a stop emits `select`. The line
 * diagram next to it is the keyboard-accessible way to pick a stop; this map is supplementary.
 */
const props = defineProps<{
  route: LineRoute
  city: City | null
  selectedStopId?: StopId | null
}>()

const emit = defineEmits<{ select: [stopId: StopId] }>()

const SHAPE_SOURCE = 'route-shape'
const STOPS_SOURCE = 'route-stops'
const STOPS_LAYER = 'route-stops-circle'

const { t, locale, attributionHtml, mapLocale } = useMapI18n()
const container = useTemplateRef<HTMLDivElement>('container')
const map = shallowRef<MapLibreMap | null>(null)
let loaded = false
let popup: Popup | null = null

function shapeData(): Feature<LineString> {
  const coordinates = props.route.shape?.coordinates?.length
    ? props.route.shape.coordinates
    : props.route.stops.map((stop) => [stop.lon, stop.lat] as [number, number])
  return { type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates } }
}

function stopsData(): FeatureCollection<Point> {
  return {
    type: 'FeatureCollection',
    features: props.route.stops.map((stop) => ({
      type: 'Feature',
      properties: {
        stop_id: stop.stop_id,
        name: stop.name,
        variant_only: stop.variant_only,
        selected: stop.stop_id === props.selectedStopId,
      },
      geometry: { type: 'Point', coordinates: [stop.lon, stop.lat] },
    })),
  }
}

function bounds(): LngLatBoundsLike | null {
  const points: [number, number][] = [
    ...(props.route.shape?.coordinates ?? []),
    ...props.route.stops.map((stop) => [stop.lon, stop.lat] as [number, number]),
  ]
  if (points.length === 0) return null
  let [minLng, minLat] = points[0]!
  let [maxLng, maxLat] = points[0]!
  for (const [lng, lat] of points) {
    minLng = Math.min(minLng, lng)
    minLat = Math.min(minLat, lat)
    maxLng = Math.max(maxLng, lng)
    maxLat = Math.max(maxLat, lat)
  }
  return [
    [minLng, minLat],
    [maxLng, maxLat],
  ]
}

function fit(animate: boolean): void {
  const target = bounds()
  if (!map.value || !target) return
  map.value.fitBounds(target, {
    padding: 32,
    maxZoom: 16,
    animate: animate && !prefersReducedMotion(),
  })
}

function addLayers(instance: MapLibreMap): void {
  const colour = props.route.line.colour
  instance.addSource(SHAPE_SOURCE, { type: 'geojson', data: shapeData() })
  instance.addSource(STOPS_SOURCE, { type: 'geojson', data: stopsData() })
  instance.addLayer({
    id: 'route-shape-casing',
    type: 'line',
    source: SHAPE_SOURCE,
    layout: { 'line-join': 'round', 'line-cap': 'round' },
    paint: { 'line-color': '#ffffff', 'line-width': 8 },
  })
  instance.addLayer({
    id: 'route-shape-line',
    type: 'line',
    source: SHAPE_SOURCE,
    layout: { 'line-join': 'round', 'line-cap': 'round' },
    paint: { 'line-color': colour, 'line-width': 5 },
  })
  instance.addLayer({
    id: STOPS_LAYER,
    type: 'circle',
    source: STOPS_SOURCE,
    paint: {
      'circle-radius': ['case', ['get', 'selected'], 9, 6],
      'circle-color': ['case', ['get', 'selected'], colour, '#ffffff'],
      'circle-stroke-color': ['case', ['get', 'variant_only'], '#6b7280', colour],
      'circle-stroke-width': 3,
    },
  })

  instance.on('click', STOPS_LAYER, (event: MapLayerMouseEvent) => {
    const id = event.features?.[0]?.properties?.stop_id
    if (typeof id === 'string') emit('select', id)
  })
  instance.on('mouseenter', STOPS_LAYER, (event: MapLayerMouseEvent) => {
    instance.getCanvas().style.cursor = 'pointer'
    const feature = event.features?.[0]
    const name = feature?.properties?.name
    if (typeof name !== 'string' || feature?.geometry.type !== 'Point') return
    popup?.remove()
    popup = new Popup({ closeButton: false, closeOnClick: false, offset: 10 })
      .setLngLat(feature.geometry.coordinates as [number, number])
      .setText(name)
      .addTo(instance)
  })
  instance.on('mouseleave', STOPS_LAYER, () => {
    instance.getCanvas().style.cursor = ''
    popup?.remove()
    popup = null
  })
}

function createMap(): void {
  if (!container.value) return
  const previous = map.value
  const camera = previous
    ? { center: previous.getCenter(), zoom: previous.getZoom() }
    : props.city
      ? { center: toLngLat(props.city.map.center), zoom: props.city.map.zoom }
      : { center: props.route.shape?.coordinates?.[0] ?? ([0, 0] as [number, number]), zoom: 12 }
  popup?.remove()
  popup = null
  previous?.remove()
  loaded = false

  const instance = new MapLibreMap({
    container: container.value,
    style: buildBaseStyle(attributionHtml()),
    maxZoom: MAP_MAX_ZOOM,
    locale: mapLocale(),
    ...camera,
  })
  instance.addControl(new NavigationControl({ showCompass: false }), 'top-right')
  instance.on('load', () => {
    if (map.value !== instance) return
    loaded = true
    addLayers(instance)
    if (!previous) fit(false)
  })
  map.value = instance
}

function updateData(refit: boolean): void {
  const instance = map.value
  if (!instance || !loaded) return
  ;(instance.getSource(SHAPE_SOURCE) as GeoJSONSource | undefined)?.setData(shapeData())
  ;(instance.getSource(STOPS_SOURCE) as GeoJSONSource | undefined)?.setData(stopsData())
  instance.setPaintProperty('route-shape-line', 'line-color', props.route.line.colour)
  if (refit) fit(true)
}

onMounted(createMap)

onBeforeUnmount(() => {
  popup?.remove()
  map.value?.remove()
  map.value = null
})

watch(
  () => props.route,
  () => updateData(true),
)
watch(
  () => props.selectedStopId,
  () => updateData(false),
)
// MapLibre UI strings and attribution are fixed at construction, so rebuild on language change.
watch(locale, createMap)
</script>

<template>
  <div
    ref="container"
    class="route-map"
    role="region"
    :aria-label="
      t('timetable.routeMapLabel', {
        line: route.line.short_name,
        headsign: route.directions.find((d) => d.direction === route.direction)?.headsign ?? '',
      })
    "
  ></div>
</template>

<style scoped>
.route-map {
  width: 100%;
  height: 100%;
  min-height: 18rem;
  border-radius: var(--radius);
  overflow: hidden;
}
</style>
