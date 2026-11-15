<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import PlaceInput from '@/components/journey/PlaceInput.vue'
import { useCityStore } from '@/stores/city'
import { useJourneyStore, type JourneyField } from '@/stores/journey'
import { PREFERENCE_KEYS, type TimeChoice } from '@/utils/journey'

/** Search form of the journey planner (from / to, time, options). State lives in the store. */
const { t } = useI18n()
const cityStore = useCityStore()
const journey = useJourneyStore()

const TIME_CHOICES: readonly TimeChoice[] = ['now', 'depart', 'arrive']

function locationError(field: JourneyField): string | null {
  const found = journey.locationProblem
  return found && found.field === field ? t(`journey.locationErrors.${found.reason}`) : null
}

const problemText = computed(() =>
  journey.problem ? t(`journey.problems.${journey.problem}`) : '',
)

const optionsTitle = computed(() =>
  journey.activePreferences > 0
    ? t('journey.options.titleActive', { count: journey.activePreferences })
    : t('journey.options.title'),
)

function onTimeChoice(event: Event): void {
  journey.setTimeChoice((event.target as HTMLSelectElement).value as TimeChoice)
}

function onSubmit(): void {
  void journey.search()
}
</script>

<template>
  <form class="journey-form" novalidate @submit.prevent="onSubmit">
    <div class="journey-form__places">
      <PlaceInput
        id="journey-from"
        :label="t('journey.from')"
        :model-value="journey.from"
        :city="cityStore.cityId"
        :locating="journey.locating === 'from'"
        :picking="journey.picking === 'from'"
        :error-text="locationError('from')"
        @update:model-value="journey.setPlace('from', $event)"
        @locate="journey.useMyLocation('from')"
        @pick="journey.startPicking('from')"
      />
      <PlaceInput
        id="journey-to"
        :label="t('journey.to')"
        :model-value="journey.to"
        :city="cityStore.cityId"
        :locating="journey.locating === 'to'"
        :picking="journey.picking === 'to'"
        :error-text="locationError('to')"
        @update:model-value="journey.setPlace('to', $event)"
        @locate="journey.useMyLocation('to')"
        @pick="journey.startPicking('to')"
      />
      <button
        type="button"
        class="journey-form__swap"
        :aria-label="t('journey.swap')"
        :title="t('journey.swap')"
        @click="journey.swap()"
      >
        <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
          <path
            d="M7 4v14M7 18l-3-3M7 18l3-3M17 20V6M17 6l-3 3M17 6l3 3"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
        </svg>
      </button>
    </div>

    <div class="journey-form__time">
      <div class="journey-form__time-field">
        <label for="journey-time-choice" class="journey-form__label">{{
          t('journey.time.label')
        }}</label>
        <select
          id="journey-time-choice"
          class="journey-form__control"
          :value="journey.timeChoice"
          @change="onTimeChoice"
        >
          <option v-for="choice in TIME_CHOICES" :key="choice" :value="choice">
            {{ t(`journey.time.${choice}`) }}
          </option>
        </select>
      </div>
      <div v-if="journey.timeChoice !== 'now'" class="journey-form__time-field">
        <label for="journey-time" class="journey-form__label">{{
          t('journey.time.inputLabel')
        }}</label>
        <input
          id="journey-time"
          v-model="journey.localTime"
          class="journey-form__control"
          type="datetime-local"
          required
        />
      </div>
    </div>

    <details class="journey-form__options">
      <summary>{{ optionsTitle }}</summary>
      <fieldset>
        <legend class="visually-hidden">{{ t('journey.options.title') }}</legend>
        <label v-for="key in PREFERENCE_KEYS" :key="key" class="journey-form__check">
          <input
            type="checkbox"
            :checked="journey.preferences[key]"
            @change="journey.setPreference(key, ($event.target as HTMLInputElement).checked)"
          />
          {{ t(`journey.options.${key}`) }}
        </label>
      </fieldset>
    </details>

    <p v-if="problemText" class="journey-form__problem" role="alert">{{ problemText }}</p>

    <button
      type="submit"
      class="button button--primary journey-form__submit"
      :disabled="journey.status === 'loading'"
    >
      {{ t('journey.search') }}
    </button>
  </form>
</template>

<style scoped>
.journey-form {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.journey-form__places {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding-right: 2.75rem;
}

.journey-form__swap {
  position: absolute;
  top: 50%;
  right: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2.25rem;
  height: 2.25rem;
  border: 1px solid var(--color-border);
  border-radius: 50%;
  background: var(--color-surface);
  color: var(--color-primary);
  cursor: pointer;
  transform: translateY(-50%);
}

.journey-form__swap:hover {
  background: var(--color-surface-alt);
}

.journey-form__time {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.journey-form__time-field {
  display: flex;
  flex: 1 1 10rem;
  flex-direction: column;
  gap: var(--space-1);
}

.journey-form__label {
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--color-text-muted);
}

.journey-form__control {
  min-height: 2.75rem;
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: 10px;
  background: var(--color-surface);
  color: var(--color-text);
  font: inherit;
}

.journey-form__options summary {
  display: inline-block;
  padding: var(--space-1) 0;
  color: var(--color-link);
  font-weight: 600;
  cursor: pointer;
}

.journey-form__options fieldset {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin: var(--space-2) 0 0;
  padding: 0;
  border: 0;
}

.journey-form__check {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-height: 2rem;
  cursor: pointer;
}

.journey-form__check input {
  width: 1.125rem;
  height: 1.125rem;
}

.journey-form__problem {
  margin: 0;
  color: var(--color-danger);
  font-size: 0.875rem;
}

.journey-form__submit {
  width: 100%;
  min-height: 2.75rem;
  border-radius: 10px;
}
</style>
