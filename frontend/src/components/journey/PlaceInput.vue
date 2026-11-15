<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { searchStops } from '@/api/client'
import type { CityId, StopSearchResult } from '@/types/api'
import type { PlaceValue } from '@/utils/journey'

/**
 * One end of the journey: a stop name field with autocomplete (WAI-ARIA combobox), plus
 * "my location" and "choose on the map" buttons. Typing clears the chosen place.
 * With `hideActions` it is a plain stop search (e.g. the timetable's stop departures entry).
 */
const props = defineProps<{
  id: string
  label: string
  modelValue: PlaceValue | null
  city: CityId | null
  locating?: boolean
  picking?: boolean
  /** Error text shown under the field (e.g. geolocation problem). */
  errorText?: string | null
  /** Hides the "my location" and "choose on the map" buttons (stop-only search). */
  hideActions?: boolean
  /** Defaults to the journey form's "stop name" placeholder. */
  placeholder?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: PlaceValue | null]
  locate: []
  pick: []
}>()

/** Delay before querying the stop search while typing. */
const DEBOUNCE_MS = 250
const MIN_CHARS = 2

const { t } = useI18n()

const text = ref('')
const editing = ref(false)
const open = ref(false)
const results = ref<StopSearchResult[]>([])
const activeIndex = ref(-1)
const status = ref<'idle' | 'loading' | 'ready' | 'error'>('idle')
let timer: ReturnType<typeof setTimeout> | null = null
let controller: AbortController | null = null

const listId = computed(() => `${props.id}-list`)
const statusId = computed(() => `${props.id}-status`)
const errorId = computed(() => `${props.id}-error`)

function placeLabel(place: PlaceValue | null): string {
  if (!place) return ''
  if (place.source === 'location') return t('journey.place.myLocation')
  if (place.source === 'map') return place.name ?? t('journey.place.mapPoint')
  return place.name ?? ''
}

const displayValue = computed(() => (editing.value ? text.value : placeLabel(props.modelValue)))
const trimmed = computed(() => text.value.trim())

const statusText = computed(() => {
  if (!open.value) return ''
  if (status.value === 'loading') return t('journey.autocomplete.searching')
  if (status.value === 'error') return t('journey.autocomplete.error')
  if (status.value === 'ready' && results.value.length === 0) {
    return t('journey.autocomplete.noResults', { query: trimmed.value })
  }
  if (status.value === 'ready') {
    return t('journey.autocomplete.count', { count: results.value.length })
  }
  return ''
})

function cancelPending(): void {
  if (timer !== null) clearTimeout(timer)
  timer = null
  controller?.abort()
  controller = null
}

async function runSearch(query: string): Promise<void> {
  if (!props.city) return
  controller?.abort()
  const current = new AbortController()
  controller = current
  status.value = 'loading'
  try {
    const found = await searchStops(props.city, query, current.signal)
    if (current.signal.aborted) return
    results.value = Array.isArray(found) ? found : []
    activeIndex.value = -1
    status.value = 'ready'
  } catch {
    if (current.signal.aborted) return
    results.value = []
    status.value = 'error'
  } finally {
    if (controller === current) controller = null
  }
}

function onInput(event: Event): void {
  text.value = (event.target as HTMLInputElement).value
  editing.value = true
  if (props.modelValue) emit('update:modelValue', null)
  cancelPending()
  // Results of the previous query are stale: drop them so Enter cannot pick one.
  results.value = []
  activeIndex.value = -1
  if (trimmed.value.length < MIN_CHARS) {
    open.value = false
    status.value = 'idle'
    return
  }
  open.value = true
  status.value = 'loading'
  const query = trimmed.value
  timer = setTimeout(() => {
    timer = null
    void runSearch(query)
  }, DEBOUNCE_MS)
}

function select(stop: StopSearchResult): void {
  cancelPending()
  emit('update:modelValue', {
    source: 'stop',
    name: stop.name,
    lat: stop.lat,
    lon: stop.lon,
    stopId: stop.stop_id,
  })
  editing.value = false
  open.value = false
  results.value = []
  status.value = 'idle'
}

function close(): void {
  open.value = false
  activeIndex.value = -1
}

function onKeydown(event: KeyboardEvent): void {
  const count = results.value.length
  if (event.key === 'ArrowDown') {
    if (!open.value && trimmed.value.length >= MIN_CHARS && count > 0) open.value = true
    if (count > 0) activeIndex.value = (activeIndex.value + 1) % count
    event.preventDefault()
  } else if (event.key === 'ArrowUp') {
    if (count > 0) activeIndex.value = activeIndex.value <= 0 ? count - 1 : activeIndex.value - 1
    event.preventDefault()
  } else if (event.key === 'Enter') {
    // Only results of the current query can be chosen (none while a search is pending).
    const current = open.value && status.value === 'ready' && timer === null
    const stop = current ? results.value[activeIndex.value >= 0 ? activeIndex.value : 0] : null
    if (stop) {
      event.preventDefault()
      select(stop)
    }
  } else if (event.key === 'Escape' && open.value) {
    event.preventDefault()
    close()
  }
}

function onBlur(): void {
  close()
  // Leaving the field without choosing shows the chosen place again (or keeps the typed text).
  if (props.modelValue) editing.value = false
}

const vehicleTypesText = (stop: StopSearchResult): string =>
  stop.vehicle_types.map((type) => t(`timetable.vehicleType.${type}`)).join(' · ')

// A place set from outside (swap, map, location) replaces whatever was typed.
watch(
  () => props.modelValue,
  (value) => {
    if (value) {
      editing.value = false
      cancelPending()
      close()
    }
  },
)

