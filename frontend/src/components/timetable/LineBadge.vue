<script setup lang="ts">
import type { LineSummary } from '@/types/api'

/** Line number chip in the line's own colours (from the API). */
withDefaults(defineProps<{ line: LineSummary; size?: 'sm' | 'md' | 'lg' }>(), { size: 'md' })
</script>

<template>
  <span
    class="line-badge"
    :class="`line-badge--${size}`"
    :style="{ backgroundColor: line.colour, color: line.text_colour }"
    >{{ line.short_name }}</span
  >
</template>

<style scoped>
.line-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 2.25em;
  padding: 0.1em 0.4em;
  border-radius: 4px;
  font-weight: 700;
  line-height: 1.3;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
  print-color-adjust: exact;
  -webkit-print-color-adjust: exact;
}

.line-badge--sm {
  font-size: 0.75rem;
}

.line-badge--md {
  font-size: 1rem;
}

.line-badge--lg {
  font-size: 1.5rem;
  padding: 0.1em 0.5em;
}
</style>
