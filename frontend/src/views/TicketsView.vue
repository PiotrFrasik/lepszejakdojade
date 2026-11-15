<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import LoadStatus from '@/components/LoadStatus.vue'
import { useApiResource } from '@/composables/useApiResource'
import { useFormat } from '@/composables/useFormat'
import { fetchTicketCatalogue } from '@/composables/useTickets'
import { useCityStore } from '@/stores/city'
import { useTicketsStore } from '@/stores/tickets'
import type { CityId, Ticket, TicketCatalogue } from '@/types/api'
import { isServiceDate, serviceDateToDate } from '@/utils/serviceDate'
import {
  TICKET_KINDS,
  groupTicketsByKind,
  latestPricesAsOf,
  priceListSources,
  urlHost,
  validityDays,
} from '@/utils/tickets'

/**
 * Ticket catalogue of the selected city (#82, contract "Tickets (#14)"): zone legend, tickets
 * grouped by kind, standard / reduced fare toggle, prices formatted for the UI language, the
 * "prices as of" date and the official price list. Names are translated by the API, so the page
 * re-fetches on language change (keeping the old list on screen meanwhile) and on city change.
 */
const { t, te, locale } = useI18n()
const fmt = useFormat()
const cityStore = useCityStore()
const ticketsStore = useTicketsStore()

interface Loaded {
  city: CityId
  catalogue: TicketCatalogue
}

// Both fares are loaded at once (the catalogue is small), so the toggle needs no request.
const resource = useApiResource<{ city: CityId; locale: string }, Loaded>(
  () => (cityStore.cityId ? { city: cityStore.cityId, locale: locale.value } : null),
  async (key, signal) => ({
    city: key.city,
    catalogue: await fetchTicketCatalogue(key.city, {}, signal),
  }),
  { keepPrevious: true },
)

/** Catalogue of the selected city only (the previous city's list is never shown). */
const catalogue = computed<TicketCatalogue | null>(() => {
  const loaded = resource.data.value
  return loaded && loaded.city === cityStore.cityId ? loaded.catalogue : null
})

const loading = computed(() => resource.status.value === 'loading' && !catalogue.value)
const refreshing = computed(() => resource.status.value === 'loading' && !!catalogue.value)

const allTickets = computed<Ticket[]>(() => catalogue.value?.tickets ?? [])
const fareTickets = computed(() =>
  allTickets.value.filter((ticket) => ticket.reduced === ticketsStore.reduced),
)
const groups = computed(() => groupTicketsByKind(fareTickets.value))

const zoneNames = computed(() => {
  const names = new Map<string, string>()
  for (const zone of catalogue.value?.zones ?? []) names.set(zone.id, zone.name)
  return names
})

const pricesAsOf = computed(() => {
  const value = latestPricesAsOf(allTickets.value)
  if (!value || !isServiceDate(value)) return ''
  return fmt.date(serviceDateToDate(value))
})

const sources = computed(() => priceListSources(allTickets.value))

const cityName = computed(() => cityStore.currentCity?.name ?? '')

function kindTitle(kind: string): string {
  return (TICKET_KINDS as readonly string[]).includes(kind) && te(`tickets.kinds.${kind}`)
    ? t(`tickets.kinds.${kind}`)
    : t('tickets.kinds.other')
}

function validityText(ticket: Ticket): string {
  if (ticket.kind === 'single') return t('tickets.validity.single')
  const minutes = ticket.validity_minutes
  if (minutes === null || !Number.isFinite(minutes) || minutes <= 0) return ''
  const days = validityDays(minutes)
  // Periods of a week or more read better in days; shorter tickets as "24 h", "60 min".
  if (days !== null && days >= 7) return t('tickets.validity.days', { days }, days)
  return t('tickets.validity.duration', { duration: fmt.duration(minutes * 60) })
}

function zonesText(ticket: Ticket): string {
  const names = ticket.zones.map((id) => zoneNames.value.get(id) ?? id)
  if (names.length === 0) return ''
  return t('tickets.zonesOfTicket', { zones: names.join(', ') })
}

function setReduced(value: boolean): void {
  ticketsStore.setReduced(value)
}
</script>

