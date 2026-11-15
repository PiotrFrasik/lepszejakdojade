<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError } from '@/api/client'
import ItineraryCard from '@/components/journey/ItineraryCard.vue'
import ModeIcon from '@/components/journey/ModeIcon.vue'
import TicketHint from '@/components/journey/TicketHint.vue'
import { useFormat } from '@/composables/useFormat'
import { useJourneyStore } from '@/stores/journey'
import type { DirectTrip } from '@/types/api'

/** Results of the last search: loading / error / empty states, connections and walk/bike row. */
const { t } = useI18n()
const fmt = useFormat()
const journey = useJourneyStore()

const expandedId = ref<string | null>(null)

const itineraries = computed(() => journey.result?.itineraries ?? [])
const comparison = computed(() => journey.result?.comparison ?? null)
const selectedIndex = computed(() =>
  itineraries.value.findIndex((item) => item.id === journey.selectedItinerary?.id),
)

const errorText = computed(() => {
  const err = journey.error
  if (err instanceof ApiError) {
    if (err.status === 503) return t('journey.results.unavailable')
    if (err.status === 0) return t('errors.network')
    if (err.status === 429) return t('errors.rateLimited')
    // Validation messages from the API are already translated (Accept-Language).
    if (err.code === 'validation_error' && err.message) return err.message
  }
  return t('errors.generic')
})

function directText(trip: DirectTrip | null): string {
  if (!trip) return t('journey.comparison.unavailable')
  return t('journey.comparison.value', {
    duration: fmt.duration(trip.duration),
    distance: fmt.distance(trip.distance),
  })
}

function toggle(id: string): void {
  journey.selectItinerary(id)
  expandedId.value = expandedId.value === id ? null : id
}

watch(
  () => journey.result,
  () => {
    expandedId.value = null
  },
)
</script>

<template>
  <section class="journey-results" aria-labelledby="journey-results-title">
    <div class="journey-results__head">
      <h2 id="journey-results-title" class="journey-results__title">
        {{ t('journey.results.title') }}
      </h2>
      <button type="button" class="journey-results__close" @click="journey.clearResults()">
        {{ t('journey.results.close') }}
      </button>
    </div>

    <p role="status" aria-live="polite" class="journey-results__status">
      <template v-if="journey.status === 'loading'">{{ t('journey.results.loading') }}</template>
      <template v-else-if="journey.status === 'ready' && itineraries.length > 0">{{
        t('journey.results.count', { count: itineraries.length })
      }}</template>
    </p>

    <div v-if="journey.status === 'loading'" class="journey-results__skeleton" aria-hidden="true">
      <span v-for="n in 3" :key="n"></span>
    </div>

    <div v-else-if="journey.status === 'error'" class="journey-results__error" role="alert">
      <p>{{ errorText }}</p>
      <button type="button" class="button" @click="journey.search()">
        {{ t('errors.retry') }}
      </button>
    </div>

    <template v-else-if="journey.status === 'ready'">
      <p v-if="itineraries.length === 0" class="journey-results__empty">
        {{ t('journey.results.empty') }}
      </p>
      <ol v-else class="journey-results__list">
        <li v-for="(itinerary, index) in itineraries" :key="itinerary.id">
          <ItineraryCard
            :itinerary="itinerary"
            :index="index"
            :selected="journey.selectedItinerary?.id === itinerary.id"
            :expanded="expandedId === itinerary.id"
            @toggle="toggle(itinerary.id)"
          />
        </li>
      </ol>

      <TicketHint
        v-if="journey.selectedItinerary && selectedIndex >= 0"
        :itinerary="journey.selectedItinerary"
        :index="selectedIndex"
      />

      <div v-if="comparison" class="journey-results__comparison">
        <h3 class="journey-results__subtitle">{{ t('journey.comparison.title') }}</h3>
        <dl>
          <div>
            <dt><ModeIcon mode="walk" /> {{ t('journey.comparison.walk') }}</dt>
            <dd>{{ directText(comparison.walk) }}</dd>
          </div>
          <div>
            <dt><ModeIcon mode="bike" /> {{ t('journey.comparison.bike') }}</dt>
            <dd>{{ directText(comparison.bike) }}</dd>
          </div>
        </dl>
      </div>
    </template>
  </section>
</template>

<style scoped>
.journey-results {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.journey-results__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
}

.journey-results__title {
  margin: 0;
  font-size: 1rem;
}

.journey-results__close {
  padding: var(--space-1) var(--space-2);
  border: 0;
  border-radius: var(--radius);
  background: none;
  color: var(--color-link);
  font: inherit;
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
}

.journey-results__close:hover {
  background: var(--color-surface-alt);
}

.journey-results__status {
  margin: 0;
  color: var(--color-text-muted);
  font-size: 0.8125rem;
}

.journey-results__status:empty {
  display: none;
}

.journey-results__skeleton {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.journey-results__skeleton span {
  display: block;
  height: 5.5rem;
  border-radius: 12px;
  background: linear-gradient(90deg, #eef1f5 25%, #f7f9fb 50%, #eef1f5 75%);
  background-size: 200% 100%;
  animation: shimmer 1.2s linear infinite;
}

@keyframes shimmer {
  from {
    background-position: 200% 0;
  }

  to {
    background-position: -200% 0;
  }
}

.journey-results__error {
  padding: var(--space-3);
  border-radius: 12px;
  background: var(--color-danger-surface);
  color: var(--color-danger);
}

.journey-results__error p {
  margin: 0 0 var(--space-2);
}

.journey-results__empty {
  margin: 0;
  padding: var(--space-3);
  border-radius: 12px;
  background: var(--color-surface-alt);
}

.journey-results__list {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin: 0;
  padding: 0;
  list-style: none;
}

.journey-results__comparison {
  padding: var(--space-3);
  border-radius: 12px;
  background: var(--color-surface-alt);
}

.journey-results__subtitle {
  margin: 0 0 var(--space-2);
  font-size: 0.875rem;
}

.journey-results__comparison dl {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2) var(--space-4);
  margin: 0;
  font-size: 0.875rem;
}

.journey-results__comparison dt {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  font-weight: 600;
}

.journey-results__comparison dd {
  margin: 0;
  color: var(--color-text-muted);
}
</style>
