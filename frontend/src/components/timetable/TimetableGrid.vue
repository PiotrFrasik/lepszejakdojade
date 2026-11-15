<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import { useFormat } from '@/composables/useFormat'
import type {
  DayType,
  ServiceDate,
  StopTimetable,
  TimetableColumn,
  TimetableDeparture,
  TimetableVariant,
} from '@/types/api'
import { serviceDateToDate, serviceMinutes } from '@/utils/serviceDate'

/**
 * Stop timetable grid: hours as rows, minutes next to them, three columns (weekday / Saturday /
 * Sunday & holidays). The column of the selected date's day type is highlighted; when that date
 * is today the next departure is highlighted and past ones dimmed. Minutes carry markers
 * (underline = low-floor, letters = route variants) explained in the legend below.
 */
const props = defineProps<{
  timetable: StopTimetable
  /** Today in the city (for next / past departures). */
  today: ServiceDate
  /** Minutes since midnight now, in the city. */
  nowMinutes: number
}>()

const emit = defineEmits<{ select: [departure: TimetableDeparture, date: ServiceDate] }>()

const { t } = useI18n()
const fmt = useFormat()

const LETTERS = 'abcdefghijklmnopqrstuvwxyz'

/** Variant id → legend letter, in the order the API lists them. */
const variantLetters = computed<Map<string, string>>(() => {
  const map = new Map<string, string>()
  props.timetable.variants.forEach((variant, index) => {
    map.set(variant.id, LETTERS[index] ?? String(index + 1))
  })
  return map
})

function variantLetter(departure: TimetableDeparture): string | null {
  if (!departure.markers.includes('short_turn') && !departure.markers.includes('variant')) {
    return null
  }
  return variantLetters.value.get(departure.variant) ?? '*'
}

function isLowFloor(departure: TimetableDeparture): boolean {
  return departure.markers.includes('low_floor')
}

/** Index of the column to highlight (the selected date's day type). */
const activeIndex = computed<number>(() =>
  props.timetable.columns.findIndex((column) => column.day_type === props.timetable.day_type),
)

/** Next / past only make sense in the highlighted column when the selected date is today. */
const liveColumn = computed<number>(() => {
  const column = props.timetable.columns[activeIndex.value]
  return column && props.timetable.date === props.today && column.date === props.today
    ? activeIndex.value
    : -1
})

function departureMinutes(departure: TimetableDeparture): number {
  return serviceMinutes(departure.time, departure.next_day)
}

/**
 * First departure not yet gone in the live column. Before today's first departure (e.g. just
 * after midnight) the previous service day's after-midnight departures, which this timetable
 * does not contain, may still be due, so no departure is marked as next then.
 */
const nextDeparture = computed<TimetableDeparture | null>(() => {
  const column = props.timetable.columns[liveColumn.value]
  if (!column) return null
  const first = column.hours[0]?.departures[0]
  if (!first || props.nowMinutes < departureMinutes(first)) return null
  for (const hour of column.hours) {
    for (const departure of hour.departures) {
      if (departureMinutes(departure) >= props.nowMinutes) return departure
    }
  }
  return null
})

function isPast(columnIndex: number, departure: TimetableDeparture): boolean {
  return columnIndex === liveColumn.value && departureMinutes(departure) < props.nowMinutes
}

interface Row {
  key: number
  label: string
  cells: TimetableDeparture[][]
}

/** Union of the hours of all columns, in service-day order (hours after midnight last). */
const rows = computed<Row[]>(() => {
  const columns = props.timetable.columns
  const byKey = new Map<number, TimetableDeparture[][]>()
  columns.forEach((column, index) => {
    for (const hour of column.hours) {
      const nextDay = hour.departures[0]?.next_day ?? false
      const key = hour.hour + (nextDay ? 24 : 0)
      const cells = byKey.get(key) ?? columns.map(() => [])
      cells[index] = [...(cells[index] ?? []), ...hour.departures]
      byKey.set(key, cells)
    }
  })
  return [...byKey.entries()]
    .sort(([a], [b]) => a - b)
    .map(([key, cells]) => ({ key, label: String(key % 24).padStart(2, '0'), cells }))
})

