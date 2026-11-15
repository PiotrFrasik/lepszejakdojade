<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, useTemplateRef, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import JourneyForm from '@/components/journey/JourneyForm.vue'
import JourneyMap from '@/components/journey/JourneyMap.vue'
import JourneyResults from '@/components/journey/JourneyResults.vue'
import { useCityStore } from '@/stores/city'
import { useJourneyStore } from '@/stores/journey'

/**
 * Home = journey planner: a full-screen map with a floating panel holding the whole flow
 * (search form, "Your journeys", results). Desktop: rounded island on the left; phone: panel
 * on top of the map.
 */
const { t } = useI18n()
const cityStore = useCityStore()
const journey = useJourneyStore()

const DESKTOP_QUERY = '(min-width: 900px)'
const isDesktop = ref(false)
const panelHeight = ref(0)
const panelWidth = ref(0)
const panel = useTemplateRef<HTMLElement>('panel')
let media: MediaQueryList | null = null
let observer: ResizeObserver | null = null

function onMediaChange(event: MediaQueryListEvent): void {
  isDesktop.value = event.matches
}

/** Keeps fitted routes clear of the panel covering part of the map. */
const mapPadding = computed(() =>
  isDesktop.value
    ? { left: panelWidth.value + 48, top: 48, right: 48, bottom: 48 }
    : { top: Math.min(panelHeight.value + 24, 320), left: 32, right: 32, bottom: 32 },
)

const pickingText = computed(() =>
  journey.picking === 'from' ? t('journey.pickingFrom') : t('journey.pickingTo'),
)

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape' && journey.picking) journey.cancelPicking()
}

onMounted(() => {
  if (typeof window.matchMedia === 'function') {
    media = window.matchMedia(DESKTOP_QUERY)
    isDesktop.value = media.matches
    media.addEventListener?.('change', onMediaChange)
  }
  if (typeof ResizeObserver !== 'undefined' && panel.value) {
    observer = new ResizeObserver(([entry]) => {
      if (!entry) return
      panelHeight.value = entry.contentRect.height
      panelWidth.value = entry.contentRect.width
    })
    observer.observe(panel.value)
  }
  window.addEventListener('keydown', onKeydown)
})

onBeforeUnmount(() => {
  media?.removeEventListener?.('change', onMediaChange)
  observer?.disconnect()
  window.removeEventListener('keydown', onKeydown)
})

// Picking hides the form: move focus to the banner's Cancel button, and back to the field's
// "choose on the map" button when picking ends.
const cancelButton = useTemplateRef<HTMLButtonElement>('cancelButton')
watch(
  () => journey.picking,
  async (field, previous) => {
    await nextTick()
    if (field) cancelButton.value?.focus()
    else if (previous) {
      panel.value
        ?.querySelector<HTMLButtonElement>(`[data-pick-button="journey-${previous}"]`)
        ?.focus()
    }
  },
)

// Leaving the page while picking would leave the map in a mode nobody can see.
watch(
  () => cityStore.cityId,
  () => journey.cancelPicking(),
)
onBeforeUnmount(() => journey.cancelPicking())
</script>

<template>
  <section class="home">
    <h1 class="visually-hidden">{{ t('journey.title') }}</h1>
    <JourneyMap
      v-if="cityStore.currentCity"
      class="home__map"
      :city="cityStore.currentCity"
      :itinerary="journey.status === 'ready' ? journey.selectedItinerary : null"
      :from="journey.from"
      :to="journey.to"
      :picking="journey.picking !== null"
      :padding="mapPadding"
      @pick="journey.pickPoint"
    />

    <div ref="panel" class="home__panel" :aria-label="t('journey.panelLabel')" role="region">
      <div v-if="journey.picking" class="home__picking" role="status">
        <p>{{ pickingText }}</p>
        <button ref="cancelButton" type="button" class="button" @click="journey.cancelPicking()">
          {{ t('journey.cancelPicking') }}
        </button>
      </div>
      <div v-show="!journey.picking" class="home__panel-body">
        <h2 class="home__title">{{ t('journey.title') }}</h2>
        <JourneyForm />
        <JourneyResults v-if="journey.status !== 'idle'" />
        <details v-else class="home__yours" open>
          <summary>{{ t('journey.yourJourneys.title') }}</summary>
          <p>{{ t('journey.yourJourneys.empty') }}</p>
        </details>
      </div>
    </div>
  </section>
</template>

<style scoped>
.home {
  position: relative;
  flex: 1 1 auto;
  min-height: 0;
  overflow: hidden;
}

.home__map {
  position: absolute;
  inset: 0;
}

.home__panel {
  position: absolute;
  z-index: 5;
  top: 0;
  left: 0;
  right: 0;
  max-height: 62%;
  overflow-y: auto;
  overscroll-behavior: contain;
  background: var(--color-surface);
  border-radius: 0 0 18px 18px;
  box-shadow: 0 6px 20px rgb(15 23 42 / 18%);
}

.home__panel-body {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-3) var(--space-4);
}

.home__title {
  margin: 0;
  font-size: 1.125rem;
}

.home__picking {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  padding: var(--space-3);
}

.home__picking p {
  margin: 0;
  font-weight: 600;
}

.home__yours {
  padding: var(--space-3);
  border-radius: 12px;
  background: var(--color-surface-alt);
}

.home__yours summary {
  font-weight: 700;
  cursor: pointer;
}

.home__yours p {
  margin: var(--space-2) 0 0;
  color: var(--color-text-muted);
  font-size: 0.875rem;
}

@media (min-width: 900px) {
  .home__panel {
    top: var(--space-4);
    left: var(--space-4);
    right: auto;
    bottom: auto;
    width: 26rem;
    max-height: calc(100% - 2 * var(--space-4));
    border-radius: 18px;
  }

  .home__panel-body {
    padding: var(--space-4);
  }
}
</style>