onBeforeUnmount(cancelPending)
</script>

<template>
  <div class="place-input">
    <label class="place-input__label" :for="id">{{ label }}</label>
    <div class="place-input__row">
      <div class="place-input__field">
        <input
          :id="id"
          class="place-input__input"
          type="text"
          role="combobox"
          autocomplete="off"
          spellcheck="false"
          aria-autocomplete="list"
          :aria-expanded="open && results.length > 0"
          :aria-controls="listId"
          :aria-activedescendant="activeIndex >= 0 ? `${id}-opt-${activeIndex}` : undefined"
          :aria-describedby="errorText ? `${statusId} ${errorId}` : statusId"
          :aria-invalid="errorText ? true : undefined"
          :placeholder="placeholder ?? t('journey.placeholder')"
          :value="displayValue"
          @input="onInput"
          @keydown="onKeydown"
          @blur="onBlur"
        />
        <ul
          v-show="open && results.length > 0"
          :id="listId"
          class="place-input__list"
          role="listbox"
          :aria-label="label"
        >
          <li
            v-for="(stop, index) in results"
            :id="`${id}-opt-${index}`"
            :key="stop.stop_id"
            class="place-input__option"
            :class="{ 'place-input__option--active': index === activeIndex }"
            role="option"
            :aria-selected="index === activeIndex"
            @mousedown.prevent="select(stop)"
          >
            <span class="place-input__option-name">{{ stop.name }}</span>
            <span class="place-input__option-types">{{ vehicleTypesText(stop) }}</span>
          </li>
        </ul>
      </div>
      <button
        v-if="!hideActions"
        type="button"
        class="place-input__icon-button"
        :aria-label="t('journey.myLocation')"
        :title="t('journey.myLocation')"
        :aria-busy="locating || undefined"
        :disabled="locating"
        @click="emit('locate')"
      >
        <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
          <circle cx="12" cy="12" r="4" fill="currentColor" />
          <path
            d="M12 2v3M12 19v3M2 12h3M19 12h3"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
          />
          <circle cx="12" cy="12" r="7.5" fill="none" stroke="currentColor" stroke-width="2" />
        </svg>
      </button>
      <button
        v-if="!hideActions"
        type="button"
        class="place-input__icon-button"
        :class="{ 'place-input__icon-button--on': picking }"
        :aria-label="t('journey.pickOnMap')"
        :title="t('journey.pickOnMap')"
        :data-pick-button="id"
        :aria-pressed="picking ? 'true' : 'false'"
        @click="emit('pick')"
      >
        <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
          <path
            d="M12 22s-7-6.3-7-12a7 7 0 0 1 14 0c0 5.7-7 12-7 12z"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linejoin="round"
          />
          <circle cx="12" cy="10" r="2.5" fill="currentColor" />
        </svg>
      </button>
    </div>
    <p :id="statusId" class="visually-hidden" role="status" aria-live="polite">{{ statusText }}</p>
    <p
      v-if="open && results.length === 0 && statusText"
      class="place-input__hint"
      aria-hidden="true"
    >
      {{ statusText }}
    </p>
    <p v-if="locating" class="place-input__hint">{{ t('journey.locating') }}</p>
    <p v-if="errorText" :id="errorId" class="place-input__error">{{ errorText }}</p>
  </div>
</template>

<style scoped>
.place-input {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  min-width: 0;
}

.place-input__label {
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--color-text-muted);
}

.place-input__row {
  display: flex;
  gap: var(--space-1);
  align-items: stretch;
}

.place-input__field {
  position: relative;
  flex: 1 1 auto;
  min-width: 0;
}

.place-input__input {
  width: 100%;
  min-height: 2.75rem;
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: 10px;
  background: var(--color-surface-alt);
  color: var(--color-text);
  font: inherit;
}

.place-input__input:focus {
  background: var(--color-surface);
  border-color: var(--color-primary);
}

.place-input__input[aria-invalid='true'] {
  border-color: var(--color-danger);
}

.place-input__list {
  position: absolute;
  z-index: 20;
  top: calc(100% + 4px);
  left: 0;
  right: 0;
  max-height: 16rem;
  margin: 0;
  padding: var(--space-1) 0;
  overflow-y: auto;
  list-style: none;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 10px;
  box-shadow: 0 8px 24px rgb(15 23 42 / 18%);
}

.place-input__option {
  display: flex;
  flex-direction: column;
  padding: var(--space-2) var(--space-3);
  cursor: pointer;
}

.place-input__option:hover,
.place-input__option--active {
  background: var(--color-highlight);
}

.place-input__option-name {
  font-weight: 600;
}

.place-input__option-types {
  font-size: 0.8125rem;
  color: var(--color-text-muted);
}

.place-input__icon-button {
  display: inline-flex;
  flex: none;
  align-items: center;
  justify-content: center;
  width: 2.75rem;
  min-height: 2.75rem;
  border: 1px solid var(--color-border);
  border-radius: 10px;
  background: var(--color-surface);
  color: var(--color-primary);
  cursor: pointer;
}

.place-input__icon-button:hover {
  background: var(--color-surface-alt);
}

.place-input__icon-button:disabled {
  opacity: 0.6;
  cursor: progress;
}

.place-input__icon-button--on {
  background: var(--color-primary);
  border-color: var(--color-primary);
  color: var(--color-on-primary);
}

.place-input__icon-button--on:hover {
  background: var(--color-primary-hover);
}

.place-input__hint {
  margin: 0;
  font-size: 0.8125rem;
  color: var(--color-text-muted);
}

.place-input__error {
  margin: 0;
  font-size: 0.8125rem;
  color: var(--color-danger);
}
</style>
