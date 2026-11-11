<script setup lang="ts">
import { nextTick, onMounted, ref, useId } from 'vue'
import { useI18n } from 'vue-i18n'

import type { CityId } from '@/config/cities'
import { useCityStore } from '@/stores/city'

/**
 * First-visit city picker. Modal: the rest of the app is made `inert` by `App.vue` while it is
 * shown, and it cannot be dismissed without choosing a city.
 */
const { t } = useI18n()
const cityStore = useCityStore()
const titleId = useId()
const descriptionId = useId()
const dialogRef = ref<HTMLElement | null>(null)

function choose(id: CityId): void {
  cityStore.setCity(id)
}

/** Keeps Tab / Shift+Tab inside the dialog. */
function trapFocus(event: KeyboardEvent): void {
  if (event.key !== 'Tab' || !dialogRef.value) return
  const focusable = Array.from(dialogRef.value.querySelectorAll<HTMLElement>('button'))
  if (focusable.length === 0) return
  const first = focusable[0]!
  const last = focusable[focusable.length - 1]!
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}

onMounted(async () => {
  await nextTick()
  dialogRef.value?.querySelector<HTMLElement>('button')?.focus()
})
</script>

<template>
  <div class="city-picker__backdrop">
    <div
      ref="dialogRef"
      class="city-picker"
      role="dialog"
      aria-modal="true"
      :aria-labelledby="titleId"
      :aria-describedby="descriptionId"
      @keydown="trapFocus"
    >
      <h2 :id="titleId" class="city-picker__title">{{ t('city.pickerTitle') }}</h2>
      <p :id="descriptionId" class="city-picker__description">{{ t('city.pickerDescription') }}</p>
      <ul class="city-picker__options" :aria-label="t('city.pickerOptionsLabel')">
        <li v-for="city in cityStore.cities" :key="city.id">
          <button
            type="button"
            class="city-picker__option"
            :data-city="city.id"
            @click="choose(city.id)"
          >
            {{ city.name }}
          </button>
        </li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
.city-picker__backdrop {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-3);
  background: rgb(10 20 35 / 60%);
}

.city-picker {
  width: 100%;
  max-width: 26rem;
  max-height: calc(100dvh - 2 * var(--space-3));
  overflow-y: auto;
  padding: var(--space-5);
  border-radius: calc(var(--radius) * 2);
  background: var(--color-surface);
  color: var(--color-text);
  box-shadow: 0 10px 40px rgb(0 0 0 / 30%);
}

.city-picker__title {
  margin: 0 0 var(--space-2);
  font-size: 1.375rem;
}

.city-picker__description {
  margin: 0 0 var(--space-4);
  color: var(--color-text-muted);
}

.city-picker__options {
  display: grid;
  gap: var(--space-3);
  margin: 0;
  padding: 0;
  list-style: none;
}

.city-picker__option {
  width: 100%;
  min-height: 3.5rem;
  padding: var(--space-3) var(--space-4);
  border: 2px solid var(--color-primary);
  border-radius: var(--radius);
  background: var(--color-surface);
  color: var(--color-primary);
  font: inherit;
  font-size: 1.25rem;
  font-weight: 700;
  cursor: pointer;
}

.city-picker__option:hover,
.city-picker__option:focus-visible {
  background: var(--color-primary);
  color: var(--color-on-primary);
}

.city-picker__option:focus-visible {
  outline: 3px solid var(--color-focus);
  outline-offset: 2px;
}

@media (min-width: 480px) {
  .city-picker__options {
    grid-template-columns: 1fr 1fr;
  }
}
</style>
