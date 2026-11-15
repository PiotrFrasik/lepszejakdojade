<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import ModeIcon from '@/components/journey/ModeIcon.vue'
import LineBadge from '@/components/timetable/LineBadge.vue'
import { useFormat } from '@/composables/useFormat'
import type { Itinerary, JourneyLeg } from '@/types/api'

/**
 * One connection of the results list. The summary button selects it (drawn on the map) and
 * toggles the leg-by-leg details.
 */
const props = withDefaults(
  defineProps<{
    itinerary: Itinerary
    index: number
    selected: boolean
    expanded: boolean
    /** Prefix of element ids, unique per list (the chat shows cards next to the results). */
    idPrefix?: string
  }>(),
  { idPrefix: 'itinerary' },
)

const emit = defineEmits<{ toggle: [] }>()

const { t } = useI18n()
const fmt = useFormat()

const detailsId = computed(() => `${props.idPrefix}-${props.index}-details`)

const transfersText = computed(() =>
  props.itinerary.transfers > 0
    ? t('journey.itinerary.transfers', { count: props.itinerary.transfers })
    : t('journey.itinerary.noTransfers'),
)

const summaryLabel = computed(() =>
  t('journey.itinerary.label', {
    index: props.index + 1,
    start: fmt.time(props.itinerary.start),
    end: fmt.time(props.itinerary.end),
    duration: fmt.duration(props.itinerary.duration),
  }),
)

function placeName(place: JourneyLeg['from']): string {
  return place.name || t('journey.leg.unnamed')
}

function walkText(leg: JourneyLeg): string {
  return t('journey.leg.walk', {
    distance: fmt.distance(leg.distance),
    duration: fmt.duration(leg.duration),
  })
}

const lastLeg = computed(() => props.itinerary.legs[props.itinerary.legs.length - 1] ?? null)
</script>

<template>
  <article
    class="itinerary"
    :class="{ 'itinerary--selected': selected }"
    :aria-label="summaryLabel"
  >
    <button
      type="button"
      class="itinerary__summary"
      :aria-expanded="expanded"
      :aria-controls="detailsId"
      @click="emit('toggle')"
    >
      <span class="itinerary__top">
        <span class="itinerary__times">
          {{
            t('journey.itinerary.times', {
              start: fmt.time(itinerary.start),
              end: fmt.time(itinerary.end),
            })
          }}
        </span>
        <span class="itinerary__duration">{{ fmt.duration(itinerary.duration) }}</span>
      </span>
      <span class="itinerary__chips">
        <template v-for="(leg, i) in itinerary.legs" :key="i">
          <span v-if="i > 0" class="itinerary__sep" aria-hidden="true">›</span>
          <LineBadge v-if="leg.line" :line="leg.line" size="sm" />
          <span v-else-if="leg.mode === 'walk'" class="itinerary__walk-chip">
            <ModeIcon mode="walk" />
            <span>{{ fmt.duration(leg.duration) }}</span>
          </span>
          <span v-else class="itinerary__walk-chip">
            <ModeIcon :mode="leg.mode" />
            <span>{{ t(`journey.leg.modes.${leg.mode}`) }}</span>
          </span>
        </template>
      </span>
      <span class="itinerary__meta">
        <span>{{ transfersText }}</span>
        <span>{{
          t('journey.itinerary.walking', { distance: fmt.distance(itinerary.walk_distance) })
        }}</span>
      </span>
      <span class="visually-hidden">{{
        expanded ? t('journey.itinerary.hideDetails') : t('journey.itinerary.showDetails')
      }}</span>
    </button>

    <ol v-if="expanded" :id="detailsId" class="itinerary__legs">
      <li
        v-for="(leg, i) in itinerary.legs"
        :key="i"
        class="itinerary__leg"
        :class="`itinerary__leg--${leg.mode}`"
        :style="leg.line ? { '--leg-colour': leg.line.colour } : undefined"
      >
        <div class="itinerary__leg-head">
          <time class="itinerary__leg-time" :datetime="leg.start">{{ fmt.time(leg.start) }}</time>
          <span class="itinerary__leg-place">{{ placeName(leg.from) }}</span>
        </div>
        <div class="itinerary__leg-body">
          <template v-if="leg.mode === 'walk'">
            <ModeIcon mode="walk" />
            <span>{{ walkText(leg) }}</span>
          </template>
          <template v-else>
            <RouterLink
              v-if="leg.line"
              class="itinerary__line-link"
              :to="{ name: 'timetable-line', params: { lineId: leg.line.id } }"
              :aria-label="t('journey.leg.lineLink', { line: leg.line.short_name })"
            >
              <LineBadge :line="leg.line" size="sm" />
            </RouterLink>
            <ModeIcon v-else :mode="leg.mode" />
            <span>
              {{ t(`journey.leg.modes.${leg.mode}`) }}
              <template v-if="leg.headsign">
                · {{ t('journey.leg.towards', { headsign: leg.headsign }) }}</template
              >
              · {{ fmt.duration(leg.duration) }}
            </span>
          </template>
        </div>
        <details v-if="leg.intermediate_stops.length > 0" class="itinerary__stops">
          <summary>
            {{ t('journey.leg.stops', { count: leg.intermediate_stops.length }) }}
          </summary>
          <ul>
            <li v-for="stop in leg.intermediate_stops" :key="stop.stop_id">{{ stop.name }}</li>
          </ul>
        </details>
      </li>
      <li v-if="lastLeg" class="itinerary__leg itinerary__leg--end">
        <div class="itinerary__leg-head">
          <time class="itinerary__leg-time" :datetime="lastLeg.end">{{
            fmt.time(lastLeg.end)
          }}</time>
          <span class="itinerary__leg-place">{{ placeName(lastLeg.to) }}</span>
        </div>
      </li>
    </ol>
  </article>
