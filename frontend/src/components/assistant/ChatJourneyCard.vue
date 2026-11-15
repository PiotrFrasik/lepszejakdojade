<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import ItineraryCard from '@/components/journey/ItineraryCard.vue'
import ModeIcon from '@/components/journey/ModeIcon.vue'
import { useFormat } from '@/composables/useFormat'
import { useJourneyStore } from '@/stores/journey'
import type { DirectTrip, JourneyChatCard, JourneyPlace } from '@/types/api'

/**
 * `journey` card of an assistant answer: the connection summary (same component as the
 * journey results) and a button that opens it in the journey planner on the home map.
 */
const props = defineProps<{ card: JourneyChatCard; idPrefix: string }>()
const emit = defineEmits<{ navigate: [] }>()

const { t } = useI18n()
const fmt = useFormat()
const router = useRouter()
const journey = useJourneyStore()

const expanded = ref(false)

function placeName(place: JourneyPlace): string {
  return place.name || t('journey.leg.unnamed')
}

function directText(trip: DirectTrip | null | undefined): string {
  if (!trip) return t('journey.comparison.unavailable')
  return t('journey.comparison.value', {
    duration: fmt.duration(trip.duration),
    distance: fmt.distance(trip.distance),
  })
}

function showOnMap(): void {
  const { from, to, itinerary, comparison } = props.card
  journey.showItinerary(from, to, itinerary, comparison ?? { walk: null, bike: null })
  emit('navigate')
  void router.push({ name: 'home' })
}
</script>

<template>
  <section class="chat-journey" :aria-labelledby="`${idPrefix}-title`">
    <h3 :id="`${idPrefix}-title`" class="chat-journey__title">
      {{
        t('assistant.cards.journeyTitle', { from: placeName(card.from), to: placeName(card.to) })
      }}
    </h3>
    <ItineraryCard
      :itinerary="card.itinerary"
      :index="0"
      :selected="false"
      :expanded="expanded"
      :id-prefix="idPrefix"
      @toggle="expanded = !expanded"
    />
    <dl
      v-if="card.comparison"
      class="chat-journey__comparison"
      :aria-label="t('journey.comparison.title')"
    >
      <div>
        <dt><ModeIcon mode="walk" /> {{ t('journey.comparison.walk') }}</dt>
        <dd>{{ directText(card.comparison.walk) }}</dd>
      </div>
      <div>
        <dt><ModeIcon mode="bike" /> {{ t('journey.comparison.bike') }}</dt>
        <dd>{{ directText(card.comparison.bike) }}</dd>
      </div>
    </dl>
    <button type="button" class="button chat-journey__map" @click="showOnMap">
      {{ t('assistant.cards.showOnMap') }}
    </button>
  </section>
</template>

<style scoped>
.chat-journey {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.chat-journey__title {
  margin: 0;
  font-size: 0.9375rem;
}

.chat-journey__comparison {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1) var(--space-3);
  margin: 0;
  color: var(--color-text-muted);
  font-size: 0.8125rem;
}

.chat-journey__comparison div {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
}

.chat-journey__comparison dt {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  font-weight: 600;
}

.chat-journey__comparison dd {
  margin: 0;
}

.chat-journey__map {
  align-self: flex-start;
}
</style>
