<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import { useApiResource } from '@/composables/useApiResource'
import { useFormat } from '@/composables/useFormat'
import { fetchTicketSuggestion } from '@/composables/useTickets'
import { useCityStore } from '@/stores/city'
import { useTicketsStore } from '@/stores/tickets'
import type { Itinerary } from '@/types/api'
import { hasSuggestedTicket, suggestDuration, suggestTransfers } from '@/utils/tickets'

/**
 * Cheapest ticket for the selected connection (`POST /cities/{city}/tickets/suggest/`), with the
 * server's one-sentence reason. Uses the fare remembered on the tickets page. Superseded requests
 * are aborted (new selection, city, language or fare). Shows nothing while there is no answer,
 * when no ticket matches or when the request fails: the hint is optional.
 */
const props = defineProps<{
  itinerary: Itinerary
  /** Position of the connection in the results list (0-based), for the heading. */
  index: number
}>()

const { t, locale } = useI18n()
const fmt = useFormat()
const cityStore = useCityStore()
const ticketsStore = useTicketsStore()

const resource = useApiResource(
  () => {
    const city = cityStore.cityId
    const duration = suggestDuration(props.itinerary.duration)
    if (!city || duration === null) return null
    return {
      city,
      locale: locale.value,
      itinerary: props.itinerary.id,
      request: {
        duration_seconds: duration,
        transfers: suggestTransfers(props.itinerary.transfers),
        reduced: ticketsStore.reduced,
      },
    }
  },
  (key, signal) => fetchTicketSuggestion(key.city, key.request, signal),
)

const suggestion = computed(() => {
  const value = resource.data.value
  return resource.status.value === 'ready' && hasSuggestedTicket(value) ? value : null
})

const price = computed(() =>
  suggestion.value
    ? fmt.money(suggestion.value.ticket.price, suggestion.value.ticket.currency)
    : '',
)
</script>

<template>
  <section v-if="suggestion" class="ticket-hint" aria-labelledby="ticket-hint-title">
    <h3 id="ticket-hint-title" class="ticket-hint__title">
      {{ t('journey.ticket.title', { index: index + 1 }) }}
    </h3>
    <p class="ticket-hint__main">
      <span class="ticket-hint__name">{{ suggestion.ticket.name }}</span>
      <span v-if="price" class="ticket-hint__price">{{ price }}</span>
    </p>
    <p v-if="suggestion.ticket.reduced" class="ticket-hint__fare">
      {{ t('journey.ticket.reducedFare') }}
    </p>
    <p v-if="suggestion.reason" class="ticket-hint__reason">{{ suggestion.reason }}</p>
    <RouterLink :to="{ name: 'tickets' }" class="ticket-hint__link">
      {{ t('journey.ticket.allTickets') }}
    </RouterLink>
  </section>
</template>

<style scoped>
.ticket-hint {
  padding: var(--space-3);
  border: 1px solid var(--color-border);
  border-left: 4px solid var(--color-primary);
  border-radius: 12px;
  background: var(--color-surface);
  font-size: 0.875rem;
}

.ticket-hint__title {
  margin: 0 0 var(--space-1);
  font-size: 0.875rem;
}

.ticket-hint__main {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--space-1) var(--space-3);
  margin: 0;
  font-size: 1rem;
}

.ticket-hint__name {
  font-weight: 600;
  overflow-wrap: anywhere;
}

.ticket-hint__price {
  font-weight: 700;
  white-space: nowrap;
}

.ticket-hint__fare {
  margin: 0;
  color: var(--color-text-muted);
  font-size: 0.8125rem;
}

.ticket-hint__reason {
  margin: var(--space-1) 0 var(--space-2);
  color: var(--color-text-muted);
}

.ticket-hint__link {
  font-weight: 600;
}
</style>
