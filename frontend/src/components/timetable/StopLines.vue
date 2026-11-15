<script setup lang="ts">
import { computed, ref, useId } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, type RouteLocationRaw } from 'vue-router'

import LineBadge from '@/components/timetable/LineBadge.vue'
import VehicleTypeTabs from '@/components/timetable/VehicleTypeTabs.vue'
import type { StopLine, StopLineDirection, VehicleType } from '@/types/api'

/**
 * "Lines at this stop": vehicle type tabs (only the types present at the stop) and, per tab, the
 * lines with their directions. Each direction links to the stop timetable of that line at the
 * platform it departs from.
 */
const props = withDefaults(
  defineProps<{
    lines: readonly StopLine[]
    /** Preferred tab order (the city's vehicle types); types not listed come after, as served. */
    typeOrder?: readonly VehicleType[]
  }>(),
  { typeOrder: () => [] },
)

const { t } = useI18n()
const idPrefix = useId()
const panelId = `${idPrefix}-panel`

const types = computed<VehicleType[]>(() => {
  const present = new Set(props.lines.map((entry) => entry.line.vehicle_type))
  const ordered = props.typeOrder.filter((type) => present.has(type))
  for (const type of present) if (!ordered.includes(type)) ordered.push(type)
  return ordered
})

const chosen = ref<VehicleType | null>(null)
/** The chosen tab while it still exists, otherwise the first one. */
const selectedType = computed<VehicleType | null>(() =>
  chosen.value && types.value.includes(chosen.value) ? chosen.value : (types.value[0] ?? null),
)

const shownLines = computed<StopLine[]>(() =>
  props.lines.filter((entry) => entry.line.vehicle_type === selectedType.value),
)

function timetableLink(entry: StopLine, direction: StopLineDirection): RouteLocationRaw {
  return {
    name: 'timetable-stop',
    params: { lineId: entry.line.id, stopId: direction.platform_id },
    query: direction.direction === 0 ? {} : { direction: String(direction.direction) },
  }
}
</script>

<template>
  <div class="stop-lines">
    <VehicleTypeTabs
      v-if="selectedType"
      :types="types"
      :model-value="selectedType"
      :panel-id="panelId"
      :id-prefix="idPrefix"
      @update:model-value="chosen = $event"
    />
    <div
      v-if="selectedType"
      :id="panelId"
      class="stop-lines__panel"
      role="tabpanel"
      :aria-labelledby="`${idPrefix}-${selectedType}`"
    >
      <ul class="stop-lines__list">
        <li
          v-for="entry in shownLines"
          :key="entry.line.id"
          class="stop-lines__line"
          data-testid="stop-line"
        >
          <span class="stop-lines__badge">
            <LineBadge :line="entry.line" aria-hidden="true" />
            <span class="visually-hidden">{{
              t('timetable.lineLabel', { line: entry.line.short_name })
            }}</span>
          </span>
          <ul class="stop-lines__directions">
            <li v-for="direction in entry.directions" :key="direction.direction">
              <RouterLink
                class="stop-lines__direction"
                :to="timetableLink(entry, direction)"
                data-testid="stop-line-direction"
              >
                <span aria-hidden="true" class="stop-lines__arrow">→</span>
                <span class="visually-hidden">{{
                  t('timetable.stopLines.directionPrefix', { line: entry.line.short_name })
                }}</span>
                {{ direction.headsign }}
              </RouterLink>
            </li>
          </ul>
        </li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
.stop-lines__panel {
  padding-top: var(--space-2);
}

.stop-lines__list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.stop-lines__line {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
  padding: var(--space-2) 0;
  border-bottom: 1px solid var(--color-border);
}

.stop-lines__badge {
  flex: 0 0 3.5rem;
  padding-top: var(--space-2);
}

.stop-lines__directions {
  flex: 1 1 auto;
  min-width: 0;
  margin: 0;
  padding: 0;
  list-style: none;
}

.stop-lines__direction {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-height: 2.75rem;
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius);
  color: var(--color-link);
  overflow-wrap: anywhere;
}

.stop-lines__direction:hover {
  background: var(--color-surface-alt);
}

.stop-lines__arrow {
  flex: 0 0 auto;
  color: var(--color-text-muted);
}
</style>
