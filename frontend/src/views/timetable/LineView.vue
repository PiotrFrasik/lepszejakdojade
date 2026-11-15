<script setup lang="ts">
import { computed, defineAsyncComponent, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute, useRouter } from 'vue-router'

import { getLineRoute } from '@/api/client'
import LoadStatus from '@/components/LoadStatus.vue'
import LineBadge from '@/components/timetable/LineBadge.vue'
import LineDiagram from '@/components/timetable/LineDiagram.vue'
import ServiceDatePicker from '@/components/timetable/ServiceDatePicker.vue'
import { useApiResource } from '@/composables/useApiResource'
import { useFormat } from '@/composables/useFormat'
import { useTimetableRoute } from '@/composables/useTimetableRoute'
import { useCityStore } from '@/stores/city'
import type { DirectionId, RouteVariant, StopId } from '@/types/api'
import { serviceDateToDate } from '@/utils/serviceDate'

// MapLibre is large; load it only when the route is shown.
const RouteMap = defineAsyncComponent(() => import('@/components/timetable/RouteMap.vue'))

/** Timetable step 3: direction toggle, vertical line diagram and route map of one line. */
const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const cityStore = useCityStore()
const fmt = useFormat()
const tt = useTimetableRoute()

const resource = useApiResource(
  () =>
    tt.cityId.value && tt.lineId.value
      ? {
          city: tt.cityId.value,
          line: tt.lineId.value,
          direction: tt.direction.value,
          date: tt.queryDate.value,
        }
      : null,
  (key, signal) =>
    getLineRoute(key.city, key.line, { direction: key.direction, date: key.date }, signal),
  // Keep the toggle, date picker and map mounted while another direction or date loads.
  { keepPrevious: true },
)

const data = computed(() => resource.data.value)
const loading = computed(() => resource.status.value === 'loading')
const headsign = computed(
  () => data.value?.directions.find((d) => d.direction === data.value?.direction)?.headsign ?? '',
)
/** The API moved to the next day with service (only for the data of the current request). */
const shiftedDate = computed(() =>
  data.value && !loading.value && data.value.date !== tt.date.value ? data.value.date : null,
)

/**
 * One-off notice passed in the URL by the stop timetable (`?notice=oppositeNotServed`); it is
 * shown here and removed from the URL so a reload or a shared link does not repeat it.
 */
const NOTICES = { oppositeNotServed: 'timetable.oppositeNotServed' } as const
const noticeKey = ref<(typeof NOTICES)[keyof typeof NOTICES] | null>(null)

watch(
  () => route.query.notice,
  (value) => {
    if (value === undefined) return
    const raw = Array.isArray(value) ? value[0] : value
    noticeKey.value = raw && raw in NOTICES ? NOTICES[raw as keyof typeof NOTICES] : null
    const rest = { ...route.query }
    delete rest.notice
    void router.replace({ query: rest })
  },
  { immediate: true },
)

// The notice belongs to the switch that caused it; drop it on any later change.
watch([() => tt.lineId.value, () => tt.direction.value, () => tt.queryDate.value], () => {
  if (route.query.notice === undefined) noticeKey.value = null
})
const otherVariants = computed<RouteVariant[]>(() =>
  (data.value?.variants ?? []).filter((v) => v.kind !== 'main'),
)

function chooseDirection(direction: DirectionId): void {
  if (direction !== tt.direction.value) tt.setDirection(direction)
}

function openStop(stopId: StopId): void {
  void router.push(tt.stopLink(stopId))
}

function formatDate(date: string): string {
  return fmt.date(serviceDateToDate(date))
}

function variantKind(variant: RouteVariant): string {
  return t(`timetable.variantKinds.${variant.kind}`)
}
</script>

