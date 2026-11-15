<script setup lang="ts">
import { computed, onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRouter } from 'vue-router'

import { ApiError, getLineRoute, getStopTimetable } from '@/api/client'
import LoadStatus from '@/components/LoadStatus.vue'
import LineBadge from '@/components/timetable/LineBadge.vue'
import ServiceDatePicker from '@/components/timetable/ServiceDatePicker.vue'
import TimetableGrid from '@/components/timetable/TimetableGrid.vue'
import TripDialog from '@/components/timetable/TripDialog.vue'
import { useApiResource } from '@/composables/useApiResource'
import { useTimetableRoute } from '@/composables/useTimetableRoute'
import type { DirectionId, ServiceDate, TimetableDeparture, TripId } from '@/types/api'

/**
 * Timetable of one line at one stop: day-type columns, date picker, quick switch to the
 * opposite direction and to the previous / next stop, trip view and a printable layout.
 */
const { t } = useI18n()
const router = useRouter()
const tt = useTimetableRoute()

const resource = useApiResource(
  () =>
    tt.cityId.value && tt.lineId.value && tt.stopId.value
      ? {
          city: tt.cityId.value,
          line: tt.lineId.value,
          stop: tt.stopId.value,
          direction: tt.direction.value,
          date: tt.queryDate.value,
        }
      : null,
  (key, signal) =>
    getStopTimetable(
      key.city,
      key.line,
      key.stop,
      { direction: key.direction, date: key.date },
      signal,
    ),
  // Keep the date picker, buttons and stop links mounted while another date or stop loads.
  { keepPrevious: true },
)

const data = computed(() => resource.data.value)

// --- Trip view -------------------------------------------------------------------------------
const selectedTrip = shallowRef<{ tripId: TripId; date: ServiceDate } | null>(null)

function openTrip(departure: TimetableDeparture, date: ServiceDate): void {
  selectedTrip.value = { tripId: departure.trip_id, date }
}

// --- Opposite direction ----------------------------------------------------------------------
const switching = ref(false)
const switchMessageKey = ref<
  'timetable.oppositeUnavailable' | 'timetable.noOppositeDirection' | null
>(null)
/** `line|stop|direction` for which the opposite direction does not exist (API 404). */
const noOppositeFor = ref<string | null>(null)
let switchController: AbortController | null = null

const currentKey = computed(() => `${tt.lineId.value}|${tt.stopId.value}|${tt.direction.value}`)
const canSwitchDirection = computed(() => noOppositeFor.value !== currentKey.value)

function cancelSwitch(): void {
  switchController?.abort()
  switchController = null
  switching.value = false
}

/**
 * The opposite direction usually stops at a different platform (another stop id), so look the
 * stop up by id, then by name, in the other direction's route. If it is not there, open the
 * line diagram of the other direction with a notice. If the direction does not exist (404),
 * hide the button for this stop.
 */
async function switchDirection(): Promise<void> {
  const current = data.value
  const city = tt.cityId.value
  if (!current || !city || switching.value) return
  const other: DirectionId = current.direction === 0 ? 1 : 0
  const key = currentKey.value
  const controller = new AbortController()
  switchController = controller
  switching.value = true
  switchMessageKey.value = null
  try {
    const route = await getLineRoute(
      city,
      current.line.id,
      { direction: other, date: tt.queryDate.value },
      controller.signal,
    )
    if (controller.signal.aborted) return
    const match =
      route.stops.find((stop) => stop.stop_id === current.stop.stop_id) ??
      route.stops.find((stop) => stop.name === current.stop.name)
    if (match) {
      await router.push(tt.stopLink(match.stop_id, other))
    } else {
      await router.push(tt.lineLink(current.line.id, other, { notice: 'oppositeNotServed' }))
    }
  } catch (err) {
    if (controller.signal.aborted) return
    if (err instanceof ApiError && err.status === 404) {
      noOppositeFor.value = key
      switchMessageKey.value = 'timetable.noOppositeDirection'
    } else {
      switchMessageKey.value = 'timetable.oppositeUnavailable'
    }
  } finally {
    if (switchController === controller) {
      switchController = null
      switching.value = false
    }
  }
}

watch(currentKey, () => {
  cancelSwitch()
  switchMessageKey.value = null
  selectedTrip.value = null
})

onBeforeUnmount(cancelSwitch)

function print(): void {
  window.print()
}
</script>

