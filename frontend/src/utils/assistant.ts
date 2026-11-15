/**
 * Pure helpers of the chat assistant: limits from the API contract, the request history and
 * filtering of response cards. No user-facing text here.
 */
import type { ChatCard, ChatMessage } from '@/types/api'

/** Max characters of one message (after trimming). */
export const MAX_MESSAGE_LENGTH = 1000
/** Max messages sent with one request; older ones are dropped by the client. */
export const MAX_HISTORY = 20

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

/**
 * Whether a response card is of a type this client knows and has the fields it renders.
 * Unknown or malformed cards are ignored, as the contract requires.
 */
export function isKnownChatCard(value: unknown): value is ChatCard {
  if (!isObject(value)) return false
  switch (value.type) {
    case 'journey':
      return (
        isObject(value.from) &&
        isObject(value.to) &&
        isObject(value.itinerary) &&
        Array.isArray(value.itinerary.legs)
      )
    case 'departures':
      return isObject(value.stop) && Array.isArray(value.departures)
    case 'stops':
      return Array.isArray(value.stops)
    default:
      return false
  }
}

/** Known cards of a response, in order. */
export function knownCards(cards: unknown): ChatCard[] {
  return Array.isArray(cards) ? cards.filter(isKnownChatCard) : []
}

/**
 * Messages for the request: the last `MAX_HISTORY` non-empty messages, trimmed and cut to
 * `MAX_MESSAGE_LENGTH` (assistant answers can be longer than the request limit). The caller
 * makes sure the last one is the user's question.
 */
export function buildHistory(messages: readonly ChatMessage[]): ChatMessage[] {
  return messages
    .map((m) => ({ role: m.role, text: m.text.trim().slice(0, MAX_MESSAGE_LENGTH) }))
    .filter((m) => m.text.length > 0)
    .slice(-MAX_HISTORY)
}
