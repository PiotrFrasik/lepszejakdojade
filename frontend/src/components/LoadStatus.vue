<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError } from '@/api/client'

/**
 * Loading and error (with retry) states of one API resource. Renders nothing when neither
 * `loading` nor `error` applies. Error texts come from client i18n, so they follow the UI
 * language without re-fetching.
 */
const props = withDefaults(
  defineProps<{
    loading?: boolean
    error?: unknown
    /** Shown instead of the generic "not found" text for `404`. */
    notFoundText?: string
    loadingText?: string
  }>(),
  { loading: false, error: undefined, notFoundText: undefined, loadingText: undefined },
)

const emit = defineEmits<{ retry: [] }>()
const { t } = useI18n()

const errorText = computed<string>(() => {
  const err = props.error
  if (err instanceof ApiError) {
    if (err.status === 404) return props.notFoundText ?? t('errors.notFound')
    if (err.status === 0) return t('errors.network')
    if (err.status === 429) return t('errors.rateLimited')
  }
  return t('errors.generic')
})
</script>

<template>
  <div v-if="error" class="load-status load-status--error" role="alert">
    <p class="load-status__text">{{ errorText }}</p>
    <button type="button" class="button" @click="emit('retry')">{{ t('errors.retry') }}</button>
  </div>
  <p v-else-if="loading" class="load-status load-status--loading" role="status">
    <span class="load-status__spinner" aria-hidden="true"></span>
    <span>{{ loadingText ?? t('common.loading') }}</span>
  </p>
</template>

<style scoped>
.load-status {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-3);
  margin: var(--space-3) 0;
}

.load-status__text {
  margin: 0;
}

.load-status--error {
  padding: var(--space-3);
  border: 1px solid var(--color-danger);
  border-radius: var(--radius);
  color: var(--color-danger);
  background: var(--color-danger-surface);
}

.load-status--loading {
  color: var(--color-text-muted);
}

.load-status__spinner {
  width: 1rem;
  height: 1rem;
  border: 2px solid var(--color-border);
  border-top-color: var(--color-primary);
  border-radius: 50%;
  animation: load-status-spin 0.8s linear infinite;
}

@keyframes load-status-spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
