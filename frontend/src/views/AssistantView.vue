<script setup lang="ts">
import { onMounted, useTemplateRef } from 'vue'
import { useI18n } from 'vue-i18n'

import ChatConversation from '@/components/assistant/ChatConversation.vue'
import { useAssistantStore } from '@/stores/assistant'

/**
 * Assistant page (bottom tab "Assistant" on phones, header link on desktop): the same
 * conversation as the floating chat panel, filling the page.
 */
const { t } = useI18n()
const assistant = useAssistantStore()
const conversation = useTemplateRef<InstanceType<typeof ChatConversation>>('conversation')

onMounted(() => conversation.value?.focusInput())
</script>

<template>
  <section class="assistant-page" aria-labelledby="assistant-page-title">
    <div class="assistant-page__head">
      <h1 id="assistant-page-title" class="assistant-page__title">{{ t('assistant.title') }}</h1>
      <button v-if="!assistant.isEmpty" type="button" class="button" @click="assistant.clear()">
        {{ t('assistant.clear') }}
      </button>
    </div>
    <div class="assistant-page__chat">
      <ChatConversation ref="conversation" id-prefix="chat-page" />
    </div>
  </section>
</template>

<style scoped>
.assistant-page {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  width: 100%;
  max-width: 48rem;
  min-height: 0;
  margin: 0 auto;
  padding: var(--space-3) var(--space-3) 0;
}

.assistant-page__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  padding-bottom: var(--space-2);
}

.assistant-page__title {
  margin: 0;
  font-size: 1.25rem;
}

.assistant-page__chat {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  min-height: 0;
  border: 1px solid var(--color-border);
  border-bottom: 0;
  border-radius: 12px 12px 0 0;
  overflow: hidden;
}

@media (min-width: 720px) {
  .assistant-page {
    padding: var(--space-4);
  }

  .assistant-page__chat {
    border-bottom: 1px solid var(--color-border);
    border-radius: 12px;
  }
}
</style>
