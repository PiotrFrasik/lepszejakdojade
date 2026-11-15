<script setup lang="ts">
import { nextTick, useTemplateRef } from 'vue'
import { useI18n } from 'vue-i18n'

import type { VehicleType } from '@/types/api'

/**
 * Vehicle type tabs (WAI-ARIA tabs pattern with automatic activation): arrow keys, Home and End
 * move between tabs and select them; only the selected tab is in the Tab order.
 */
const props = defineProps<{
  types: readonly VehicleType[]
  modelValue: VehicleType
  /** Id of the tab panel controlled by these tabs. */
  panelId: string
  idPrefix: string
}>()

const emit = defineEmits<{ 'update:modelValue': [value: VehicleType] }>()
const { t } = useI18n()
const list = useTemplateRef<HTMLElement>('list')

function tabId(type: VehicleType): string {
  return `${props.idPrefix}-${type}`
}

async function select(index: number): Promise<void> {
  const type = props.types[index]
  if (!type) return
  emit('update:modelValue', type)
  await nextTick()
  list.value?.querySelectorAll<HTMLElement>('[role="tab"]')[index]?.focus()
}

function onKeydown(event: KeyboardEvent): void {
  const count = props.types.length
  if (count === 0) return
  const current = Math.max(0, props.types.indexOf(props.modelValue))
  let next: number | null = null
  if (event.key === 'ArrowRight') next = (current + 1) % count
  else if (event.key === 'ArrowLeft') next = (current - 1 + count) % count
  else if (event.key === 'Home') next = 0
  else if (event.key === 'End') next = count - 1
  if (next === null) return
  event.preventDefault()
  void select(next)
}
</script>

<template>
  <div
    ref="list"
    class="vehicle-tabs"
    role="tablist"
    :aria-label="t('timetable.vehicleTypesLabel')"
    @keydown="onKeydown"
  >
    <button
      v-for="(type, index) in types"
      :id="tabId(type)"
      :key="type"
      type="button"
      role="tab"
      class="vehicle-tabs__tab"
      :aria-selected="type === modelValue"
      :aria-controls="panelId"
      :tabindex="type === modelValue ? 0 : -1"
      @click="select(index)"
    >
      {{ t(`timetable.vehicleTypes.${type}`) }}
    </button>
  </div>
</template>

<style scoped>
.vehicle-tabs {
  display: flex;
  gap: var(--space-1);
  overflow-x: auto;
  border-bottom: 2px solid var(--color-border);
  scrollbar-width: thin;
}

.vehicle-tabs__tab {
  flex: 0 0 auto;
  min-height: 2.75rem;
  margin-bottom: -2px;
  padding: var(--space-2) var(--space-4);
  border: 0;
  border-bottom: 3px solid transparent;
  background: none;
  color: var(--color-text-muted);
  font: inherit;
  font-weight: 600;
  cursor: pointer;
}

.vehicle-tabs__tab:hover {
  color: var(--color-text);
}

.vehicle-tabs__tab[aria-selected='true'] {
  border-bottom-color: var(--color-primary);
  color: var(--color-primary);
}
</style>
