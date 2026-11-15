<script setup lang="ts">
import { computed, nextTick, useTemplateRef, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'

import ChatConversation from '@/components/assistant/ChatConversation.vue'
import { useAssistantStore } from '@/stores/assistant'

/**
 * Chat launcher button and the floating chat panel, available on every page except the
 * assistant page itself. Desktop: a panel in the bottom-right corner; phone (`modal`): a
 * full-screen sheet over the page and the bottom tab bar (`App.vue` makes the page inert).
 * Escape closes it and focus returns to the launcher.
 */
const props = defineProps<{ modal: boolean }>()

const { t } = useI18n()
const route = useRoute()
const assistant = useAssistantStore()

const launcher = useTemplateRef<HTMLButtonElement>('launcher')
const conversation = useTemplateRef<InstanceType<typeof ChatConversation>>('conversation')

const onAssistantPage = computed(() => route.name === 'assistant')
/** Full-screen map pages have map controls in the bottom-right corner. */
const raised = computed(() => route.meta.fullscreen === true)

function open(): void {
  assistant.openPanel()
  void nextTick(() => conversation.value?.focusInput())
}

function close(returnFocus = true): void {
  assistant.closePanel()
  if (returnFocus) void nextTick(() => launcher.value?.focus())
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape') {
    event.stopPropagation()
    close()
  }
}

// The assistant page shows the same conversation, so the panel is not needed there.
watch(onAssistantPage, (value) => {
  if (value) assistant.closePanel()
})
</script>

<template>
  <template v-if="!onAssistantPage">
    <button
      v-if="!assistant.panelOpen"
      ref="launcher"
      type="button"
      class="chat-launcher no-print"
      :class="{ 'chat-launcher--raised': raised }"
      aria-haspopup="dialog"
      :aria-label="t('assistant.open')"
      @click="open"
    >
      <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
        <path
          d="M4 5h16v11H9l-5 4zM8 10h8"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
      </svg>
      <span class="chat-launcher__label">{{ t('assistant.title') }}</span>
    </button>

    <section
      v-else
      class="chat-panel no-print"
      :class="{ 'chat-panel--modal': props.modal }"
      role="dialog"
      :aria-modal="props.modal ? 'true' : undefined"
      aria-labelledby="chat-panel-title"
      @keydown="onKeydown"
    >
      <header class="chat-panel__head">
        <h2 id="chat-panel-title" class="chat-panel__title">{{ t('assistant.title') }}</h2>
        <button
          v-if="!assistant.isEmpty"
          type="button"
          class="chat-panel__action"
          @click="assistant.clear()"
        >
          {{ t('assistant.clear') }}
        </button>
        <button
          type="button"
          class="chat-panel__close"
          :aria-label="t('assistant.close')"
          @click="close()"
        >
          <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
            <path
              d="M6 6l12 12M18 6L6 18"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
            />
          </svg>
        </button>
      </header>
      <ChatConversation ref="conversation" id-prefix="chat-panel" @navigate="close(false)" />
    </section>
  </template>
</template>

<style scoped>
.chat-launcher {
  position: fixed;
  z-index: 900;
  right: var(--space-3);
  /* Above the bottom tab bar (3.5rem + safe area) on phones. */
  bottom: calc(3.5rem + env(safe-area-inset-bottom) + var(--space-3));
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  min-height: 3.25rem;
  padding: var(--space-2) var(--space-4);
  border: 0;
  border-radius: 999px;
  background: var(--color-primary);
  color: var(--color-on-primary);
  font: inherit;
  font-weight: 700;
  box-shadow: 0 6px 18px rgb(15 23 42 / 28%);
  cursor: pointer;
}

.chat-launcher:hover {
  background: var(--color-primary-hover);
}

.chat-launcher:focus-visible {
  outline-color: var(--color-focus-on-primary);
  outline-offset: 3px;
}

/* Clear of the map zoom buttons and attribution in the bottom-right corner. */
.chat-launcher--raised {
  bottom: calc(3.5rem + env(safe-area-inset-bottom) + 7rem);
}

/* Phones: icon only (the accessible name comes from `aria-label`). */
.chat-launcher__label {
  display: none;
}

.chat-panel {
  position: fixed;
  z-index: 950;
  right: var(--space-4);
  bottom: var(--space-4);
  display: flex;
  flex-direction: column;
  width: min(26rem, calc(100vw - 2 * var(--space-4)));
  height: min(40rem, calc(100dvh - 6rem));
  border: 1px solid var(--color-border);
  border-radius: 18px;
  background: var(--color-surface);
  box-shadow: 0 12px 32px rgb(15 23 42 / 28%);
  overflow: hidden;
}

/* Phone: full-screen sheet covering the header and the bottom tab bar. */
.chat-panel--modal {
  inset: 0;
  width: auto;
  height: auto;
  border: 0;
  border-radius: 0;
  padding-bottom: env(safe-area-inset-bottom);
}

.chat-panel__head {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-2) var(--space-2) var(--space-4);
  background: var(--color-primary);
  color: var(--color-on-primary);
}

.chat-panel__title {
  flex: 1 1 auto;
  margin: 0;
  font-size: 1.0625rem;
}

.chat-panel__action,
.chat-panel__close {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 2.5rem;
  min-width: 2.5rem;
  padding: var(--space-1) var(--space-2);
  border: 0;
  border-radius: var(--radius);
  background: none;
  color: inherit;
  font: inherit;
  font-weight: 600;
  cursor: pointer;
}

.chat-panel__action:hover,
.chat-panel__close:hover {
  background: rgb(255 255 255 / 15%);
}

.chat-panel__action:focus-visible,
.chat-panel__close:focus-visible {
  outline-color: var(--color-focus-on-primary);
}

@media (min-width: 720px) {
  .chat-launcher {
    right: var(--space-4);
    bottom: var(--space-4);
  }

  .chat-launcher--raised {
    bottom: 7.5rem;
  }

  .chat-launcher__label {
    display: inline;
  }
}
</style>
