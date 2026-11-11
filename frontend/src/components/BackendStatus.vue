<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { getHealth } from '@/api/client'

/** Non-blocking backend health indicator (`GET /api/v1/health/`). */
type Status = 'checking' | 'ok' | 'degraded' | 'unavailable'

const { t } = useI18n()
const status = ref<Status>('checking')
const version = ref<string | null>(null)
let controller: AbortController | null = null

async function check(): Promise<void> {
  controller?.abort()
  controller = new AbortController()
  status.value = 'checking'
  try {
    const health = await getHealth(controller.signal)
    version.value = health.version ?? null
    status.value = health.status === 'ok' ? 'ok' : 'degraded'
  } catch (err) {
    if ((err as { name?: unknown })?.name === 'AbortError') return
    version.value = null
    status.value = 'unavailable'
  }
}

const label = computed(() => t(`status.${status.value}`))

onMounted(() => {
  void check()
})

onBeforeUnmount(() => {
  controller?.abort()
})
</script>

<template>
  <p class="backend-status" :data-status="status" role="status">
    <span class="backend-status__dot" aria-hidden="true"></span>
    <span class="visually-hidden">{{ t('status.label') }}:</span>
    <span>{{ label }}</span>
    <span v-if="version && status !== 'unavailable'" class="backend-status__version">
      ({{ version }})
    </span>
  </p>
</template>

<style scoped>
.backend-status {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  margin: 0;
  font-size: 0.875rem;
}

.backend-status__dot {
  width: 0.625rem;
  height: 0.625rem;
  border-radius: 50%;
  background: var(--color-text-muted);
}

[data-status='ok'] .backend-status__dot {
  background: var(--color-success);
}

[data-status='degraded'] .backend-status__dot {
  background: var(--color-warning);
}

[data-status='unavailable'] .backend-status__dot {
  background: var(--color-danger);
}

.backend-status__version {
  color: var(--color-text-muted);
}
</style>
