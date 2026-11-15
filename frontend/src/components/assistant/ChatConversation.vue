<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, useTemplateRef, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import ChatDeparturesCard from '@/components/assistant/ChatDeparturesCard.vue'
import ChatJourneyCard from '@/components/assistant/ChatJourneyCard.vue'
import ChatStopsCard from '@/components/assistant/ChatStopsCard.vue'
import { useAssistantStore } from '@/stores/assistant'
import { useCityStore } from '@/stores/city'
import { MAX_MESSAGE_LENGTH } from '@/utils/assistant'

/**
 * The conversation with the assistant: message list with cards, example questions when empty,
 * error messages and the question input. Used by the floating panel and the assistant page.
 * Answers are plain text and are always rendered as text (never as HTML).
 */
const props = defineProps<{ idPrefix: string }>()
const emit = defineEmits<{ navigate: [] }>()

const { t } = useI18n()
const assistant = useAssistantStore()
const cityStore = useCityStore()

const log = useTemplateRef<HTMLElement>('log')
const input = useTemplateRef<HTMLTextAreaElement>('input')

const suggestionKeys = ['departures', 'journey', 'lines'] as const

const length = computed(() => assistant.draft.length)
const tooLong = computed(() => assistant.draft.trim().length > MAX_MESSAGE_LENGTH)

// Countdown of a `429` with `Retry-After`.
const now = ref(Date.now())
let timer: ReturnType<typeof setInterval> | null = null

function stopTimer(): void {
  if (timer !== null) clearInterval(timer)
  timer = null
}

watch(
  () => assistant.problem?.retryAt,
  (retryAt) => {
    stopTimer()
    now.value = Date.now()
    if (retryAt) {
      timer = setInterval(() => {
        now.value = Date.now()
        if (now.value >= retryAt) stopTimer()
      }, 1000)
    }
  },
  { immediate: true },
)
onBeforeUnmount(stopTimer)

const retrySeconds = computed<number>(() => {
  const retryAt = assistant.problem?.retryAt
  return retryAt ? Math.max(0, Math.ceil((retryAt - now.value) / 1000)) : 0
})

const blocked = computed(() => retrySeconds.value > 0)
const canSend = computed(
  () =>
    !assistant.sending &&
    !blocked.value &&
    !tooLong.value &&
    assistant.draft.trim().length > 0 &&
    cityStore.cityId !== null,
)

const problemText = computed<string | null>(() => {
  const problem = assistant.problem
  if (!problem) return null
  switch (problem.kind) {
    case 'too_long':
      return t('assistant.tooLong', { max: MAX_MESSAGE_LENGTH })
    case 'validation':
      // `error.message` is already translated by the API (Accept-Language).
      return problem.message || t('assistant.problems.validation')
    case 'rate_limited':
      if (!problem.retryAt) return t('assistant.problems.rateLimitedWait')
      return blocked.value
        ? t('assistant.problems.rateLimited', { seconds: retrySeconds.value })
        : t('assistant.problems.rateLimitedOver')
    case 'unavailable':
      return t('assistant.problems.unavailable')
    case 'network':
      return t('errors.network')
    default:
      return t('errors.generic')
  }
})

function cardId(entryId: number, index: number): string {
  return `${props.idPrefix}-card-${entryId}-${index}`
}