</template>

<style scoped>
.itinerary {
  border: 1px solid var(--color-border);
  border-radius: 12px;
  background: var(--color-surface);
  overflow: hidden;
}

.itinerary--selected {
  border-color: var(--color-primary);
  box-shadow: inset 4px 0 0 var(--color-primary);
}

.itinerary__summary {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  width: 100%;
  padding: var(--space-3);
  border: 0;
  background: none;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.itinerary__summary:hover {
  background: var(--color-surface-alt);
}

.itinerary__top {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--space-2);
}

.itinerary__times {
  font-size: 1.125rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.itinerary__duration {
  font-weight: 600;
  white-space: nowrap;
}

.itinerary__chips {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-1);
}

.itinerary__sep {
  color: var(--color-text-muted);
}

.itinerary__walk-chip {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 0 var(--space-1);
  border-radius: 4px;
  background: var(--color-surface-alt);
  color: var(--color-text-muted);
  font-size: 0.75rem;
  line-height: 1.3;
}

.itinerary__meta {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1) var(--space-3);
  color: var(--color-text-muted);
  font-size: 0.8125rem;
}

.itinerary__legs {
  margin: 0;
  padding: 0 var(--space-3) var(--space-3);
  list-style: none;
}

.itinerary__leg {
  --leg-colour: var(--color-text-muted);

  position: relative;
  padding: 0 0 var(--space-3) 4.25rem;
}

.itinerary__leg::before {
  content: '';
  position: absolute;
  top: 1.25rem;
  bottom: 0;
  left: 3.35rem;
  width: 4px;
  border-radius: 2px;
  background: var(--leg-colour);
}

.itinerary__leg--walk::before {
  width: 0;
  border-left: 3px dotted var(--color-text-muted);
  background: none;
}

.itinerary__leg--end::before {
  display: none;
}

.itinerary__leg-head {
  display: flex;
  align-items: baseline;
  gap: var(--space-2);
  margin-left: -4.25rem;
}

.itinerary__leg-time {
  flex: none;
  width: 3rem;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.itinerary__leg-place {
  padding-left: 1rem;
  font-weight: 600;
}

.itinerary__leg-body {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-1) 0;
  color: var(--color-text-muted);
  font-size: 0.875rem;
}

.itinerary__line-link {
  display: inline-flex;
  text-decoration: none;
}

.itinerary__stops {
  font-size: 0.8125rem;
  color: var(--color-text-muted);
}

.itinerary__stops summary {
  cursor: pointer;
}

.itinerary__stops ul {
  margin: var(--space-1) 0 0;
  padding-left: var(--space-4);
}
</style>
