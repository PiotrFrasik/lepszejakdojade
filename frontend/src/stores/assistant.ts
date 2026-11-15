import { defineStore } from 'pinia'
import { computed, ref, shallowRef, watch } from 'vue'

import { ApiError, sendChat } from '@/api/client'
import { useCityStore } from '@/stores/city'
import type { ChatCard, ChatRequest, ChatResponse, ChatRole, CityId } from '@/types/api'
import { MAX_MESSAGE_LENGTH, buildHistory, knownCards } from '@/utils/assistant'
import { SESSION_KEYS, readSession, removeSession, writeSession } from '@/utils/storage'

/** One message shown in the chat window. */
export interface ConversationEntry {
  id: number
  role: ChatRole
  text: string
  /** Known cards of an assistant answer (always empty for user messages). */
  cards: ChatCard[]
}

export type ChatProblemKind =
  'too_long' | 'validation' | 'rate_limited' | 'unavailable' | 'network' | 'generic'

/** Why the last question failed. The question text is put back into the input. */
export interface ChatProblem {
  kind: ChatProblemKind
  /** Translated `error.message` from the API (validation errors only). */
  message?: string
  /** Epoch ms before which sending is blocked (`429` with `Retry-After`). */
  retryAt?: number
}

interface StoredConversation {
  city: CityId
  entries: ConversationEntry[]
}

const useMock = import.meta.env.DEV && import.meta.env.VITE_ASSISTANT_MOCK === 'true'

async function send(request: ChatRequest, signal: AbortSignal): Promise<ChatResponse> {
  if (useMock) {
    const { mockSendChat } = await import('@/api/assistantMock')
    return mockSendChat(request, signal)
  }
  return sendChat(request, signal)
}

function isAbortError(err: unknown): boolean {
  return (
    typeof err === 'object' && err !== null && (err as { name?: unknown }).name === 'AbortError'
  )
}

function toProblem(err: unknown): ChatProblem {
  if (err instanceof ApiError) {
    if (err.status === 0) return { kind: 'network' }
    if (err.status === 429) {
      return err.retryAfter !== null
        ? { kind: 'rate_limited', retryAt: Date.now() + err.retryAfter * 1000 }
        : { kind: 'rate_limited' }
    }
    if (err.status === 503) return { kind: 'unavailable' }
    if (err.status === 400) return { kind: 'validation', message: err.message || undefined }
  }
  return { kind: 'generic' }
}

function loadStored(city: CityId | null): ConversationEntry[] {
  const raw = readSession(SESSION_KEYS.assistantConversation)
  if (!raw || !city) return []
  try {
    const parsed = JSON.parse(raw) as Partial<StoredConversation>
    if (parsed.city !== city || !Array.isArray(parsed.entries)) return []
    return parsed.entries
      .filter(
        (e): e is ConversationEntry =>
          typeof e === 'object' &&
          e !== null &&
          (e.role === 'user' || e.role === 'assistant') &&
          typeof e.text === 'string',
      )
      .map((e, i) => ({ id: i + 1, role: e.role, text: e.text, cards: knownCards(e.cards) }))
  } catch {
    return []
  }
}

/**
 * Chat assistant conversation. The API is stateless, so the whole conversation lives here
 * (and in `sessionStorage`, so it survives a reload of the tab) and its last messages are sent
 * with every question. A conversation belongs to one city and is cleared when the city
 * changes. Also holds whether the floating chat panel is open.
 */
export const useAssistantStore = defineStore('assistant', () => {
  const cityStore = useCityStore()

  const entries = ref<ConversationEntry[]>(loadStored(cityStore.cityId))
  const draft = ref('')
  const sending = ref(false)
  const problem = shallowRef<ChatProblem | null>(null)
  const panelOpen = ref(false)

  let nextId = entries.value.length + 1
  let controller: AbortController | null = null

  const isEmpty = computed(() => entries.value.length === 0)

  function persist(): void {
    if (!cityStore.cityId || entries.value.length === 0) {
      removeSession(SESSION_KEYS.assistantConversation)
      return
    }
    const stored: StoredConversation = { city: cityStore.cityId, entries: entries.value }
    writeSession(SESSION_KEYS.assistantConversation, JSON.stringify(stored))
  }

  /**
   * Sends `text` (default: the draft) with the conversation so far. On failure the question is
   * removed from the conversation and put back into the draft, so it can be sent again.
   */
  async function ask(text: string = draft.value): Promise<void> {
    const question = text.trim()
    const city = cityStore.cityId
    if (sending.value || !question || !city) return
    if (question.length > MAX_MESSAGE_LENGTH) {
      problem.value = { kind: 'too_long' }
      return
    }

    const entry: ConversationEntry = { id: nextId++, role: 'user', text: question, cards: [] }
    entries.value.push(entry)
    draft.value = ''
    problem.value = null
    sending.value = true

    const current = new AbortController()
    controller = current
    try {
      const response = await send({ city, messages: buildHistory(entries.value) }, current.signal)
      if (current.signal.aborted) return
      entries.value.push({
        id: nextId++,
        role: 'assistant',
        text: typeof response?.message?.text === 'string' ? response.message.text : '',
        cards: knownCards(response?.cards),
      })
      persist()
    } catch (err) {
      if (current.signal.aborted || isAbortError(err)) return
      entries.value = entries.value.filter((e) => e.id !== entry.id)
      if (!draft.value) draft.value = question
      problem.value = toProblem(err)
    } finally {
      if (controller === current) {
        controller = null
        sending.value = false
      }
    }
  }

  /** Starts a new conversation (cancels a pending question). */
  function clear(): void {
    controller?.abort()
    controller = null
    sending.value = false
    entries.value = []
    problem.value = null
    nextId = 1
    persist()
  }

  function dismissProblem(): void {
    problem.value = null
  }

  function openPanel(): void {
    panelOpen.value = true
  }

  function closePanel(): void {
    panelOpen.value = false
  }

  watch(
    () => cityStore.cityId,
    (next, previous) => {
      if (previous !== null && next !== previous) {
        clear()
        draft.value = ''
      }
    },
  )

  return {
    entries,
    draft,
    sending,
    problem,
    panelOpen,
    isEmpty,
    ask,
    clear,
    dismissProblem,
    openPanel,
    closePanel,
  }
})
