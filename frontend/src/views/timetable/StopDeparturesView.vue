<script setup lang="ts">
import { computed, useId } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import { ApiError } from '@/api/client'
import LoadStatus from '@/components/LoadStatus.vue'
import DepartureRow from '@/components/timetable/DepartureRow.vue'
import StopLines from '@/components/timetable/StopLines.vue'
import { useFormat } from '@/composables/useFormat'
import { useStopDepartures } from '@/composables/useStopDepartures'
import { useStopOverview } from '@/composables/useStopOverview'
import { useTimetableRoute } from '@/composables/useTimetableRoute'
import { useCityStore } from '@/stores/city'
import type { StopDeparture, StopLine, VehicleType } from '@/types/api'
import { hasDeparted } from '@/utils/departures'

/**
 * Stop page: the departures board of the stop group (next departures of all lines, live times
 * where the city has realtime data, refreshed every 30 s while the page is visible) and below it
 * the lines serving the stop, each direction linking to its stop timetable. Both are loaded in
 * parallel and fail independently.
 */
const { t } = useI18n()
const fmt = useFormat()
const tt = useTimetableRoute()
const cityStore = useCityStore()
const idPrefix = useId()
const departuresHeadingId = `${idPrefix}-departures`
const linesHeadingId = `${idPrefix}-lines`

const stopKey = () =>
  tt.cityId.value && tt.stopId.value ? { city: tt.cityId.value, stop: tt.stopId.value } : null

const board = useStopDepartures(stopKey)
const overview = useStopOverview(stopKey)

const overviewData = computed(() => overview.data.value)
const stopLines = computed<readonly StopLine[]>(() => {
  const lines = overviewData.value?.lines
  return Array.isArray(lines) ? lines : []
})
const cityTypes = computed<readonly VehicleType[]>(
  () => cityStore.currentCityDetails?.vehicle_types ?? [],
)

function isNotFound(err: unknown): boolean {
  return err instanceof ApiError && err.status === 404
}

/** Both requests say the stop does not exist: one message for the page instead of two. */
const stopMissing = computed(
  () => isNotFound(board.error.value) && isNotFound(overview.error.value),
)

function retryAll(): void {
  board.reload()
  overview.reload()
}

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
/** From whichever response arrived; the two agree on the stop group. */
const stopName = computed<string>(
  () => overviewData.value?.stop?.name ?? data.value?.stop.name ?? '',
)

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
      v-if="stopMissing"
      :error="board.error.value"
      :not-found-text="t('timetable.departures.notFound')"
      @retry="retryAll"
    />

    <template v-else>
      <h1 v-if="stopName" class="stop-board__title">{{ stopName }}</h1>

      <section class="stop-board__section" :aria-labelledby="departuresHeadingId">
        <h2 :id="departuresHeadingId" class="stop-board__heading">
          {{ t('timetable.departures.title') }}
        </h2>

        <LoadStatus
          v-if="!data"
          :loading="board.status.value === 'loading'"
          :error="board.error.value"
          :not-found-text="t('timetable.departures.notFound')"
          :loading-text="t('timetable.departures.loading')"
          @retry="board.reload"
        />

        <template v-if="data">
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

      <section class="stop-board__section" :aria-labelledby="linesHeadingId">
        <h2 :id="linesHeadingId" class="stop-board__heading">
          {{ t('timetable.stopLines.title') }}
        </h2>

        <LoadStatus
          v-if="!overviewData"
          :loading="overview.status.value === 'loading'"
          :error="overview.error.value"
          :not-found-text="t('timetable.departures.notFound')"
          :loading-text="t('timetable.stopLines.loading')"
          @retry="overview.reload"
        />
        <template v-else>
          <p v-if="stopLines.length === 0" class="stop-board__empty" data-testid="no-stop-lines">
            {{ t('timetable.stopLines.empty') }}
          </p>
          <StopLines v-else :lines="stopLines" :type-order="cityTypes" />
        </template>
      </section>
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

.stop-board__title {
  margin: 0 0 var(--space-3);
  overflow-wrap: anywhere;
}

.stop-board__section + .stop-board__section {
  margin-top: var(--space-6);
}

.stop-board__heading {
  margin: 0 0 var(--space-3);
  font-size: 1.25rem;
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
