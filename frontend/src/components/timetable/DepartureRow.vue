<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import { useFormat } from '@/composables/useFormat'
import type { StopDeparture } from '@/types/api'
import { departureTiming, minutesUntil } from '@/utils/departures'

/**
 * One row of the stop departures board: line tile, headsign, platform and the time column.
 * Live state is always given in text (badges and visually hidden labels), never by colour only.
 */
const props = defineProps<{
  departure: StopDeparture
  realtimeAvailable: boolean
  /** Current time (epoch ms) used for the countdown. */
  nowMs: number
}>()

const { t } = useI18n()
const fmt = useFormat()

const timing = computed(() => departureTiming(props.departure, props.realtimeAvailable))
const isLive = computed(() => ['on_time', 'late', 'early'].includes(timing.value.kind))
const isCanceled = computed(() => timing.value.kind === 'canceled')
/** Expected time differs from the timetable by at least a minute. */
const isShifted = computed(() => timing.value.kind === 'late' || timing.value.kind === 'early')
const shiftMinutes = computed(() =>
  timing.value.kind === 'late' || timing.value.kind === 'early' ? timing.value.minutes : 0,
)

const scheduledTime = computed(() => fmt.time(props.departure.scheduled))
const expectedTime = computed(() =>
  props.departure.expected ? fmt.time(props.departure.expected) : scheduledTime.value,
)
const mainTime = computed(() => (isShifted.value ? expectedTime.value : scheduledTime.value))

const countdown = computed(() =>
  minutesUntil(props.departure, props.realtimeAvailable, props.nowMs),
)
</script>

<template>
  <li
    class="departure"
    :class="{ 'departure--canceled': isCanceled, 'departure--live': isLive }"
    data-testid="departure-row"
  >
    <span
      class="departure__tile"
      :style="{ backgroundColor: departure.line.colour, color: departure.line.text_colour }"
      aria-hidden="true"
      >{{ departure.line.short_name }}</span
    >
    <span class="visually-hidden">{{
      t('timetable.lineLabel', { line: departure.line.short_name })
    }}</span>

    <div class="departure__main">
      <span class="departure__headsign"
        ><span aria-hidden="true">→ </span
        ><span class="visually-hidden">{{ t('timetable.departures.towards') }} </span
        >{{ departure.headsign }}</span
      >
      <span v-if="departure.platform_code" class="departure__platform">{{
        t('timetable.departures.platform', { code: departure.platform_code })
      }}</span>
    </div>

    <div class="departure__time">
      <span v-if="isCanceled" class="departure__badge departure__badge--canceled">{{
        t('timetable.departures.canceled')
      }}</span>
      <template v-else-if="countdown !== null">
        <span class="departure__countdown" aria-hidden="true">{{
          countdown === 0
            ? t('timetable.departures.now')
            : t('timetable.departures.inMinutes', { minutes: countdown })
        }}</span>
        <span class="visually-hidden">{{
          countdown === 0
            ? t('timetable.departures.now')
            : t('timetable.departures.inMinutesLong', { minutes: countdown }, countdown)
        }}</span>
      </template>

      <span class="departure__clock">
        <span
          class="departure__main-time"
          :class="{ 'departure__main-time--canceled': isCanceled }"
        >
          <span v-if="isShifted" class="visually-hidden"
            >{{ t('timetable.departures.expectedTime') }}
          </span>
          <span v-else-if="isCanceled" class="visually-hidden"
            >{{ t('timetable.departures.scheduledTime') }} </span
          >{{ mainTime }}</span
        >
        <s v-if="isShifted" class="departure__scheduled"
          ><span class="visually-hidden">{{ t('timetable.departures.scheduledTime') }} </span
          >{{ scheduledTime }}</s
        >
      </span>

      <span v-if="isLive" class="departure__status">
        <span
          v-if="timing.kind === 'late'"
          class="departure__badge departure__badge--late"
          aria-hidden="true"
          >{{ t('timetable.departures.late', { minutes: shiftMinutes }) }}</span
        >
        <span
          v-else-if="timing.kind === 'early'"
          class="departure__badge departure__badge--early"
          aria-hidden="true"
          >{{ t('timetable.departures.early', { minutes: shiftMinutes }) }}</span
        >
        <span v-else class="departure__badge departure__badge--on-time">{{
          t('timetable.departures.onTime')
        }}</span>
        <span v-if="timing.kind === 'late'" class="visually-hidden">{{
          t('timetable.departures.lateLong', { minutes: shiftMinutes }, shiftMinutes)
        }}</span>
        <span v-else-if="timing.kind === 'early'" class="visually-hidden">{{
          t('timetable.departures.earlyLong', { minutes: shiftMinutes }, shiftMinutes)
        }}</span>
        <span class="departure__live"
          ><span class="departure__live-dot" aria-hidden="true"></span
          >{{ t('timetable.departures.live') }}</span
        >
      </span>
    </div>
  </li>
