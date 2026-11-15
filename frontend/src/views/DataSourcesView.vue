<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import { getDataSources } from '@/api/client'
import LoadStatus from '@/components/LoadStatus.vue'
import { useApiResource } from '@/composables/useApiResource'
import { useFormat } from '@/composables/useFormat'
import { useCityStore } from '@/stores/city'
import type { DataFeed, DataSourcesCity, ServiceDate } from '@/types/api'
import { serviceDateToDate } from '@/utils/serviceDate'

/**
 * Data sources page (#29): licence attributions per city, the static "processed data" statement
 * required by several licences, and when each imported feed was created, downloaded and imported.
 * City names and descriptions are translated by the API, so the page re-fetches on language change.
 */
const { t, locale } = useI18n()
const fmt = useFormat()
const cityStore = useCityStore()

const resource = useApiResource(
  () => ({ locale: locale.value }),
  (_key, signal) => getDataSources(signal),
  { keepPrevious: true },
)

/** All cities from the response, the selected one first (otherwise in API order). */
const cities = computed<DataSourcesCity[]>(() => {
  const list = resource.data.value?.cities ?? []
  const current = cityStore.cityId
  return [...list].sort((a, b) => Number(b.id === current) - Number(a.id === current))
})

const loading = computed(() => resource.status.value === 'loading' && !resource.data.value)

function dateTimeOrUnknown(value: string | null): string {
  return (value && fmt.dateTime(value)) || t('dataSources.unknown')
}

function serviceDate(value: ServiceDate | null): string {
  return (value && fmt.date(serviceDateToDate(value))) || t('dataSources.unknown')
}

function servicePeriod(feed: DataFeed): string {
  if (!feed.service_start_date && !feed.service_end_date) return t('dataSources.unknown')
  return t('dataSources.servicePeriodRange', {
    start: serviceDate(feed.service_start_date),
    end: serviceDate(feed.service_end_date),
  })
}

function headingId(city: DataSourcesCity): string {
  return `data-sources-city-${city.id}`
}
</script>

<template>
  <section class="page data-sources" aria-labelledby="data-sources-title">
    <h1 id="data-sources-title">{{ t('dataSources.title') }}</h1>
    <p>{{ t('dataSources.intro') }}</p>

    <aside class="data-sources__notice" aria-labelledby="data-sources-processed">
      <h2 id="data-sources-processed" class="data-sources__notice-title">
        {{ t('dataSources.processedTitle') }}
      </h2>
      <p>{{ t('dataSources.processed') }}</p>
    </aside>

    <LoadStatus
      :loading="loading"
      :error="resource.error.value"
      :loading-text="t('dataSources.loading')"
      @retry="resource.reload"
    />

    <template v-if="resource.data.value">
      <p v-if="cities.length === 0" class="data-sources__empty">
        {{ t('dataSources.noCities') }}
      </p>

      <section
        v-for="city in cities"
        :key="city.id"
        class="data-sources__city"
        :aria-labelledby="headingId(city)"
      >
        <h2 :id="headingId(city)">{{ city.name }}</h2>

        <h3>{{ t('dataSources.sourcesHeading') }}</h3>
        <p v-if="city.sources.length === 0" class="data-sources__empty">
          {{ t('dataSources.noSources') }}
        </p>
        <ul v-else class="data-sources__list">
          <li
            v-for="source in city.sources"
            :key="`${source.name}|${source.url}`"
            class="data-sources__card"
          >
            <a
              :href="source.url"
              target="_blank"
              rel="noopener noreferrer"
              class="data-sources__name"
            >
              {{ source.name }}
              <span class="visually-hidden">{{ t('dataSources.newTab') }}</span>
            </a>
            <p v-if="source.description" class="data-sources__description">
              {{ source.description }}
            </p>
            <p class="data-sources__licence">
              {{ t('dataSources.licence') }}
              <a
                v-if="source.licence && source.licence_url"
                :href="source.licence_url"
                target="_blank"
                rel="noopener noreferrer license"
              >
                {{ source.licence }}
                <span class="visually-hidden">{{ t('dataSources.newTab') }}</span>
              </a>
              <a
                v-else-if="source.licence_url"
                :href="source.licence_url"
                target="_blank"
                rel="noopener noreferrer license"
              >
                {{ source.licence_url }}
                <span class="visually-hidden">{{ t('dataSources.newTab') }}</span>
              </a>
              <span v-else>{{ source.licence ?? t('dataSources.unknown') }}</span>
            </p>
          </li>
        </ul>

        <h3>{{ t('dataSources.freshnessHeading') }}</h3>
        <p v-if="city.feeds.length === 0" class="data-sources__empty">
          {{ t('dataSources.noFeeds') }}
        </p>
        <ul v-else class="data-sources__list">
          <li v-for="feed in city.feeds" :key="feed.feed_id" class="data-sources__card">
            <dl class="data-sources__facts">
              <dt>{{ t('dataSources.publisher') }}</dt>
              <dd>{{ feed.publisher_name || t('dataSources.unknown') }}</dd>
              <dt>{{ t('dataSources.feedId') }}</dt>
              <dd>
                <code>{{ feed.feed_id }}</code>
              </dd>
              <dt>{{ t('dataSources.created') }}</dt>
              <dd>{{ dateTimeOrUnknown(feed.last_modified) }}</dd>
              <dt>{{ t('dataSources.downloaded') }}</dt>
              <dd>{{ dateTimeOrUnknown(feed.downloaded_at) }}</dd>
              <dt>{{ t('dataSources.imported') }}</dt>
              <dd>{{ dateTimeOrUnknown(feed.imported_at) }}</dd>
              <dt>{{ t('dataSources.servicePeriod') }}</dt>
              <dd>{{ servicePeriod(feed) }}</dd>
            </dl>
          </li>
        </ul>
      </section>
    </template>
  </section>
</template>

<style scoped>
.data-sources__notice {
  margin: var(--space-4) 0;
  padding: var(--space-3) var(--space-4);
  border-left: 4px solid var(--color-warning);
  border-radius: var(--radius);
  background: var(--color-highlight);
}

.data-sources__notice p {
  margin: 0;
}

.data-sources__notice-title {
  margin: 0 0 var(--space-2);
  font-size: 1rem;
}

.data-sources__city {
  margin-top: var(--space-6);
}

.data-sources__city h2 {
  margin-bottom: var(--space-3);
  font-size: 1.25rem;
}

.data-sources__city h3 {
  margin: var(--space-4) 0 var(--space-2);
  font-size: 1rem;
}

.data-sources__list {
  display: grid;
  gap: var(--space-3);
  margin: 0;
  padding: 0;
  list-style: none;
}

.data-sources__card {
  padding: var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  background: var(--color-surface);
  overflow-wrap: anywhere;
}

.data-sources__name {
  font-weight: 600;
}

.data-sources__description,
.data-sources__licence {
  margin: var(--space-2) 0 0;
}

.data-sources__licence {
  color: var(--color-text-muted);
}

.data-sources__facts {
  display: grid;
  grid-template-columns: 1fr;
  gap: 0 var(--space-3);
  margin: 0;
}

.data-sources__facts dt {
  color: var(--color-text-muted);
  font-size: 0.875rem;
}

.data-sources__facts dd {
  margin: 0 0 var(--space-2);
}

.data-sources__empty {
  color: var(--color-text-muted);
}

@media (min-width: 40rem) {
  .data-sources__facts {
    grid-template-columns: max-content 1fr;
  }

  .data-sources__facts dt,
  .data-sources__facts dd {
    margin: 0;
    padding: var(--space-1) 0;
  }
}
</style>
