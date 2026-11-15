<script setup lang="ts">
import type { LegMode } from '@/types/api'

/** Small decorative icon of a travel mode. Always next to a text, so hidden from screen readers. */
defineProps<{ mode: LegMode | 'bike' }>()
</script>

<template>
  <svg class="mode-icon" viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
    <g
      fill="none"
      stroke="currentColor"
      stroke-width="2"
      stroke-linecap="round"
      stroke-linejoin="round"
    >
      <template v-if="mode === 'walk'">
        <circle cx="13" cy="4" r="2" fill="currentColor" stroke="none" />
        <path d="M10 22l2-7 3 3v4M9 12l2-5 4 1 2 4M11 7l-3 3v3" />
      </template>
      <template v-else-if="mode === 'bike'">
        <circle cx="6" cy="16" r="4" />
        <circle cx="18" cy="16" r="4" />
        <path d="M6 16l4-7h6l2 7M10 9l3 7h-7M14 6h3" />
      </template>
      <template v-else>
        <rect x="5" y="3" width="14" height="15" rx="3" />
        <path d="M5 11h14M9 21l-2 0M15 21h2M8 18l-1 3M16 18l1 3" />
        <circle cx="9" cy="14.5" r="0.8" fill="currentColor" />
        <circle cx="15" cy="14.5" r="0.8" fill="currentColor" />
      </template>
    </g>
  </svg>
</template>

<style scoped>
.mode-icon {
  flex: none;
  vertical-align: middle;
}
</style>
