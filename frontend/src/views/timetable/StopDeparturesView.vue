<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import LoadStatus from '@/components/LoadStatus.vue'
import DepartureRow from '@/components/timetable/DepartureRow.vue'
import { useFormat } from '@/composables/useFormat'
import { useStopDepartures } from '@/composables/useStopDepartures'
import { useTimetableRoute } from '@/composables/useTimetableRoute'
import type { StopDeparture } from '@/types/api'
import { hasDeparted } from '@/utils/departures'

/**
 * Departures board of a stop group: next departures of all lines, with live times where the
 * city has realtime data. Refreshes itself every 30 s while the page is visible.
 */
const { t } = useI18n()
const fmt = useFormat()
const tt = useTimetableRoute()

const board = useStopDepartures(() =>
  tt.cityId.value && tt.stopId.value ? { city: tt.cityId.value, stop: tt.stopId.value } : null,
)

const data = computed(() => board.data.value)
/** Live times are shown only when the city has them and the board is not stale (> 5 min old). */
const showLive = computed(() => Boolean(data.value?.realtime_available) && !board.stale.value)
/** Rows that have not left yet by the server-based clock (matters when refreshes fail). */
const departures = computed<StopDeparture[]>(() =>
  (data.value?.departures ?? []).filter(
    (departure) => !hasDeparted(departure, showLive.value, board.nowMs.value),
  ),
)
const updatedAt = computed(() => (data.value ? fmt.timeSeconds(data.value.generated_at) : ''))

function rowKey(departure: StopDeparture): string {
  return `${departure.trip_id}|${departure.platform_id}|${departure.scheduled}`
}
</script>

<template>
  <section class="page stop-board">
    <nav class="stop-board__crumbs" :aria-label="t('timetable.breadcrumbs')">
      <ol>
        <li>
          <RouterLink :to="{ name: 'timetable' }">{{ t('timetable.title') }}</RouterLink>
        </li>
      </ol>
    </nav>

    <LoadStatus
      v-if="!data"
      :loading="board.status.value === 'loading'"
      :error="board.error.value"
      :not-found-text="t('timetable.departures.notFound')"
      :loading-text="t('timetable.departures.loading')"
      @retry="board.reload"
    />

    <template v-if="data">
      <header class="stop-board__header">
        <h1 class="stop-board__title">{{ data.stop.name }}</h1>
        <p class="stop-board__subtitle">{{ t('timetable.departures.title') }}</p>
      </header>

      <div class="stop-board__toolbar">
        <p class="stop-board__updated">
          {{ t('timetable.departures.updated', { time: updatedAt }) }}
        </p>
        <button
          type="button"
          class="button"
          :disabled="board.refreshing.value"
          :aria-busy="board.refreshing.value || undefined"
          @click="board.reload"
        >
          {{
            board.refreshing.value
              ? t('timetable.departures.refreshing')
              : t('timetable.departures.refresh')
          }}
        </button>
      </div>

      <p v-if="!showLive" class="stop-board__note" data-testid="no-realtime">
        {{ t('timetable.departures.noRealtime') }}
      </p>

      <!-- Announced once when a refresh fails; successful auto-refreshes stay silent. -->
      <p class="stop-board__problem-region" role="status">
        <span v-if="board.refreshError.value" class="stop-board__problem">{{
          t('timetable.departures.refreshFailed', { time: updatedAt })
        }}</span>
      </p>

      <p v-if="departures.length === 0" class="stop-board__empty">
        {{ t('timetable.departures.empty') }}
      </p>
      <ol
        v-else
        class="stop-board__list"
        :aria-label="t('timetable.departures.listLabel', { stop: data.stop.name })"
      >
        <DepartureRow
          v-for="departure in departures"
          :key="rowKey(departure)"
          :departure="departure"
          :realtime-available="showLive"
          :now-ms="board.nowMs.value"
        />
      </ol>
    </template>
  </section>
</template>

<style scoped>
.stop-board__crumbs ol {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1);
  margin: 0 0 var(--space-3);
  padding: 0;
  list-style: none;
}

.stop-board__header {
  margin-bottom: var(--space-3);
}

.stop-board__title {
  margin: 0;
  overflow-wrap: anywhere;
}

.stop-board__subtitle {
  margin: var(--space-1) 0 0;
  color: var(--color-text-muted);
}

.stop-board__toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2) var(--space-3);
  margin-bottom: var(--space-3);
}

.stop-board__updated {
  margin: 0;
  color: var(--color-text-muted);
  font-size: 0.875rem;
  font-variant-numeric: tabular-nums;
}

.stop-board__note {
  margin: 0 0 var(--space-3);
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  background: var(--color-surface-alt);
  color: var(--color-text-muted);
}

.stop-board__problem-region {
  margin: 0;
}

.stop-board__problem {
  display: block;
  margin-bottom: var(--space-3);
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--color-warning-text);
  border-radius: var(--radius);
  background: var(--color-highlight);
  color: var(--color-warning-text);
}

.stop-board__empty {
  color: var(--color-text-muted);
}

.stop-board__list {
  margin: 0;
  padding: 0;
  list-style: none;
  border-top: 1px solid var(--color-border);
}
</style>
