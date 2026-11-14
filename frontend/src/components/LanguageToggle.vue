<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import type { AppLocale } from '@/i18n'
import { useLocaleStore } from '@/stores/locale'

// PL/EN switcher. The initial language comes from `getInitialLocale()`; account sync is #17.
const { t } = useI18n()
const localeStore = useLocaleStore()

function select(locale: AppLocale): void {
  if (locale !== localeStore.locale) localeStore.setLocale(locale)
}
</script>

<template>
  <div class="language-toggle" role="group" :aria-label="t('language.label')">
    <button
      v-for="locale in localeStore.supportedLocales"
      :key="locale"
      type="button"
      class="language-toggle__button"
      :lang="locale"
      :aria-pressed="locale === localeStore.locale"
      :title="t(`language.names.${locale}`)"
      @click="select(locale)"
    >
      {{ locale.toUpperCase()
      }}<span class="visually-hidden">&nbsp;{{ t(`language.names.${locale}`) }}</span>
    </button>
  </div>
</template>

<style scoped>
.language-toggle {
  display: inline-flex;
  border: 1px solid rgb(255 255 255 / 70%);
  border-radius: var(--radius);
  overflow: hidden;
}

.language-toggle__button {
  min-width: 2.75rem;
  min-height: 2.5rem;
  padding: var(--space-1) var(--space-2);
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  font-weight: 600;
  cursor: pointer;
}

.language-toggle__button + .language-toggle__button {
  border-left: 1px solid rgb(255 255 255 / 70%);
}

.language-toggle__button[aria-pressed='true'] {
  background: var(--color-on-primary);
  color: var(--color-primary);
}

.language-toggle__button:focus-visible {
  outline-offset: -4px;
}
</style>
