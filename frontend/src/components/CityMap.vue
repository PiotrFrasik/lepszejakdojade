<script setup lang="ts">
import 'maplibre-gl/dist/maplibre-gl.css'
import { Map as MapLibreMap, NavigationControl, type MapOptions } from 'maplibre-gl'
import { onBeforeUnmount, onMounted, shallowRef, useTemplateRef, watch } from 'vue'

import { prefersReducedMotion, useMapI18n } from '@/composables/useMapI18n'
import { toLngLat, type City } from '@/config/cities'
import { MAP_MAX_ZOOM, buildBaseStyle } from '@/config/map'
import '@/config/mapWorker'

const props = defineProps<{
  city: City
}>()

/** Initial camera of the city from the API (MapLibre wants `[lon, lat]`). */
function cityCamera(): { center: [number, number]; zoom: number } {
  return { center: toLngLat(props.city.map.center), zoom: props.city.map.zoom }
}

const { t, locale, attributionHtml, mapLocale } = useMapI18n()
const container = useTemplateRef<HTMLDivElement>('container')
const map = shallowRef<MapLibreMap | null>(null)

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
    : cityCamera()
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
    const target = { ...cityCamera(), bearing: 0, pitch: 0 }
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
