<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute, useRouter } from 'vue-router'

import CitySwitcher from '@/components/CitySwitcher.vue'
import LanguageToggle from '@/components/LanguageToggle.vue'

const { t } = useI18n()

const navItems = [
  { to: { name: 'home' }, labelKey: 'nav.home', section: false },
  { to: { name: 'journey' }, labelKey: 'nav.journey', section: true },
  { to: { name: 'timetable' }, labelKey: 'nav.timetable', section: true },
  { to: { name: 'tickets' }, labelKey: 'nav.tickets', section: true },
  { to: { name: 'assistant' }, labelKey: 'nav.assistant', section: true },
] as const

const route = useRoute()
const router = useRouter()

/** Section links (e.g. Timetables) stay highlighted on their sub-pages. */
function isSectionActive(item: (typeof navItems)[number]): boolean {
  if (!item.section) return false
  const base = router.resolve(item.to).path
  return route.path.startsWith(`${base}/`)
}
</script>

<template>
  <header class="app-header">
    <div class="app-header__bar">
      <RouterLink :to="{ name: 'home' }" class="app-header__brand" :aria-label="t('app.homeLink')">
        <img src="/favicon.svg" alt="" width="28" height="28" />
        <span class="app-header__name">{{ t('app.name') }}</span>
      </RouterLink>
      <div class="app-header__controls">
        <CitySwitcher />
        <LanguageToggle />
      </div>
    </div>
    <nav class="app-header__nav" :aria-label="t('nav.label')">
      <ul>
        <li v-for="item in navItems" :key="item.labelKey">
          <RouterLink
            :to="item.to"
            class="app-header__link"
            :class="{ 'app-header__link--active': isSectionActive(item) }"
            >{{ t(item.labelKey) }}</RouterLink
          >
        </li>
      </ul>
    </nav>
  </header>
</template>

<style scoped>
.app-header {
  background: var(--color-primary);
  color: var(--color-on-primary);
  box-shadow: 0 1px 3px rgb(0 0 0 / 20%);
  position: relative;
  z-index: 10;
}

.app-header__bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
}

.app-header__brand {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  min-width: 0;
  color: inherit;
  text-decoration: none;
  font-weight: 700;
  font-size: 1.125rem;
}

.app-header__brand img {
  flex: none;
  border-radius: 6px;
  outline: 1px solid rgb(255 255 255 / 60%);
}

.app-header__name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.app-header__controls {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.app-header__nav ul {
  display: flex;
  gap: var(--space-1);
  margin: 0;
  padding: 0 var(--space-2) var(--space-2);
  list-style: none;
  overflow-x: auto;
  scrollbar-width: thin;
}

.app-header__link {
  display: block;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius);
  color: inherit;
  text-decoration: none;
  white-space: nowrap;
  font-size: 0.9375rem;
}

.app-header__link:hover {
  background: rgb(255 255 255 / 12%);
}

.app-header__link.router-link-exact-active,
.app-header__link--active {
  background: var(--color-on-primary);
  color: var(--color-primary);
  font-weight: 600;
}

.app-header :focus-visible {
  outline: 3px solid var(--color-focus-on-primary);
  outline-offset: 2px;
}

@media (min-width: 960px) {
  .app-header {
    display: flex;
    align-items: center;
  }

  .app-header__bar {
    display: contents;
  }

  .app-header__brand {
    order: 1;
    padding: var(--space-2) var(--space-3);
  }

  .app-header__nav {
    order: 2;
    flex: 1 1 auto;
  }

  .app-header__nav ul {
    padding: var(--space-2);
  }

  .app-header__controls {
    order: 3;
    padding: var(--space-2) var(--space-3);
  }
}
</style>
