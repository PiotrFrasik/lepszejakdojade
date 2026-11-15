<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, type RouteLocationRaw } from 'vue-router'

import LineBadge from '@/components/timetable/LineBadge.vue'
import type { LineRoute, RouteVariant, StopId, VariantKind } from '@/types/api'

/**
 * Vertical line diagram: stops connected by a line in the line's colour, transfer line chips per
 * stop, stops served only by some trips marked, and the ends of route variants (short turns,
 * depot runs) marked at the stops they affect. Each stop links to its timetable.
 */
const props = defineProps<{
  route: LineRoute
  /** Builds the link to a stop's timetable. */
  stopLink: (stopId: StopId) => RouteLocationRaw
  highlightedStopId?: StopId | null
}>()

const { t } = useI18n()

interface VariantMark {
  key: string
  text: string
}

const mainVariant = computed<RouteVariant | undefined>(
  () => props.route.variants.find((v) => v.kind === 'main') ?? props.route.variants[0],
)

function kindLabel(kind: VariantKind): string {
  if (kind === 'short_turn') return t('timetable.variantKinds.short_turn')
  if (kind === 'depot') return t('timetable.variantKinds.depot')
  return t('timetable.variantKinds.other')
}

/** Marks where a non-main variant starts or ends somewhere other than the main variant. */
const marksByStop = computed<Map<StopId, VariantMark[]>>(() => {
  const marks = new Map<StopId, VariantMark[]>()
  const main = mainVariant.value
  const mainFirst = main?.stop_ids[0]
  const mainLast = main?.stop_ids[main.stop_ids.length - 1]
  const add = (stopId: StopId, mark: VariantMark): void => {
    const list = marks.get(stopId) ?? []
    list.push(mark)
    marks.set(stopId, list)
  }
  for (const variant of props.route.variants) {
    if (variant === main || variant.stop_ids.length === 0) continue
    const first = variant.stop_ids[0]!
    const last = variant.stop_ids[variant.stop_ids.length - 1]!
    const kind = kindLabel(variant.kind)
    if (first !== mainFirst) {
      add(first, {
        key: `${variant.id}-start`,
        text: t('timetable.variantStartsHere', { kind, headsign: variant.headsign }),
      })
    }
    if (last !== mainLast) {
      add(last, {
        key: `${variant.id}-end`,
        text: t('timetable.variantEndsHere', { kind, headsign: variant.headsign }),
      })
    }
  }
  return marks
})
</script>

<template>
  <ol class="line-diagram" :style="{ '--line-colour': route.line.colour }">
    <li
      v-for="(stop, index) in route.stops"
      :key="`${stop.stop_id}-${index}`"
      class="line-diagram__stop"
      :class="{
        'line-diagram__stop--variant': stop.variant_only,
        'line-diagram__stop--current': stop.stop_id === highlightedStopId,
      }"
    >
      <span class="line-diagram__rail" aria-hidden="true"
        ><span class="line-diagram__dot"></span
      ></span>
      <div class="line-diagram__body">
        <RouterLink
          :to="stopLink(stop.stop_id)"
          class="line-diagram__name"
          :aria-current="stop.stop_id === highlightedStopId ? 'location' : undefined"
        >
          {{ stop.name }}
          <span v-if="stop.code" class="line-diagram__code">{{ stop.code }}</span>
        </RouterLink>
        <span
          v-if="stop.wheelchair_boarding === true"
          class="line-diagram__icon"
          :title="t('timetable.wheelchairBoarding')"
          >♿<span class="visually-hidden">{{ t('timetable.wheelchairBoarding') }}</span></span
        >
        <span v-if="stop.variant_only" class="line-diagram__tag">
          {{ t('timetable.variantOnlyStop') }}
        </span>
        <ul v-if="marksByStop.get(stop.stop_id)" class="line-diagram__marks">
          <li v-for="mark in marksByStop.get(stop.stop_id)" :key="mark.key">{{ mark.text }}</li>
        </ul>
        <div v-if="stop.transfers.length" class="line-diagram__transfers">
          <span class="visually-hidden">{{ t('timetable.transfers') }}:</span>
          <RouterLink
            v-for="transfer in stop.transfers"
            :key="transfer.id"
            :to="{ name: 'timetable-line', params: { lineId: transfer.id } }"
            class="line-diagram__transfer"
            :aria-label="t('timetable.lineLabel', { line: transfer.short_name })"
          >
            <LineBadge :line="transfer" size="sm" />
          </RouterLink>
        </div>
      </div>
    </li>
  </ol>
</template>

<style scoped>
.line-diagram {
  margin: 0;
  padding: 0;
  list-style: none;
}

.line-diagram__stop {
  display: grid;
  grid-template-columns: 1.75rem 1fr;
  column-gap: var(--space-2);
  min-height: 3rem;
}

.line-diagram__rail {
  position: relative;
  display: flex;
  justify-content: center;
}

.line-diagram__rail::before {
  content: '';
  position: absolute;
  top: 0;
  bottom: 0;
  left: 50%;
  width: 6px;
  transform: translateX(-50%);
  background: var(--line-colour);
  print-color-adjust: exact;
  -webkit-print-color-adjust: exact;
}

.line-diagram__stop:first-child .line-diagram__rail::before {
  top: 1.1rem;
}

.line-diagram__stop:last-child .line-diagram__rail::before {
  bottom: calc(100% - 1.1rem);
}

.line-diagram__dot {
  position: relative;
  width: 1rem;
  height: 1rem;
  margin-top: 0.6rem;
  border: 3px solid var(--line-colour);
  border-radius: 50%;
  background: var(--color-surface);
}

.line-diagram__stop--variant .line-diagram__dot {
  border-style: dashed;
  border-color: var(--color-text-muted);
}

.line-diagram__stop--current .line-diagram__dot {
  background: var(--line-colour);
  box-shadow: 0 0 0 3px var(--color-surface);
}

.line-diagram__body {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--space-1) var(--space-2);
  padding: var(--space-2) 0;
  min-width: 0;
}

.line-diagram__name {
  font-weight: 600;
  color: var(--color-text);
  text-decoration: none;
  padding: 0.125rem 0;
}

.line-diagram__name:hover {
  text-decoration: underline;
  color: var(--color-link);
}

.line-diagram__stop--current .line-diagram__name {
  color: var(--color-primary);
}

.line-diagram__stop--variant .line-diagram__name {
  font-weight: 400;
  font-style: italic;
}

.line-diagram__code {
  color: var(--color-text-muted);
  font-weight: 400;
  font-size: 0.8125rem;
}

.line-diagram__icon {
  font-size: 0.875rem;
}

.line-diagram__tag {
  padding: 0 var(--space-1);
  border: 1px dashed var(--color-text-muted);
  border-radius: 4px;
  color: var(--color-text-muted);
  font-size: 0.75rem;
}

.line-diagram__marks {
  flex-basis: 100%;
  margin: 0;
  padding: 0;
  list-style: none;
  color: var(--color-warning-text);
  font-size: 0.8125rem;
}

.line-diagram__marks li::before {
  content: '↳ ';
}

.line-diagram__transfers {
  display: flex;
  flex-basis: 100%;
  flex-wrap: wrap;
  gap: var(--space-1);
}

.line-diagram__transfer {
  text-decoration: none;
  border-radius: 4px;
}
</style>
