<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute, useRouter } from 'vue-router'

/** Phone navigation at the bottom of the screen (hidden from 720px, where the header nav shows). */
const { t } = useI18n()
const route = useRoute()
const router = useRouter()

const tabs = [
  { name: 'home', labelKey: 'nav.journey', icon: 'M5 19l4-14 4 9 3-5 3 10' },
  { name: 'timetable', labelKey: 'nav.timetable', icon: 'M4 5h16v15H4zM4 10h16M9 5v15' },
  {
    name: 'tickets',
    labelKey: 'nav.tickets',
    icon: 'M3 7h18v4a2 2 0 0 0 0 4v4H3v-4a2 2 0 0 0 0-4zM14 7v12',
  },
  { name: 'assistant', labelKey: 'nav.assistant', icon: 'M4 5h16v11H9l-5 4zM8 10h8' },
] as const

function isActive(name: string): boolean {
  const base = router.resolve({ name }).path
  return name === 'home' ? route.path === base : route.path.startsWith(base)
}
</script>

<template>
  <nav class="tab-bar" :aria-label="t('nav.tabsLabel')">
    <ul>
      <li v-for="tab in tabs" :key="tab.name">
        <RouterLink
          :to="{ name: tab.name }"
          class="tab-bar__link"
          :class="{ 'tab-bar__link--active': isActive(tab.name) }"
          :aria-current="isActive(tab.name) ? 'page' : undefined"
        >
          <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
            <path
              :d="tab.icon"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
            />
          </svg>
          <span>{{ t(tab.labelKey) }}</span>
        </RouterLink>
      </li>
    </ul>
  </nav>
</template>

<style scoped>
.tab-bar {
  position: sticky;
  bottom: 0;
  z-index: 10;
  background: var(--color-surface);
  border-top: 1px solid var(--color-border);
  padding-bottom: env(safe-area-inset-bottom);
}

.tab-bar ul {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  margin: 0;
  padding: 0;
  list-style: none;
}

.tab-bar__link {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  min-height: 3.5rem;
  padding: var(--space-2) var(--space-1);
  color: var(--color-text-muted);
  font-size: 0.75rem;
  font-weight: 600;
  text-align: center;
  text-decoration: none;
}

.tab-bar__link--active {
  color: var(--color-primary);
}

.tab-bar__link--active svg {
  stroke-width: 2.5;
}

@media (min-width: 720px) {
  .tab-bar {
    display: none;
  }
}

@media print {
  .tab-bar {
    display: none;
  }
}
</style>
