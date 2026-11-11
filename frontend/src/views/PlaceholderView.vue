<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'

/** Temporary page for sections that are not built yet. Title comes from `route.meta.titleKey`. */
const { t } = useI18n()
const route = useRoute()

const title = computed(() => (route.meta.titleKey ? t(route.meta.titleKey) : t('app.name')))
</script>

<template>
  <section class="page">
    <h1>{{ title }}</h1>
    <p>{{ t('placeholder.comingSoon') }}</p>
  </section>
</template>
