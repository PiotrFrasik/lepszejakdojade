<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import BackendStatus from '@/components/BackendStatus.vue'

const { t } = useI18n()
</script>

<template>
  <footer class="app-footer">
    <p class="app-footer__notice">{{ t('footer.demoNotice') }}</p>
    <div class="app-footer__row">
      <RouterLink :to="{ name: 'data-sources' }" class="app-footer__link">
        {{ t('footer.dataSources') }}
      </RouterLink>
      <BackendStatus />
    </div>
  </footer>
</template>

<style scoped>
.app-footer {
  padding: var(--space-3);
  border-top: 1px solid var(--color-border);
  background: var(--color-surface-alt);
  color: var(--color-text);
  font-size: 0.875rem;
}

.app-footer__notice {
  margin: 0 0 var(--space-2);
  color: var(--color-text-muted);
}

.app-footer__row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2) var(--space-4);
}

.app-footer__link {
  color: var(--color-link);
}
</style>
