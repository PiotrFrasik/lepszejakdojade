<script setup lang="ts">
import { watchEffect } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterView, useRoute } from 'vue-router'

import AppFooter from '@/components/AppFooter.vue'
import AppHeader from '@/components/AppHeader.vue'
import CityPicker from '@/components/CityPicker.vue'
import { useCityStore } from '@/stores/city'

const { t } = useI18n()
const route = useRoute()
const cityStore = useCityStore()

// Keep the document title in sync with the route and the UI language.
watchEffect(() => {
  const appName = t('app.name')
  const titleKey = route.meta.titleKey
  document.title = titleKey ? `${t(titleKey)} · ${appName}` : appName
})
</script>

<template>
  <div class="app-shell" :inert="!cityStore.hasCity || undefined">
    <a class="skip-link" href="#main-content">{{ t('app.skipToContent') }}</a>
    <AppHeader />
    <main id="main-content" class="app-main" tabindex="-1">
      <RouterView />
    </main>
    <AppFooter />
  </div>
  <CityPicker v-if="!cityStore.hasCity" />
</template>

<style scoped>
.app-shell {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  min-height: 100dvh;
}

.app-main {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  min-width: 0;
}

.app-main:focus {
  outline: none;
}
</style>
