<script setup lang="ts">
import { computed, nextTick, onMounted, useId, useTemplateRef } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, type RouteLocationRaw } from 'vue-router'

import { getTrip } from '@/api/client'
import LoadStatus from '@/components/LoadStatus.vue'
import LineBadge from '@/components/timetable/LineBadge.vue'
import { useApiResource } from '@/composables/useApiResource'
import { useFormat } from '@/composables/useFormat'
import type { CityId, DirectionId, LineId, ServiceDate, StopId, TripId } from '@/types/api'
import { serviceDateToDate } from '@/utils/serviceDate'

/**
 * Whole trip after clicking a minute: times at every stop, the clicked stop highlighted and
 * earlier stops dimmed. A modal `<dialog>` (Escape closes it, focus returns to the minute).
 */
const props = defineProps<{
  city: CityId
  tripId: TripId
  date: ServiceDate
  /** Stop the user came from (highlighted). */
  currentStopId: StopId
  stopLink: (stopId: StopId, direction: DirectionId, lineId: LineId) => RouteLocationRaw
}>()

const emit = defineEmits<{ close: [] }>()
const { t } = useI18n()
const fmt = useFormat()
const titleId = useId()
const dialog = useTemplateRef<HTMLDialogElement>('dialog')

const trip = useApiResource(
  () => ({ city: props.city, trip: props.tripId, date: props.date }),
  (key, signal) => getTrip(key.city, key.trip, key.date, signal),
)

const currentIndex = computed(
  () => trip.data.value?.stops.findIndex((stop) => stop.stop_id === props.currentStopId) ?? -1,
)

function time(value: string | null): string {
  return value ? fmt.time(value) : '–'
}

onMounted(async () => {
  await nextTick()
  const el = dialog.value
  if (!el) return
  if (typeof el.showModal === 'function') {
    try {
      el.showModal()
    } catch {
      el.setAttribute('open', '')
    }
  } else {
    el.setAttribute('open', '')
  }
  el.querySelector<HTMLElement>('.trip-dialog__close')?.focus()
})

function close(): void {
  dialog.value?.close?.()
  emit('close')
}

/** Clicking the backdrop (outside the dialog box) closes it. */
function onClick(event: MouseEvent): void {
  if (event.target === dialog.value) close()
}
</script>

<template>
  <dialog
    ref="dialog"
    class="trip-dialog"
    :aria-labelledby="titleId"
    @cancel.prevent="close"
    @click="onClick"
  >
    <div class="trip-dialog__box">
      <header class="trip-dialog__header">
        <h2 :id="titleId" class="trip-dialog__title">
          <template v-if="trip.data.value">
            <LineBadge :line="trip.data.value.line" />
            <span>→ {{ trip.data.value.headsign }}</span>
          </template>
          <template v-else>{{ t('timetable.trip.title') }}</template>
        </h2>
        <button
          type="button"
          class="button trip-dialog__close"
          :aria-label="t('timetable.trip.close')"
          @click="close"
        >
          ✕
        </button>
      </header>

      <LoadStatus
        :loading="trip.status.value === 'loading'"
        :error="trip.error.value"
        :not-found-text="t('timetable.trip.notFound')"
        @retry="trip.reload"
      />

      <template v-if="trip.data.value">
        <p class="trip-dialog__meta">
          {{ fmt.dateLong(serviceDateToDate(trip.data.value.date)) }}
          <template v-if="trip.data.value.wheelchair_accessible === true">
            · ♿ {{ t('timetable.trip.accessible') }}
          </template>
        </p>
        <ol class="trip-dialog__stops">
          <li
            v-for="(stop, index) in trip.data.value.stops"
            :key="`${stop.stop_id}-${index}`"
            class="trip-dialog__stop"
            :class="{
              'trip-dialog__stop--before': currentIndex >= 0 && index < currentIndex,
              'trip-dialog__stop--current': index === currentIndex,
            }"
            :aria-current="index === currentIndex ? 'location' : undefined"
          >
            <span class="trip-dialog__time">{{ time(stop.departure ?? stop.arrival) }}</span>
            <RouterLink
              :to="stopLink(stop.stop_id, trip.data.value.direction, trip.data.value.line.id)"
              class="trip-dialog__name"
              @click="close"
              >{{ stop.name }}</RouterLink
            >
          </li>
        </ol>
      </template>
    </div>
  </dialog>
</template>

<style scoped>
.trip-dialog {
  width: min(32rem, calc(100vw - 1rem));
  max-height: calc(100dvh - 2rem);
  padding: 0;
  border: 0;
  border-radius: var(--radius);
  box-shadow: 0 8px 32px rgb(0 0 0 / 30%);
}

.trip-dialog::backdrop {
  background: rgb(0 0 0 / 45%);
}

.trip-dialog__box {
  padding: var(--space-4);
}

.trip-dialog__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-3);
}

.trip-dialog__title {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
  margin: 0;
  font-size: 1.125rem;
}

.trip-dialog__close {
  flex: none;
  min-width: 2.5rem;
}

.trip-dialog__meta {
  color: var(--color-text-muted);
  font-size: 0.875rem;
}

.trip-dialog__stops {
  margin: 0;
  padding: 0;
  list-style: none;
}

.trip-dialog__stop {
  display: grid;
  grid-template-columns: 3.5rem 1fr;
  gap: var(--space-2);
  padding: var(--space-1) 0;
  border-bottom: 1px solid var(--color-border);
  font-variant-numeric: tabular-nums;
}

.trip-dialog__stop--before {
  color: var(--color-text-muted);
}

.trip-dialog__stop--before .trip-dialog__name {
  color: var(--color-text-muted);
}

.trip-dialog__stop--current {
  background: var(--color-highlight);
  font-weight: 700;
}

.trip-dialog__time {
  padding-left: var(--space-1);
}

.trip-dialog__name {
  color: var(--color-text);
}
</style>
