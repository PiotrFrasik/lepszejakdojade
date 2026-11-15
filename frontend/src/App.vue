<script setup lang="ts">
import { computed, watchEffect } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterView, useRoute } from 'vue-router'

import AppFooter from '@/components/AppFooter.vue'
import AppHeader from '@/components/AppHeader.vue'
import BottomTabBar from '@/components/BottomTabBar.vue'
import CityPicker from '@/components/CityPicker.vue'
import { useCityStore } from '@/stores/city'

const { t } = useI18n()
const route = useRoute()
const cityStore = useCityStore()
cityStore.init()

const fullscreen = computed(() => route.meta.fullscreen === true)

// Keep the document title in sync with the route and the UI language.
watchEffect(() => {
  const appName = t('app.name')
  const titleKey = route.meta.titleKey
  document.title = titleKey ? `${t(titleKey)} · ${appName}` : appName
})
</script>

<template>
  <div
    class="app-shell"
    :class="{ 'app-shell--fullscreen': fullscreen }"
    :inert="cityStore.needsPicker || undefined"
  >
    <a class="skip-link" href="#main-content">{{ t('app.skipToContent') }}</a>
    <AppHeader />
    <main id="main-content" class="app-main" tabindex="-1">
      <RouterView />
    </main>
    <AppFooter v-if="!fullscreen" />
    <BottomTabBar />
  </div>
  <CityPicker v-if="cityStore.needsPicker" />
</template>

<style scoped>
.app-shell {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  min-height: 100dvh;
}

/* Full-screen map pages: the shell is exactly the viewport and the page itself never scrolls. */
.app-shell--fullscreen {
  height: 100vh;
  height: 100dvh;
  overflow: hidden;
}

.app-main {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  min-width: 0;
}

.app-shell--fullscreen .app-main {
  min-height: 0;
}

.app-main:focus {
  outline: none;
}
</style>
