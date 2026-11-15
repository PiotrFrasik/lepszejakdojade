<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import ModeIcon from '@/components/journey/ModeIcon.vue'
import type { StopSearchResult, StopsChatCard } from '@/types/api'

/**
 * `stops` card of an assistant answer (the place name was ambiguous). Choosing a stop puts a
 * question about it into the input, so the user can send or edit it.
 */
defineProps<{ card: StopsChatCard; idPrefix: string }>()
const emit = defineEmits<{ prefill: [text: string] }>()

const { t } = useI18n()

function choose(stop: StopSearchResult): void {
  emit('prefill', t('assistant.cards.stopQuestion', { stop: stop.name }))
}
</script>

<template>
  <section class="chat-stops" :aria-labelledby="`${idPrefix}-title`">
    <h3 :id="`${idPrefix}-title`" class="chat-stops__title">
      {{ t('assistant.cards.stopsTitle') }}
    </h3>
    <ul class="chat-stops__list">
      <li v-for="stop in card.stops" :key="stop.stop_id">
        <button
          type="button"
          class="chat-stops__item"
          :aria-label="t('assistant.cards.stopAsk', { stop: stop.name })"
          @click="choose(stop)"
        >
          <span class="chat-stops__name">{{ stop.name }}</span>
          <span class="chat-stops__modes">
            <ModeIcon v-for="mode in stop.vehicle_types ?? []" :key="mode" :mode="mode" />
          </span>
        </button>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.chat-stops__title {
  margin: 0 0 var(--space-2);
  font-size: 0.9375rem;
}

.chat-stops__list {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  margin: 0;
  padding: 0;
  list-style: none;
}

.chat-stops__item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  width: 100%;
  min-height: 2.75rem;
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  background: var(--color-surface);
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.chat-stops__item:hover {
  background: var(--color-surface-alt);
}

.chat-stops__name {
  font-weight: 600;
}

.chat-stops__modes {
  display: inline-flex;
  gap: var(--space-1);
  color: var(--color-text-muted);
}
</style>