<template>
  <section class="page tickets" aria-labelledby="tickets-title">
    <h1 id="tickets-title">{{ t('tickets.title') }}</h1>
    <p v-if="cityName" class="tickets__intro">{{ t('tickets.intro', { city: cityName }) }}</p>
    <p class="tickets__notice">{{ t('tickets.notice') }}</p>

    <div class="fare-toggle" role="group" :aria-label="t('tickets.fareLabel')">
      <button
        type="button"
        class="fare-toggle__option"
        :aria-pressed="!ticketsStore.reduced"
        @click="setReduced(false)"
      >
        {{ t('tickets.fare.standard') }}
      </button>
      <button
        type="button"
        class="fare-toggle__option"
        :aria-pressed="ticketsStore.reduced"
        @click="setReduced(true)"
      >
        {{ t('tickets.fare.reduced') }}
      </button>
    </div>

    <LoadStatus
      :loading="loading"
      :error="resource.error.value"
      :not-found-text="t('tickets.cityNotFound')"
      :loading-text="t('tickets.loading')"
      @retry="resource.reload"
    />

    <div v-if="catalogue" class="tickets__content" :aria-busy="refreshing">
      <p v-if="pricesAsOf || sources.length > 0" class="tickets__meta">
        <span v-if="pricesAsOf">{{ t('tickets.pricesAsOf', { date: pricesAsOf }) }}</span>
        <template v-for="url in sources" :key="url">
          <a :href="url" target="_blank" rel="noopener noreferrer" class="tickets__source">
            {{ t('tickets.source', { host: urlHost(url) }) }}
            <span class="visually-hidden">{{ t('tickets.newTab') }}</span>
          </a>
        </template>
      </p>

      <section
        v-if="catalogue.zones.length > 0"
        class="tickets__zones"
        aria-labelledby="tickets-zones-title"
      >
        <h2 id="tickets-zones-title">{{ t('tickets.zonesTitle') }}</h2>
        <ul class="tickets__zone-list">
          <li v-for="zone in catalogue.zones" :key="zone.id" class="tickets__zone">
            <span class="tickets__zone-id" aria-hidden="true">{{ zone.id }}</span>
            <span>{{ zone.name }}</span>
          </li>
        </ul>
        <p class="tickets__muted">{{ t('tickets.zonesHint') }}</p>
      </section>

      <p v-if="allTickets.length === 0" class="tickets__empty">{{ t('tickets.empty') }}</p>
      <p v-else-if="fareTickets.length === 0" class="tickets__empty">
        {{ ticketsStore.reduced ? t('tickets.emptyReduced') : t('tickets.emptyStandard') }}
      </p>

      <section
        v-for="group in groups"
        :key="group.kind"
        class="tickets__group"
        :aria-labelledby="`tickets-kind-${group.kind}`"
      >
        <h2 :id="`tickets-kind-${group.kind}`">{{ kindTitle(group.kind) }}</h2>
        <ul class="tickets__list">
          <li v-for="ticket in group.tickets" :key="ticket.id" class="ticket-card">
            <div class="ticket-card__head">
              <h3 class="ticket-card__name">{{ ticket.name }}</h3>
              <p class="ticket-card__price">{{ fmt.money(ticket.price, ticket.currency) }}</p>
            </div>
            <ul class="ticket-card__facts">
              <li v-if="validityText(ticket)">{{ validityText(ticket) }}</li>
              <li v-if="zonesText(ticket)">{{ zonesText(ticket) }}</li>
              <li v-if="ticket.reduced">{{ t('tickets.fare.reduced') }}</li>
            </ul>
            <p v-if="ticket.description" class="ticket-card__description">
              {{ ticket.description }}
            </p>
          </li>
        </ul>
      </section>
    </div>
  </section>
</template>

<style scoped>
.tickets__intro {
  margin-bottom: var(--space-2);
}

.tickets__notice {
  margin: 0 0 var(--space-4);
  padding: var(--space-2) var(--space-3);
  border-left: 4px solid var(--color-warning);
  border-radius: var(--radius);
  background: var(--color-highlight);
}

.fare-toggle {
  display: inline-flex;
  max-width: 100%;
  border: 1px solid var(--color-primary);
  border-radius: var(--radius);
  overflow: hidden;
}

.fare-toggle__option {
  flex: 1 1 auto;
  min-height: 2.75rem;
  min-width: 7rem;
  padding: var(--space-2) var(--space-4);
  border: 0;
  background: var(--color-surface);
  color: var(--color-primary);
  font: inherit;
  font-weight: 600;
  cursor: pointer;
}

.fare-toggle__option + .fare-toggle__option {
  border-left: 1px solid var(--color-primary);
}

.fare-toggle__option[aria-pressed='true'] {
  background: var(--color-primary);
  color: var(--color-on-primary);
}

.fare-toggle__option:focus-visible {
  outline-offset: -4px;
}

.tickets__content[aria-busy='true'] {
  opacity: 0.6;
}

.tickets__meta {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1) var(--space-4);
  margin: var(--space-4) 0;
  color: var(--color-text-muted);
  font-size: 0.875rem;
}

.tickets__source {
  font-weight: 600;
  overflow-wrap: anywhere;
}

.tickets__zones,
.tickets__group {
  margin-top: var(--space-5);
}

.tickets h2 {
  margin: 0 0 var(--space-3);
  font-size: 1.125rem;
}

.tickets__zone-list {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2) var(--space-4);
  margin: 0;
  padding: 0;
  list-style: none;
}

.tickets__zone {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
}

.tickets__zone-id {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 1.75rem;
  height: 1.75rem;
  padding: 0 var(--space-1);
  border-radius: var(--radius);
  background: var(--color-primary);
  color: var(--color-on-primary);
  font-weight: 700;
  font-size: 0.875rem;
}

.tickets__muted,
.tickets__empty {
  color: var(--color-text-muted);
}

.tickets__muted {
  margin: var(--space-2) 0 0;
  font-size: 0.875rem;
}

.tickets__empty {
  margin: var(--space-4) 0;
  padding: var(--space-3);
  border-radius: var(--radius);
  background: var(--color-surface-alt);
}

.tickets__list {
  display: grid;
  gap: var(--space-3);
  margin: 0;
  padding: 0;
  list-style: none;
}

.ticket-card {
  padding: var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  background: var(--color-surface);
}

.ticket-card__head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--space-1) var(--space-3);
}

.ticket-card__name {
  margin: 0;
  font-size: 1rem;
  overflow-wrap: anywhere;
}

.ticket-card__price {
  margin: 0;
  font-size: 1.125rem;
  font-weight: 700;
  white-space: nowrap;
}

.ticket-card__facts {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1) var(--space-3);
  margin: var(--space-1) 0 0;
  padding: 0;
  list-style: none;
  color: var(--color-text-muted);
  font-size: 0.875rem;
}

.ticket-card__description {
  margin: var(--space-2) 0 0;
  font-size: 0.875rem;
}

@media (min-width: 40rem) {
  .tickets__list {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
