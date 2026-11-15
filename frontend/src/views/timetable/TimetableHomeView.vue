<script setup lang="ts">
import { computed, useId, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import { getLines } from '@/api/client'
import PlaceInput from '@/components/journey/PlaceInput.vue'
import LoadStatus from '@/components/LoadStatus.vue'
import LineGrid from '@/components/timetable/LineGrid.vue'
import VehicleTypeTabs from '@/components/timetable/VehicleTypeTabs.vue'
import { useApiResource } from '@/composables/useApiResource'
import { useCityStore } from '@/stores/city'
import type { VehicleType } from '@/types/api'
import type { PlaceValue } from '@/utils/journey'
import { STORAGE_KEYS, readStorage, writeStorage } from '@/utils/storage'

/**
 * Timetable step 1 and 2: vehicle type tabs (only the city's types, last tab remembered) and
 * the line tile grid. The tab is also in the URL (`?type=bus`) so links are shareable.
 */
const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const cityStore = useCityStore()
const idPrefix = useId()
const panelId = `${idPrefix}-panel`
const stopSearchId = `${idPrefix}-stop`

const details = computed(() => cityStore.currentCityDetails)
const vehicleTypes = computed<readonly VehicleType[]>(() => details.value?.vehicle_types ?? [])

function pick(value: unknown): VehicleType | null {
  const raw = Array.isArray(value) ? value[0] : value
  return typeof raw === 'string' && (vehicleTypes.value as readonly string[]).includes(raw)
    ? (raw as VehicleType)
    : null
}

/** URL first, then the remembered tab, then the city's first type. */
const selectedType = computed<VehicleType | null>(
  () =>
    pick(route.query.type) ??
    pick(readStorage(STORAGE_KEYS.timetableVehicleType)) ??
    vehicleTypes.value[0] ??
    null,
)

function selectType(type: VehicleType): void {
  writeStorage(STORAGE_KEYS.timetableVehicleType, type)
  void router.replace({ query: { ...route.query, type } })
}

// Keep the URL in sync with the shown tab (e.g. after a city switch drops a missing type).
watch(selectedType, (type) => {
  if (type && route.query.type !== undefined && route.query.type !== type) {
    void router.replace({ query: { ...route.query, type } })
  }
})

const lines = useApiResource(
  () =>
    cityStore.cityId && selectedType.value
      ? { city: cityStore.cityId, type: selectedType.value }
      : null,
  (key, signal) => getLines(key.city, key.type, signal),
)

/** Entry from a stop: choosing a stop opens its departures board. */
function openStop(place: PlaceValue | null): void {
  if (place?.source === 'stop' && place.stopId) {
    void router.push({ name: 'timetable-stop-departures', params: { stopId: place.stopId } })
  }
}

/** Without details and without an error the details are (about to be) loading. */
const detailsLoading = computed(() => !details.value && cityStore.detailsError === null)

function retryDetails(): void {
  if (cityStore.cityId) void cityStore.loadDetails(cityStore.cityId)
}
</script>

<template>
  <section class="page timetable-home">
    <h1>{{ t('timetable.title') }}</h1>

    <section
      v-if="cityStore.cityId"
      class="timetable-home__stop-search"
      :aria-labelledby="`${stopSearchId}-title`"
    >
      <h2 :id="`${stopSearchId}-title`" class="timetable-home__subtitle">
        {{ t('timetable.departures.searchTitle') }}
      </h2>
      <PlaceInput
        :id="stopSearchId"
        :label="t('timetable.departures.searchLabel')"
        :placeholder="t('timetable.departures.searchPlaceholder')"
        :model-value="null"
        :city="cityStore.cityId"
        hide-actions
        @update:model-value="openStop"
      />
    </section>

    <LoadStatus
      v-if="!details"
      :loading="detailsLoading"
      :error="cityStore.detailsError"
      @retry="retryDetails"
    />

    <template v-else>
      <p v-if="vehicleTypes.length === 0" class="timetable-home__empty">
        {{ t('timetable.noVehicleTypes') }}
      </p>
      <template v-else-if="selectedType">
        <VehicleTypeTabs
          :types="vehicleTypes"
          :model-value="selectedType"
          :panel-id="panelId"
          :id-prefix="idPrefix"
          @update:model-value="selectType"
        />
        <div
          :id="panelId"
          role="tabpanel"
          :aria-labelledby="`${idPrefix}-${selectedType}`"
          class="timetable-home__panel"
        >
          <LoadStatus
            :loading="lines.status.value === 'loading'"
            :error="lines.error.value"
            :loading-text="t('timetable.loadingLines')"
            @retry="lines.reload"
          />
          <LineGrid
            v-if="lines.data.value"
            :lines="lines.data.value"
            :groups="details.line_groups"
          />
        </div>
      </template>
    </template>
  </section>
</template>

<style scoped>
.timetable-home__stop-search {
  max-width: 28rem;
  margin-bottom: var(--space-5);
}

.timetable-home__subtitle {
  margin: 0 0 var(--space-2);
  font-size: 1.125rem;
}

.timetable-home__empty {
  color: var(--color-text-muted);
}

.timetable-home__panel:focus-visible {
  outline-offset: 4px;
}
</style>