const hasAnyDepartures = computed(() => rows.value.length > 0)
const hasLowFloor = computed(() =>
  props.timetable.columns.some((c) => c.hours.some((h) => h.departures.some((d) => isLowFloor(d)))),
)

function dayTypeLabel(dayType: DayType): string {
  return t(`timetable.dayTypes.${dayType}`)
}

function columnDate(column: TimetableColumn): string {
  return fmt.date(serviceDateToDate(column.date))
}

function variantText(variant: TimetableVariant): string {
  return t('timetable.legend.variant', {
    kind: t(`timetable.variantKinds.${variant.kind}`),
    headsign: variant.headsign,
  })
}

function departureLabel(columnIndex: number, departure: TimetableDeparture): string {
  const parts = [
    t('timetable.departureLabel', { time: departure.time, headsign: departure.headsign }),
  ]
  if (isLowFloor(departure)) parts.push(t('timetable.lowFloorVehicle'))
  const variant = props.timetable.variants.find((v) => v.id === departure.variant)
  if (variant && variantLetter(departure)) parts.push(variantText(variant))
  if (departure === nextDeparture.value) parts.push(t('timetable.legend.next'))
  else if (isPast(columnIndex, departure)) parts.push(t('timetable.legend.past'))
  return parts.join(', ')
}
</script>

<template>
  <div class="tt-grid">
    <p v-if="nextDeparture" class="tt-grid__next" role="status">
      {{ t('timetable.nextDeparture') }}: <strong>{{ nextDeparture.time }}</strong> →
      {{ nextDeparture.headsign }}
    </p>

    <p v-if="!hasAnyDepartures" class="tt-grid__empty">{{ t('timetable.noDepartures') }}</p>

    <table v-else class="tt-grid__table">
      <caption class="visually-hidden">
        {{
          t('timetable.tableCaption', {
            line: timetable.line.short_name,
            stop: timetable.stop.name,
            headsign: timetable.headsign,
          })
        }}
      </caption>
      <thead>
        <tr>
          <th scope="col" class="tt-grid__hour-head">{{ t('timetable.hour') }}</th>
          <th
            v-for="(column, index) in timetable.columns"
            :key="column.day_type"
            scope="col"
            class="tt-grid__col-head"
            :class="{ 'tt-grid__active': index === activeIndex }"
          >
            <span class="tt-grid__day">{{ dayTypeLabel(column.day_type) }}</span>
            <span class="tt-grid__date">{{ columnDate(column) }}</span>
            <span v-if="index === activeIndex" class="visually-hidden">
              ({{ t('timetable.selectedDayType') }})
            </span>
            <span v-if="column.hours.length === 0" class="tt-grid__date">
              {{ t('timetable.noService') }}
            </span>
          </th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="row.key">
          <th scope="row" class="tt-grid__hour">{{ row.label }}</th>
          <td
            v-for="(cell, index) in row.cells"
            :key="index"
            class="tt-grid__cell"
            :class="{ 'tt-grid__active': index === activeIndex }"
          >
            <button
              v-for="(departure, position) in cell"
              :key="`${departure.trip_id}-${position}`"
              type="button"
              class="tt-grid__minute"
              :class="{
                'tt-grid__minute--low-floor': isLowFloor(departure),
                'tt-grid__minute--next': departure === nextDeparture,
                'tt-grid__minute--past': isPast(index, departure),
              }"
              :aria-label="departureLabel(index, departure)"
              :title="departureLabel(index, departure)"
              @click="emit('select', departure, timetable.columns[index]!.date)"
            >
              <span class="tt-grid__mm">{{ String(departure.minute).padStart(2, '0') }}</span
              ><sup v-if="variantLetter(departure)" class="tt-grid__letter">{{
                variantLetter(departure)
              }}</sup>
            </button>
          </td>
        </tr>
      </tbody>
    </table>

    <section v-if="hasAnyDepartures" class="tt-grid__legend">
      <h2 class="tt-grid__legend-title">{{ t('timetable.legend.title') }}</h2>
      <ul>
        <li v-if="hasLowFloor">
          <span class="tt-grid__sample tt-grid__minute--low-floor" aria-hidden="true">12</span>
          {{ t('timetable.legend.lowFloor') }}
        </li>
        <li v-for="variant in timetable.variants" :key="variant.id">
          <span class="tt-grid__sample" aria-hidden="true"
            >12<sup>{{ variantLetters.get(variant.id) }}</sup></span
          >
          {{ variantText(variant) }}
        </li>
        <li class="no-print">
          <span class="tt-grid__sample tt-grid__active" aria-hidden="true">&nbsp;</span>
          {{ t('timetable.legend.selectedColumn') }}
        </li>
        <li v-if="nextDeparture" class="no-print">
          <span class="tt-grid__sample tt-grid__minute--next" aria-hidden="true">12</span>
          {{ t('timetable.legend.next') }}
        </li>
        <li class="no-print">{{ t('timetable.legend.clickHint') }}</li>
      </ul>
    </section>
  </div>