<template>
  <section class="page stop-tt">
    <nav class="stop-tt__crumbs no-print" :aria-label="t('timetable.breadcrumbs')">
      <ol>
        <li>
          <RouterLink
            :to="{ name: 'timetable', query: data ? { type: data.line.vehicle_type } : undefined }"
            >{{ t('timetable.title') }}</RouterLink
          >
        </li>
        <li>
          <RouterLink :to="tt.lineLink()">{{
            data
              ? t('timetable.lineLabel', { line: data.line.short_name })
              : t('timetable.lineDiagram')
          }}</RouterLink>
        </li>
      </ol>
    </nav>

    <LoadStatus
      :loading="resource.status.value === 'loading'"
      :error="resource.error.value"
      :not-found-text="t('timetable.stopNotFound')"
      :loading-text="t('timetable.loadingTimetable')"
      @retry="resource.reload"
    />

    <template v-if="data">
      <header class="stop-tt__header">
        <h1 class="stop-tt__title">
          {{ data.stop.name }}
          <span v-if="data.stop.code" class="stop-tt__code">{{ data.stop.code }}</span>
        </h1>
        <p class="stop-tt__line">
          <LineBadge :line="data.line" size="lg" aria-hidden="true" />
          <span class="visually-hidden">{{
            t('timetable.lineLabel', { line: data.line.short_name })
          }}</span>
          <span class="stop-tt__headsign">→ {{ data.headsign }}</span>
        </p>
      </header>

      <div class="stop-tt__controls no-print">
        <ServiceDatePicker
          :model-value="tt.date.value"
          :today="tt.today.value"
          @update:model-value="tt.setDate"
        />
        <div class="stop-tt__actions">
          <button
            v-if="canSwitchDirection"
            type="button"
            class="button"
            :disabled="switching"
            :aria-busy="switching || undefined"
            @click="switchDirection"
          >
            ⇄ {{ switching ? t('timetable.switchingDirection') : t('timetable.oppositeDirection') }}
          </button>
          <button type="button" class="button" @click="print">
            {{ t('timetable.print') }}
          </button>
        </div>
        <p v-if="switchMessageKey" class="stop-tt__message" role="status">
          {{ t(switchMessageKey) }}
        </p>
      </div>

      <nav class="stop-tt__neighbours no-print" :aria-label="t('timetable.neighbourStops')">
        <RouterLink
          v-if="data.previous_stop"
          :to="tt.stopLink(data.previous_stop.stop_id)"
          class="stop-tt__neighbour"
          rel="prev"
        >
          <span class="stop-tt__neighbour-label">← {{ t('timetable.previousStop') }}</span>
          <span>{{ data.previous_stop.name }}</span>
        </RouterLink>
        <span v-else></span>
        <RouterLink
          v-if="data.next_stop"
          :to="tt.stopLink(data.next_stop.stop_id)"
          class="stop-tt__neighbour stop-tt__neighbour--next"
          rel="next"
        >
          <span class="stop-tt__neighbour-label">{{ t('timetable.nextStop') }} →</span>
          <span>{{ data.next_stop.name }}</span>
        </RouterLink>
      </nav>

      <TimetableGrid
        :timetable="data"
        :today="tt.today.value"
        :now-minutes="tt.nowMinutes.value"
        @select="openTrip"
      />

      <TripDialog
        v-if="selectedTrip && tt.cityId.value"
        :key="`${selectedTrip.tripId}-${selectedTrip.date}`"
        :city="tt.cityId.value"
        :trip-id="selectedTrip.tripId"
        :date="selectedTrip.date"
        :current-stop-id="data.stop.stop_id"
        :stop-link="(stopId, direction, lineId) => tt.stopLink(stopId, direction, lineId)"
        @close="selectedTrip = null"
      />
    </template>
  </section>
</template>

<style scoped>
.stop-tt__crumbs ol {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1);
  margin: 0 0 var(--space-3);
  padding: 0;
  list-style: none;
}

.stop-tt__crumbs li + li::before {
  content: '›';
  margin-right: var(--space-1);
  color: var(--color-text-muted);
}

.stop-tt__header {
  margin-bottom: var(--space-4);
}

.stop-tt__title {
  margin: 0;
}

.stop-tt__code {
  color: var(--color-text-muted);
  font-size: 1rem;
  font-weight: 400;
}

.stop-tt__line {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2) var(--space-3);
  margin: var(--space-2) 0 0;
}

.stop-tt__headsign {
  font-size: 1.25rem;
  font-weight: 600;
}

.stop-tt__controls {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--space-3);
  margin-bottom: var(--space-3);
}

.stop-tt__actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.stop-tt__message {
  flex-basis: 100%;
  margin: 0;
  color: var(--color-warning-text);
}

.stop-tt__neighbours {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-2);
  margin-bottom: var(--space-4);
}

.stop-tt__neighbour {
  display: flex;
  flex-direction: column;
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  text-decoration: none;
  min-width: 0;
  overflow-wrap: anywhere;
}

.stop-tt__neighbour:hover {
  background: var(--color-surface-alt);
}

.stop-tt__neighbour--next {
  text-align: right;
}

.stop-tt__neighbour-label {
  color: var(--color-text-muted);
  font-size: 0.8125rem;
}
</style>