</template>

<style scoped>
.departure {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: var(--space-2) var(--space-3);
  padding: var(--space-3) var(--space-2);
  border-bottom: 1px solid var(--color-border);
}

/* Same look as the line tiles of the timetable browser. */
.departure__tile {
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 3rem;
  min-height: 2.5rem;
  padding: var(--space-1);
  border-radius: var(--radius);
  font-size: 1.125rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  box-shadow: inset 0 0 0 1px rgb(0 0 0 / 12%);
}

.departure__main {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.departure__headsign {
  font-weight: 600;
  overflow-wrap: anywhere;
}

.departure__platform {
  color: var(--color-text-muted);
  font-size: 0.8125rem;
}

.departure__time {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 2px;
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.departure__countdown {
  font-weight: 700;
  color: var(--color-primary);
}

.departure__clock {
  display: flex;
  align-items: baseline;
  gap: var(--space-1);
}

.departure__main-time {
  font-size: 1.125rem;
  font-weight: 700;
}

.departure__scheduled {
  color: var(--color-text-muted);
  font-size: 0.875rem;
}

.departure__status {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: var(--space-1);
}

.departure__badge {
  padding: 0 0.4em;
  border-radius: 999px;
  font-size: 0.75rem;
  font-weight: 700;
  line-height: 1.5;
  white-space: nowrap;
}

.departure__badge--late {
  background: var(--color-danger-surface);
  color: var(--color-danger);
  box-shadow: inset 0 0 0 1px var(--color-danger);
}

.departure__badge--early {
  background: var(--color-highlight);
  color: var(--color-warning-text);
  box-shadow: inset 0 0 0 1px var(--color-warning-text);
}

.departure__badge--on-time {
  background: var(--color-success-surface);
  color: var(--color-success-text);
  box-shadow: inset 0 0 0 1px var(--color-success-text);
}

.departure__badge--canceled {
  background: var(--color-text-muted);
  color: var(--color-surface);
}

.departure__live {
  display: inline-flex;
  align-items: center;
  gap: 0.25em;
  color: var(--color-success-text);
  font-size: 0.75rem;
  font-weight: 600;
}

.departure__live-dot {
  width: 0.5rem;
  height: 0.5rem;
  border-radius: 50%;
  background: var(--color-success);
  animation: departure-pulse 2s ease-in-out infinite;
}

.departure--canceled .departure__tile,
.departure--canceled .departure__main {
  opacity: 0.55;
}

.departure--canceled .departure__headsign,
.departure__main-time--canceled {
  text-decoration: line-through;
}

.departure__main-time--canceled {
  color: var(--color-text-muted);
}

@keyframes departure-pulse {
  50% {
    opacity: 0.35;
  }
}

@media (prefers-reduced-motion: reduce) {
  .departure__live-dot {
    animation: none;
  }
}
</style>