</template>

<style scoped>
.tt-grid__next {
  margin: 0 0 var(--space-3);
  padding: var(--space-2) var(--space-3);
  border-left: 4px solid var(--color-primary);
  background: var(--color-surface-alt);
}

.tt-grid__empty {
  color: var(--color-text-muted);
}

.tt-grid__table {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
  font-variant-numeric: tabular-nums;
}

.tt-grid__hour-head {
  width: 2.5rem;
}

.tt-grid__table th,
.tt-grid__table td {
  border: 1px solid var(--color-border);
  vertical-align: top;
}

.tt-grid__col-head {
  padding: var(--space-1);
  text-align: left;
  font-weight: 400;
}

.tt-grid__day {
  display: block;
  font-weight: 700;
  font-size: 0.875rem;
  line-height: 1.2;
}

.tt-grid__date {
  display: block;
  color: var(--color-text-muted);
  font-size: 0.75rem;
}

.tt-grid__hour {
  padding: var(--space-1);
  background: var(--color-surface-alt);
  font-weight: 700;
  text-align: center;
}

.tt-grid__cell {
  padding: 2px;
}

.tt-grid__active {
  background: var(--color-highlight);
}

.tt-grid__minute {
  display: inline-block;
  min-width: 2rem;
  min-height: 1.75rem;
  margin: 1px;
  padding: 0 0.15rem;
  border: 1px solid transparent;
  border-radius: 4px;
  background: none;
  color: inherit;
  font: inherit;
  cursor: pointer;
}

.tt-grid__minute:hover {
  border-color: var(--color-primary);
}

.tt-grid__minute--low-floor .tt-grid__mm,
.tt-grid__sample.tt-grid__minute--low-floor {
  text-decoration: underline;
  text-decoration-thickness: 2px;
  text-underline-offset: 2px;
}

.tt-grid__minute--past {
  color: var(--color-text-muted);
  opacity: 0.6;
}

.tt-grid__minute--next {
  background: var(--color-primary);
  color: var(--color-on-primary);
  font-weight: 700;
}

.tt-grid__letter {
  font-size: 0.7em;
  font-weight: 700;
}

.tt-grid__legend {
  margin-top: var(--space-4);
  font-size: 0.875rem;
}

.tt-grid__legend-title {
  margin: 0 0 var(--space-2);
  font-size: 1rem;
}

.tt-grid__legend ul {
  margin: 0;
  padding: 0;
  list-style: none;
}

.tt-grid__legend li {
  display: flex;
  align-items: baseline;
  gap: var(--space-2);
  margin-bottom: var(--space-1);
}

.tt-grid__sample {
  display: inline-block;
  min-width: 2rem;
  padding: 0 0.15rem;
  border-radius: 4px;
  text-align: center;
  font-variant-numeric: tabular-nums;
}

@media (min-width: 640px) {
  .tt-grid__hour-head {
    width: 3.5rem;
  }

  .tt-grid__day {
    font-size: 1rem;
  }
}

@media print {
  .tt-grid__active,
  .tt-grid__minute--next {
    background: none;
    color: inherit;
  }

  .tt-grid__minute--past {
    opacity: 1;
    color: inherit;
  }

  .tt-grid__minute {
    min-height: 0;
    min-width: 0;
    margin: 0 0.15rem;
  }

  .tt-grid__table th,
  .tt-grid__table td {
    border-color: #000;
  }
}
</style>
