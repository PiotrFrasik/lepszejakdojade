<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, type RouteLocationRaw } from 'vue-router'

import LineBadge from '@/components/timetable/LineBadge.vue'
import { useFormat } from '@/composables/useFormat'
import type { ChatDeparture, DeparturesChatCard } from '@/types/api'
import { serviceDateToDate, todayIn } from '@/utils/serviceDate'

/**
 * `departures` card of an assistant answer: upcoming departures at one stop. Each row links to
 * the stop timetable of that line, platform (`departure.stop_id`), direction and service date.
 */
const props = defineProps<{ card: DeparturesChatCard; idPrefix: string }>()
const emit = defineEmits<{ navigate: [] }>()

const { t } = useI18n()
const fmt = useFormat()

const today = computed(() => todayIn(fmt.timeZone.value))
const departures = computed(() =>
  props.card.departures.filter((d): d is ChatDeparture => Boolean(d?.line?.id && d.time)),
)

function link(departure: ChatDeparture): RouteLocationRaw {
  return {
    name: 'timetable-stop',
    // Each departure has its own platform; `card.stop.stop_id` is only the group's representative.
    params: { lineId: departure.line.id, stopId: departure.stop_id || props.card.stop.stop_id },
    query: {
      direction: departure.direction === 1 ? '1' : undefined,
      date: departure.date && departure.date !== today.value ? departure.date : undefined,
    },
  }
}

/**
 * Calendar day of the departure: `date` is the service day, and `next_day` times (after
 * midnight) fall on the following calendar day. The link keeps the service `date`.
 */
function calendarDate(departure: ChatDeparture): Date | null {
  if (!departure.date) return null
  const day = serviceDateToDate(departure.date)
  if (departure.next_day) day.setUTCDate(day.getUTCDate() + 1)
  return day
}

/** Shown after the time when the departure is not on today's calendar day. */
function dayNote(departure: ChatDeparture): string | null {
  const day = calendarDate(departure)
  if (!day) return null
  // `day` is noon UTC, so its ISO date is the calendar day.
  return day.toISOString().slice(0, 10) === today.value ? null : fmt.date(day)
}

function linkLabel(departure: ChatDeparture): string {
  const values = {
    line: departure.line.short_name,
    headsign: departure.headsign,
    time: departure.time,
  }
  const day = dayNote(departure)
  return day
    ? t('assistant.cards.departureLinkDay', { ...values, day })
    : t('assistant.cards.departureLink', values)
}
</script>

<template>
  <section class="chat-departures" :aria-labelledby="`${idPrefix}-title`">
    <h3 :id="`${idPrefix}-title`" class="chat-departures__title">
      {{ t('assistant.cards.departuresTitle', { stop: card.stop.name }) }}
    </h3>
    <ul class="chat-departures__list">
      <li v-for="(departure, i) in departures" :key="`${departure.trip_id}-${i}`">
        <RouterLink
          :to="link(departure)"
          class="chat-departures__row"
          :aria-label="linkLabel(departure)"
          @click="emit('navigate')"
        >
          <LineBadge :line="departure.line" size="sm" />
          <span class="chat-departures__time">
            {{ departure.time }}
            <small v-if="dayNote(departure)">{{ dayNote(departure) }}</small>
          </span>
          <span class="chat-departures__headsign">{{ departure.headsign }}</span>
        </RouterLink>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.chat-departures__title {
  margin: 0 0 var(--space-2);
  font-size: 0.9375rem;
}

.chat-departures__list {
  margin: 0;
  padding: 0;
  list-style: none;
  border: 1px solid var(--color-border);
  border-radius: 12px;
  background: var(--color-surface);
  overflow: hidden;
}

.chat-departures__list li + li {
  border-top: 1px solid var(--color-border);
}

.chat-departures__row {
  display: grid;
  grid-template-columns: 3rem auto 1fr;
  align-items: center;
  gap: var(--space-2);
  min-height: 2.75rem;
  padding: var(--space-2) var(--space-3);
  color: inherit;
  text-decoration: none;
}

.chat-departures__row:hover {
  background: var(--color-surface-alt);
}

.chat-departures__time {
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.chat-departures__time small {
  display: block;
  color: var(--color-text-muted);
  font-size: 0.75rem;
  font-weight: 400;
}

.chat-departures__headsign {
  min-width: 0;
  overflow-wrap: anywhere;
}
</style>
