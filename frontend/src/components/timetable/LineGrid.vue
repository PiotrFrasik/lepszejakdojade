<script setup lang="ts">
import { computed, ref, useId } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import type { Line, LineGroup } from '@/types/api'

/**
 * Line tiles grouped by `line_groups` (display order from the API), each group in its colour,
 * with a search box that filters while typing. Lines keep the API order within a group.
 */
const props = defineProps<{
  lines: readonly Line[]
  groups: readonly LineGroup[]
}>()

const { t } = useI18n()
const searchId = useId()
const query = ref('')

function normalize(value: string): string {
  return value
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/ł/g, 'l')
    .replace(/Ł/g, 'L')
    .toLowerCase()
    .trim()
}

/** Number prefix match ("5" → 5, 50, 52) or a match anywhere in the long name. */
function matches(line: Line, q: string): boolean {
  if (!q) return true
  return normalize(line.short_name).startsWith(q) || normalize(line.long_name).includes(q)
}

const filtered = computed<Line[]>(() => {
  const q = normalize(query.value)
  return props.lines.filter((line) => matches(line, q))
})

interface GroupView {
  group: LineGroup
  lines: Line[]
}

const grouped = computed<GroupView[]>(() => {
  const known = new Set(props.groups.map((group) => group.id))
  const fallback = props.groups[0]?.id
  const byGroup = new Map<string, Line[]>()
  for (const line of filtered.value) {
    // Contract: every line has a known group; be lenient and fall back to the first one.
    const id = known.has(line.group) ? line.group : fallback
    if (id === undefined) continue
    const list = byGroup.get(id) ?? []
    list.push(line)
    byGroup.set(id, list)
  }
  return props.groups
    .map((group) => ({ group, lines: byGroup.get(group.id) ?? [] }))
    .filter((view) => view.lines.length > 0)
})

function tileLabel(line: Line): string {
  const base = line.long_name
    ? t('timetable.lineTileLabel', { line: line.short_name, name: line.long_name })
    : t('timetable.lineLabel', { line: line.short_name })
  return line.notice ? `${base}. ${noticeLabel(line)}` : base
}

function noticeLabel(line: Line): string {
  if (!line.notice) return ''
  const kind =
    line.notice.kind === 'detour' ? t('timetable.notice.detour') : t('timetable.notice.change')
  return line.notice.text ? `${kind}: ${line.notice.text}` : kind
}
</script>

<template>
  <div class="line-grid">
    <div class="line-grid__search">
      <label :for="searchId" class="line-grid__search-label">{{
        t('timetable.searchLabel')
      }}</label>
      <input
        :id="searchId"
        v-model="query"
        type="search"
        class="line-grid__search-input"
        :placeholder="t('timetable.searchPlaceholder')"
        autocomplete="off"
        enterkeyhint="search"
      />
    </div>
    <p class="visually-hidden" role="status" aria-live="polite">
      {{ query ? t('timetable.searchResults', { count: filtered.length }) : '' }}
    </p>

    <p v-if="lines.length === 0" class="line-grid__empty">{{ t('timetable.noLines') }}</p>
    <p v-else-if="grouped.length === 0" class="line-grid__empty">
      {{ t('timetable.noSearchResults', { query }) }}
    </p>

    <section
      v-for="view in grouped"
      :key="view.group.id"
      class="line-grid__group"
      :aria-labelledby="`${searchId}-${view.group.id}`"
    >
      <h2
        :id="`${searchId}-${view.group.id}`"
        class="line-grid__group-title"
        :style="{ borderLeftColor: view.group.colour }"
      >
        {{ view.group.name }}
      </h2>
      <ul class="line-grid__tiles">
        <li v-for="line in view.lines" :key="line.id">
          <RouterLink
            :to="{ name: 'timetable-line', params: { lineId: line.id } }"
            class="line-grid__tile"
            :style="{ backgroundColor: line.colour, color: line.text_colour }"
            :aria-label="tileLabel(line)"
            :title="line.long_name || undefined"
          >
            <span aria-hidden="true">{{ line.short_name }}</span>
            <span
              v-if="line.notice"
              class="line-grid__notice"
              aria-hidden="true"
              :title="noticeLabel(line)"
              >!</span
            >
          </RouterLink>
        </li>
      </ul>
    </section>
  </div>
</template>

<style scoped>
.line-grid__search {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  margin: var(--space-4) 0;
  max-width: 24rem;
}

.line-grid__search-label {
  font-weight: 600;
}

.line-grid__search-input {
  min-height: 2.75rem;
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--color-text-muted);
  border-radius: var(--radius);
  font: inherit;
}

.line-grid__empty {
  color: var(--color-text-muted);
}

.line-grid__group {
  margin-bottom: var(--space-5);
}

.line-grid__group-title {
  margin: 0 0 var(--space-3);
  padding-left: var(--space-2);
  border-left: 6px solid;
  font-size: 1.125rem;
}

.line-grid__tiles {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(3.5rem, 1fr));
  gap: var(--space-2);
  margin: 0;
  padding: 0;
  list-style: none;
}

.line-grid__tile {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 3rem;
  padding: var(--space-1);
  border-radius: var(--radius);
  font-size: 1.125rem;
  font-weight: 700;
  text-decoration: none;
  font-variant-numeric: tabular-nums;
  box-shadow: inset 0 0 0 1px rgb(0 0 0 / 12%);
}

.line-grid__tile:hover {
  filter: brightness(1.1);
}

.line-grid__notice {
  position: absolute;
  top: -0.4rem;
  right: -0.4rem;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 1.25rem;
  height: 1.25rem;
  border-radius: 50%;
  background: var(--color-warning);
  color: var(--color-text);
  font-size: 0.75rem;
  box-shadow: 0 0 0 2px var(--color-surface);
}
</style>