<template>
  <section class="page line-view">
    <nav class="line-view__back no-print" :aria-label="t('timetable.breadcrumbs')">
      <RouterLink
        :to="{
          name: 'timetable',
          query: data ? { type: data.line.vehicle_type } : undefined,
        }"
        >← {{ t('timetable.backToLines') }}</RouterLink
      >
    </nav>

    <p v-if="noticeKey" class="line-view__notice" role="status">{{ t(noticeKey) }}</p>

    <LoadStatus
      :loading="loading"
      :error="resource.error.value"
      :not-found-text="t('timetable.lineNotFound')"
      :loading-text="t('timetable.loadingRoute')"
      @retry="resource.reload"
    />

    <template v-if="data">
      <header class="line-view__header">
        <h1 class="line-view__title">
          <LineBadge :line="data.line" size="lg" aria-hidden="true" />
          <span class="visually-hidden">{{
            t('timetable.lineLabel', { line: data.line.short_name })
          }}</span>
          <span class="line-view__headsign">→ {{ headsign }}</span>
        </h1>
        <p class="line-view__type">{{ t(`timetable.vehicleType.${data.line.vehicle_type}`) }}</p>
      </header>

      <div class="line-view__controls">
        <div
          v-if="data.directions.length > 1"
          class="direction-toggle"
          role="group"
          :aria-label="t('timetable.direction')"
        >
          <button
            v-for="dir in data.directions"
            :key="dir.direction"
            type="button"
            class="direction-toggle__option"
            :aria-pressed="dir.direction === data.direction"
            @click="chooseDirection(dir.direction)"
          >
            → {{ dir.headsign }}
          </button>
        </div>
        <ServiceDatePicker
          :model-value="tt.date.value"
          :today="tt.today.value"
          @update:model-value="tt.setDate"
        />
      </div>

      <p v-if="shiftedDate" class="line-view__notice" role="status">
        {{
          t('timetable.noServiceShifted', {
            requested: formatDate(tt.date.value),
            shown: formatDate(shiftedDate),
          })
        }}
      </p>

      <details v-if="otherVariants.length" class="line-view__variants">
        <summary>{{ t('timetable.variantsTitle', { count: otherVariants.length }) }}</summary>
        <ul>
          <li v-for="variant in otherVariants" :key="variant.id">
            <strong>{{ variantKind(variant) }}</strong
            >: → {{ variant.headsign }}
            <span class="line-view__muted">
              ({{ t('timetable.tripCount', { count: variant.trip_count }) }})
            </span>
          </li>
        </ul>
      </details>

      <p v-if="data.stops.length === 0" class="line-view__muted">{{ t('timetable.noStops') }}</p>
      <div v-else class="line-view__layout">
        <div class="line-view__diagram">
          <h2 class="visually-hidden">{{ t('timetable.stopsHeading') }}</h2>
          <p class="line-view__hint">{{ t('timetable.pickStopHint') }}</p>
          <LineDiagram :route="data" :stop-link="(id) => tt.stopLink(id)" />
        </div>
        <div class="line-view__map no-print">
          <RouteMap :route="data" :city="cityStore.currentCity" @select="openStop" />
        </div>
      </div>
    </template>
  </section>
</template>

<style scoped>
.line-view {
  max-width: 72rem;
}

.line-view__back {
  margin-bottom: var(--space-3);
}

.line-view__header {
  margin-bottom: var(--space-3);
}

.line-view__title {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2) var(--space-3);
  margin: 0;
}

.line-view__headsign {
  font-size: 1.25rem;
}

.line-view__type {
  margin: var(--space-1) 0 0;
  color: var(--color-text-muted);
}

.line-view__controls {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  gap: var(--space-4);
  margin-bottom: var(--space-4);
}

.direction-toggle {
  display: flex;
  flex-wrap: wrap;
  border: 1px solid var(--color-primary);
  border-radius: var(--radius);
  overflow: hidden;
  max-width: 100%;
}

.direction-toggle__option {
  flex: 1 1 auto;
  min-height: 2.75rem;
  padding: var(--space-2) var(--space-3);
  border: 0;
  background: var(--color-surface);
  color: var(--color-primary);
  font: inherit;
  font-weight: 600;
  text-align: left;
  cursor: pointer;
}

.direction-toggle__option + .direction-toggle__option {
  border-left: 1px solid var(--color-primary);
}

.direction-toggle__option[aria-pressed='true'] {
  background: var(--color-primary);
  color: var(--color-on-primary);
}

.direction-toggle__option:focus-visible {
  outline-offset: -4px;
}

.line-view__notice {
  padding: var(--space-2) var(--space-3);
  border-left: 4px solid var(--color-warning);
  background: var(--color-highlight);
}

.line-view__variants {
  margin-bottom: var(--space-4);
}

.line-view__variants summary {
  cursor: pointer;
  font-weight: 600;
}

.line-view__muted,
.line-view__hint {
  color: var(--color-text-muted);
}

.line-view__hint {
  margin: 0 0 var(--space-2);
  font-size: 0.875rem;
}

.line-view__layout {
  display: grid;
  gap: var(--space-4);
}

.line-view__map {
  height: 20rem;
}

@media (min-width: 840px) {
  .line-view__layout {
    grid-template-columns: minmax(18rem, 1fr) 1.4fr;
    align-items: start;
  }

  .line-view__map {
    position: sticky;
    top: var(--space-3);
    height: calc(100vh - 8rem);
    min-height: 24rem;
  }
}
</style>
