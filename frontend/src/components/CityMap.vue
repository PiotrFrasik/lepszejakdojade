<script setup lang="ts">
import 'maplibre-gl/dist/maplibre-gl.css'
import { Map as MapLibreMap, NavigationControl, type MapOptions } from 'maplibre-gl'
import { onBeforeUnmount, onMounted, shallowRef, useTemplateRef, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import type { CityConfig } from '@/config/cities'
import { MAP_MAX_ZOOM, OSM_COPYRIGHT_URL, buildBaseStyle } from '@/config/map'

const props = defineProps<{
  city: CityConfig
}>()

const { t, locale } = useI18n()
const container = useTemplateRef<HTMLDivElement>('container')
const map = shallowRef<MapLibreMap | null>(null)

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function attributionHtml(): string {
  return `&copy; <a href="${OSM_COPYRIGHT_URL}" target="_blank" rel="noopener">${escapeHtml(
    t('map.osmContributors'),
  )}</a>`
}

/** MapLibre's own UI strings (control tooltips etc.), taken from i18n. */
function mapLocale(): Record<string, string> {
  return {
    'Map.Title': t('map.controls.title'),
    'NavigationControl.ZoomIn': t('map.controls.zoomIn'),
    'NavigationControl.ZoomOut': t('map.controls.zoomOut'),
    'NavigationControl.ResetBearing': t('map.controls.resetBearing'),
    'AttributionControl.ToggleAttribution': t('map.controls.toggleAttribution'),
    'AttributionControl.MapFeedback': t('map.controls.mapFeedback'),
    'GeolocateControl.FindMyLocation': t('map.controls.findMyLocation'),
    'GeolocateControl.LocationNotAvailable': t('map.controls.locationNotAvailable'),
    'Popup.Close': t('map.controls.popupClose'),
    'CooperativeGesturesHandler.WindowsHelpText': t('map.controls.cooperativeWindows'),
    'CooperativeGesturesHandler.MacHelpText': t('map.controls.cooperativeMac'),
    'CooperativeGesturesHandler.MobileHelpText': t('map.controls.cooperativeMobile'),
  }
}

function prefersReducedMotion(): boolean {
  return (
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  )
}

/** Creates the map; keeps the current camera when re-creating (e.g. after a language change). */
function createMap(): void {
  if (!container.value) return
  const previous = map.value
  const camera: Pick<MapOptions, 'center' | 'zoom' | 'bearing' | 'pitch'> = previous
    ? {
        center: previous.getCenter(),
        zoom: previous.getZoom(),
        bearing: previous.getBearing(),
        pitch: previous.getPitch(),
      }
    : { center: props.city.center, zoom: props.city.zoom }
  previous?.remove()

  const instance = new MapLibreMap({
    container: container.value,
    style: buildBaseStyle(attributionHtml()),
    maxZoom: MAP_MAX_ZOOM,
    locale: mapLocale(),
    ...camera,
  })
  instance.addControl(new NavigationControl({ visualizePitch: true }), 'top-right')
  map.value = instance
}

onMounted(createMap)

onBeforeUnmount(() => {
  map.value?.remove()
  map.value = null
})

watch(
  () => props.city.id,
  () => {
    const instance = map.value
    if (!instance) return
    const target = { center: props.city.center, zoom: props.city.zoom, bearing: 0, pitch: 0 }
    if (prefersReducedMotion()) instance.jumpTo(target)
    else instance.flyTo({ ...target, essential: false })
  },
)

// MapLibre UI strings and attribution are fixed at construction, so rebuild on language change.
watch(locale, createMap)
</script>

<template>
  <div
    ref="container"
    class="city-map"
    role="region"
    :aria-label="t('map.label', { city: city.name })"
    :data-city="city.id"
  ></div>
</template>

<style scoped>
.city-map {
  width: 100%;
  height: 100%;
  min-height: 18rem;
}
</style>
