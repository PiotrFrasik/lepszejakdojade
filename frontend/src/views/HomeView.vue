<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import CityMap from '@/components/CityMap.vue'
import { useCityStore } from '@/stores/city'

const { t } = useI18n()
const cityStore = useCityStore()
</script>

<template>
  <section class="home">
    <h1 class="visually-hidden">{{ t('app.tagline') }}</h1>
    <CityMap v-if="cityStore.currentCity" :city="cityStore.currentCity" class="home__map" />
  </section>
</template>

<style scoped>
.home {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  min-height: 60vh;
}

.home__map {
  flex: 1 1 auto;
}
</style>
