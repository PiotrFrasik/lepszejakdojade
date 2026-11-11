<script setup lang="ts">
import { computed, useId } from 'vue'
import { useI18n } from 'vue-i18n'

import { useCityStore } from '@/stores/city'

const { t } = useI18n()
const cityStore = useCityStore()
const selectId = useId()

const selected = computed({
  get: () => (cityStore.hasCity ? (cityStore.cityId ?? '') : ''),
  set: (value: string) => cityStore.setCity(value),
})

const placeholder = computed(() =>
  cityStore.cities.length === 0 && cityStore.listStatus === 'loading'
    ? t('city.loading')
    : t('city.label'),
)
</script>

<template>
  <div class="city-switcher">
    <label :for="selectId" class="visually-hidden">{{ t('city.label') }}</label>
    <select
      :id="selectId"
      v-model="selected"
      class="city-switcher__select"
      :disabled="cityStore.cities.length === 0"
    >
      <option v-if="!cityStore.hasCity" value="" disabled>{{ placeholder }}</option>
      <option v-for="city in cityStore.cities" :key="city.id" :value="city.id">
        {{ city.name }}
      </option>
    </select>
  </div>
</template>

<style scoped>
.city-switcher__select {
  min-height: 2.5rem;
  max-width: 10rem;
  padding: var(--space-1) var(--space-6) var(--space-1) var(--space-3);
  border: 1px solid rgb(255 255 255 / 70%);
  border-radius: var(--radius);
  background-color: rgb(255 255 255 / 12%);
  background-image:
    linear-gradient(45deg, transparent 50%, currentcolor 50%),
    linear-gradient(135deg, currentcolor 50%, transparent 50%);
  background-position:
    calc(100% - 15px) 50%,
    calc(100% - 10px) 50%;
  background-size: 5px 5px;
  background-repeat: no-repeat;
  color: inherit;
  font: inherit;
  font-weight: 600;
  appearance: none;
  cursor: pointer;
}

.city-switcher__select:disabled {
  opacity: 0.7;
  cursor: progress;
}

.city-switcher__select option {
  color: var(--color-text);
  background: var(--color-surface);
}
</style>
