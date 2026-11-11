<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

const { t } = useI18n()
</script>

<template>
  <section class="page">
    <h1>{{ t('notFound.title') }}</h1>
    <p>{{ t('notFound.message') }}</p>
    <p>
      <RouterLink :to="{ name: 'home' }">{{ t('notFound.backHome') }}</RouterLink>
    </p>
  </section>
</template>