function scrollToEnd(): void {
  void nextTick(() => {
    const el = log.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

function focusInput(): void {
  void nextTick(() => input.value?.focus())
}

async function submit(): Promise<void> {
  if (!canSend.value) return
  await assistant.ask()
  focusInput()
}

function onKeydown(event: KeyboardEvent): void {
  // Enter sends, Shift+Enter adds a new line (not while composing text with an IME).
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
    event.preventDefault()
    void submit()
  }
}

function askSuggestion(text: string): void {
  assistant.draft = text
  void submit()
}

function prefill(text: string): void {
  assistant.draft = text
  focusInput()
}

watch(() => [assistant.entries.length, assistant.sending], scrollToEnd, { immediate: true })

/**
 * Text for the screen-reader live region: "typing" while waiting, then the new answer or the
 * problem. Set once per event, so the ticking `Retry-After` countdown is not re-announced.
 */
const announcement = ref('')
watch(
  () => assistant.sending,
  (sending, wasSending) => {
    if (sending) {
      announcement.value = t('assistant.typing')
      return
    }
    if (!wasSending) return
    const last = assistant.entries[assistant.entries.length - 1]
    if (assistant.problem) announcement.value = problemText.value ?? ''
    else if (last?.role === 'assistant') {
      announcement.value = t('assistant.announceAnswer', {
        text: last.text || t('assistant.emptyAnswer'),
      })
    } else announcement.value = ''
  },
)
watch(
  () => assistant.problem,
  (problem) => {
    if (problem && !assistant.sending) announcement.value = problemText.value ?? ''
  },
)

defineExpose({ focusInput })
</script>

<template>
  <div class="chat">
    <div
      ref="log"
      class="chat__log"
      role="log"
      aria-live="off"
      :aria-label="t('assistant.conversationLabel')"
      tabindex="0"
    >
      <div v-if="assistant.isEmpty" class="chat__empty">
        <p class="chat__intro">
          {{
            cityStore.currentCity
              ? t('assistant.intro', { city: cityStore.currentCity.name })
              : t('assistant.introNoCity')
          }}
        </p>
        <template v-if="cityStore.currentCity">
          <h3 class="chat__suggestions-title">{{ t('assistant.suggestionsTitle') }}</h3>
          <ul class="chat__suggestions">
            <li v-for="key in suggestionKeys" :key="key">
              <button
                type="button"
                class="chat__suggestion"
                :disabled="assistant.sending || blocked"
                @click="askSuggestion(t(`assistant.suggestions.${key}`))"
              >
                {{ t(`assistant.suggestions.${key}`) }}
              </button>
            </li>
          </ul>
        </template>
      </div>

      <article
        v-for="entry in assistant.entries"
        :key="entry.id"
        class="chat__message"
        :class="`chat__message--${entry.role}`"
      >
        <h3 class="visually-hidden">
          {{ entry.role === 'user' ? t('assistant.you') : t('assistant.assistantName') }}
        </h3>
        <p class="chat__bubble">
          {{ entry.text || (entry.role === 'assistant' ? t('assistant.emptyAnswer') : '') }}
        </p>
        <div v-if="entry.cards.length > 0" class="chat__cards">
          <template v-for="(card, index) in entry.cards" :key="index">
            <ChatJourneyCard
              v-if="card.type === 'journey'"
              :card="card"
              :id-prefix="cardId(entry.id, index)"
              @navigate="emit('navigate')"
            />
            <ChatDeparturesCard
              v-else-if="card.type === 'departures'"
              :card="card"
              :id-prefix="cardId(entry.id, index)"
              @navigate="emit('navigate')"
            />
            <ChatStopsCard
              v-else-if="card.type === 'stops'"
              :card="card"
              :id-prefix="cardId(entry.id, index)"
              @prefill="prefill"
            />
          </template>
        </div>
      </article>

      <div v-if="assistant.sending" class="chat__typing" aria-hidden="true">
        <span></span><span></span><span></span>
      </div>
    </div>

    <p role="status" aria-live="polite" class="visually-hidden">{{ announcement }}</p>

    <div v-if="problemText" class="chat__problem">
      <p>{{ problemText }}</p>
      <button type="button" class="chat__dismiss" @click="assistant.dismissProblem()">
        {{ t('assistant.dismiss') }}
      </button>
    </div>

    <form class="chat__form" @submit.prevent="submit">
      <label :for="`${idPrefix}-input`" class="visually-hidden">
        {{ t('assistant.inputLabel') }}
      </label>
      <textarea
        :id="`${idPrefix}-input`"
        ref="input"
        v-model="assistant.draft"
        class="chat__input"
        rows="2"
        :maxlength="MAX_MESSAGE_LENGTH"
        :placeholder="t('assistant.placeholder')"
        :disabled="assistant.sending || !cityStore.currentCity"
        :aria-describedby="`${idPrefix}-counter`"
        @keydown="onKeydown"
      ></textarea>
      <div class="chat__form-row">
        <span
          :id="`${idPrefix}-counter`"
          class="chat__counter"
          :class="{ 'chat__counter--over': tooLong }"
        >
          {{ t('assistant.counter', { count: length, max: MAX_MESSAGE_LENGTH }) }}
        </span>
        <button type="submit" class="button button--primary" :disabled="!canSend">
          {{ t('assistant.send') }}
        </button>
      </div>
    </form>
  </div>
</template>

<style scoped>
.chat {
  display: flex;
  flex-direction: column;
  min-height: 0;
  flex: 1 1 auto;
}

.chat__log {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  gap: var(--space-3);
  min-height: 0;
  padding: var(--space-3);
  overflow-y: auto;
  overscroll-behavior: contain;
}

.chat__empty {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.chat__intro {
  margin: 0;
  color: var(--color-text-muted);
}

.chat__suggestions-title {
  margin: var(--space-2) 0 0;
  font-size: 0.875rem;
}

.chat__suggestions {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin: 0;
  padding: 0;
  list-style: none;
}

.chat__suggestion {
  width: 100%;
  min-height: 2.75rem;
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: 12px;
  background: var(--color-surface-alt);
  color: var(--color-text);
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.chat__suggestion:hover:not(:disabled) {
  border-color: var(--color-primary);
}

.chat__suggestion:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.chat__message {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.chat__message--user {
  align-items: flex-end;
}

.chat__bubble {
  max-width: 85%;
  margin: 0;
  padding: var(--space-2) var(--space-3);
  border-radius: 14px;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.chat__message--user .chat__bubble {
  border-bottom-right-radius: 4px;
  background: var(--color-primary);
  color: var(--color-on-primary);
}

.chat__message--assistant .chat__bubble {
  border-bottom-left-radius: 4px;
  background: var(--color-surface-alt);
}

.chat__cards {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.chat__typing {
  display: inline-flex;
  align-self: flex-start;
  gap: 4px;
  padding: var(--space-3);
  border-radius: 14px;
  background: var(--color-surface-alt);
}

.chat__typing span {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--color-text-muted);
  animation: chat-typing 1.2s infinite ease-in-out;
}

.chat__typing span:nth-child(2) {
  animation-delay: 0.2s;
}

.chat__typing span:nth-child(3) {
  animation-delay: 0.4s;
}

@keyframes chat-typing {
  0%,
  80%,
  100% {
    opacity: 0.3;
  }

  40% {
    opacity: 1;
  }
}

.chat__problem {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-2);
  margin: 0 var(--space-3);
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--color-danger);
  border-radius: var(--radius);
  background: var(--color-danger-surface);
  font-size: 0.875rem;
}

.chat__problem p {
  margin: 0;
}

.chat__dismiss {
  flex: none;
  padding: 0 var(--space-1);
  border: 0;
  background: none;
  color: var(--color-link);
  font: inherit;
  font-weight: 600;
  text-decoration: underline;
  cursor: pointer;
}

.chat__form {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-3);
  border-top: 1px solid var(--color-border);
  background: var(--color-surface);
}

.chat__input {
  width: 100%;
  min-height: 3rem;
  max-height: 10rem;
  padding: var(--space-2);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  font: inherit;
  resize: vertical;
}

.chat__input:disabled {
  background: var(--color-surface-alt);
}

.chat__form-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
}

.chat__counter {
  color: var(--color-text-muted);
  font-size: 0.75rem;
  font-variant-numeric: tabular-nums;
}

.chat__counter--over {
  color: var(--color-danger);
  font-weight: 700;
}
</style>
