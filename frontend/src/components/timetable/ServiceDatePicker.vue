<script setup lang="ts">
import { computed, useId } from 'vue'
import { useI18n } from 'vue-i18n'

import { useFormat } from '@/composables/useFormat'
import type { ServiceDate } from '@/types/api'
import { isServiceDate, serviceDateToDate } from '@/utils/serviceDate'

/** Date picker for the service date, with a "today" shortcut and the date spelled out. */
const props = defineProps<{
  modelValue: ServiceDate
  today: ServiceDate
}>()

const emit = defineEmits<{ 'update:modelValue': [value: ServiceDate] }>()
const { t } = useI18n()
const fmt = useFormat()
const inputId = useId()
const descriptionId = useId()

const longDate = computed(() => fmt.dateLong(serviceDateToDate(props.modelValue)))

function onInput(event: Event): void {
  const input = event.target as HTMLInputElement
  if (isServiceDate(input.value)) emit('update:modelValue', input.value)
  // Cleared or invalid: show the current date again instead of an empty field.
  else input.value = props.modelValue
}
</script>

<template>
  <div class="date-picker">
    <label :for="inputId" class="date-picker__label">{{ t('timetable.date') }}</label>
    <div class="date-picker__row">
      <input
        :id="inputId"
        type="date"
        class="date-picker__input"
        :value="modelValue"
        :aria-describedby="descriptionId"
        @change="onInput"
      />
      <button
        type="button"
        class="button"
        :disabled="modelValue === today"
        @click="emit('update:modelValue', today)"
      >
        {{ t('timetable.today') }}
      </button>
    </div>
    <p :id="descriptionId" class="date-picker__long">{{ longDate }}</p>
  </div>
</template>

<style scoped>
.date-picker {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.date-picker__label {
  font-weight: 600;
}

.date-picker__row {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.date-picker__input {
  min-height: 2.5rem;
  padding: var(--space-1) var(--space-2);
  border: 1px solid var(--color-text-muted);
  border-radius: var(--radius);
  font: inherit;
}

.date-picker__long {
  margin: 0;
  color: var(--color-text-muted);
  font-size: 0.875rem;
}
</style>
