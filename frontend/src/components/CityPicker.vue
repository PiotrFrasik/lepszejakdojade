<script setup lang="ts">
import { computed, nextTick, onMounted, ref, useId, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import type { CityId } from '@/config/cities'
import { useCityStore } from '@/stores/city'

/**
 * First-visit city picker. Modal: the rest of the app is made `inert` by `App.vue` while it is
 * shown, and it cannot be dismissed without choosing a city. Cities come from the API, so it
 * also shows the loading and error (with retry) states of the city list.
 */
const { t } = useI18n()
const cityStore = useCityStore()
const titleId = useId()
const descriptionId = useId()
const dialogRef = ref<HTMLElement | null>(null)

const hasOptions = computed(() => cityStore.cities.length > 0)
const isRetrying = computed(() => cityStore.listStatus === 'loading')
/** First load: nothing to show yet and no earlier failure. */
const isLoading = computed(
  () => isRetrying.value && !hasOptions.value && cityStore.listError === null,
)
/** Stays visible during a retry (button disabled, "retrying"); options replace it on success. */
const isError = computed(() => cityStore.listError !== null && !hasOptions.value)
const isEmpty = computed(() => cityStore.listStatus === 'ready' && !hasOptions.value)

function choose(id: CityId): void {
  cityStore.setCity(id)
}

function retry(): void {
  void cityStore.loadCities()
}

/** Focuses the first enabled button, or the dialog itself while there is none (loading). */
async function focusFirst(): Promise<void> {
  await nextTick()
  const dialog = dialogRef.value
  if (!dialog) return
  ;(dialog.querySelector<HTMLElement>('button:not([disabled])') ?? dialog).focus()
}

/** Keeps Tab / Shift+Tab inside the dialog. */
function trapFocus(event: KeyboardEvent): void {
  if (event.key !== 'Tab' || !dialogRef.value) return
  const focusable = Array.from(
    dialogRef.value.querySelectorAll<HTMLElement>('button:not([disabled])'),
  )
  if (focusable.length === 0) {
    event.preventDefault()
    return
  }
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

// The city list is loaded by `App.vue` (`cityStore.init()`).
onMounted(() => {
  void focusFirst()
})

// Move focus to the new buttons when the state changes (loaded, failed, retrying, retried).
watch([hasOptions, isError, isRetrying], async () => {
  await nextTick()
  const active = document.activeElement
  const onUsableButton =
    active instanceof HTMLButtonElement &&
    !active.disabled &&
    dialogRef.value?.contains(active) === true
  if (!onUsableButton) void focusFirst()
})
</script>

<template>
  <div class="city-picker__backdrop">
    <div
      ref="dialogRef"
      class="city-picker"
      role="dialog"
      aria-modal="true"
      tabindex="-1"
      :aria-labelledby="titleId"
      :aria-describedby="descriptionId"
      :aria-busy="isLoading || isRetrying || undefined"
      @keydown="trapFocus"
    >
      <h2 :id="titleId" class="city-picker__title">{{ t('city.pickerTitle') }}</h2>
      <p :id="descriptionId" class="city-picker__description">{{ t('city.pickerDescription') }}</p>
      <p v-if="isLoading" class="city-picker__status" role="status">
        <span class="city-picker__spinner" aria-hidden="true"></span>
        {{ t('city.loading') }}
      </p>
      <div v-else-if="isError" class="city-picker__error" role="alert">
        <p class="city-picker__error-text">{{ t('city.loadError') }}</p>
        <button type="button" class="city-picker__retry" :disabled="isRetrying" @click="retry">
          {{ isRetrying ? t('city.retrying') : t('city.retry') }}
        </button>
      </div>
      <div v-else-if="isEmpty" class="city-picker__error" role="status">
        <p class="city-picker__error-text">{{ t('city.empty') }}</p>
        <button type="button" class="city-picker__retry" @click="retry">
          {{ t('city.retry') }}
        </button>
      </div>
      <ul v-if="hasOptions" class="city-picker__options" :aria-label="t('city.pickerOptionsLabel')">
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

.city-picker:focus {
  outline: none;
}

.city-picker__status {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin: 0;
  color: var(--color-text-muted);
}

.city-picker__spinner {
  flex: none;
  width: 1.25rem;
  height: 1.25rem;
  border: 3px solid var(--color-border);
  border-top-color: var(--color-primary);
  border-radius: 50%;
  animation: city-picker-spin 0.8s linear infinite;
}

@keyframes city-picker-spin {
  to {
    transform: rotate(360deg);
  }
}

@media (prefers-reduced-motion: reduce) {
  .city-picker__spinner {
    animation: none;
  }
}

.city-picker__error {
  margin: 0 0 var(--space-4);
  padding: var(--space-3);
  border-left: 4px solid var(--color-danger);
  border-radius: var(--radius);
  background: var(--color-surface-alt);
}

.city-picker__error-text {
  margin: 0 0 var(--space-3);
}

.city-picker__retry {
  min-height: 2.75rem;
  padding: var(--space-2) var(--space-4);
  border: 0;
  border-radius: var(--radius);
  background: var(--color-primary);
  color: var(--color-on-primary);
  font: inherit;
  font-weight: 600;
  cursor: pointer;
}

.city-picker__retry:disabled {
  opacity: 0.7;
  cursor: progress;
}

.city-picker__retry:focus-visible {
  outline: 3px solid var(--color-focus);
  outline-offset: 2px;
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
