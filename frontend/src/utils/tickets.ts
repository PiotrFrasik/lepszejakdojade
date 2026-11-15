import type { Ticket, TicketKind, TicketSuggestResponse } from '@/types/api'

/** Kinds in the order of the API sort (`single`, `time`, `daily`, `period`). */
export const TICKET_KINDS: readonly TicketKind[] = ['single', 'time', 'daily', 'period']

export interface TicketGroup {
  /** A known kind, or any other string the API may add later. */
  kind: string
  tickets: Ticket[]
}

/**
 * Tickets grouped by `kind`: known kinds in `TICKET_KINDS` order, then unknown kinds in order of
 * appearance. Ticket order inside a group is kept (the API already sorts it). Empty groups are
 * left out.
 */
export function groupTicketsByKind(tickets: readonly Ticket[]): TicketGroup[] {
  const byKind = new Map<string, Ticket[]>()
  for (const ticket of tickets) {
    const list = byKind.get(ticket.kind)
    if (list) list.push(ticket)
    else byKind.set(ticket.kind, [ticket])
  }
  const known = TICKET_KINDS.filter((kind) => byKind.has(kind)).map((kind) => ({
    kind,
    tickets: byKind.get(kind)!,
  }))
  const unknown = [...byKind.entries()]
    .filter(([kind]) => !(TICKET_KINDS as readonly string[]).includes(kind))
    .map(([kind, list]) => ({ kind, tickets: list }))
  return [...known, ...unknown]
}

/** Most recent `prices_as_of` (`YYYY-MM-DD` compares as text), or `null` without tickets. */
export function latestPricesAsOf(tickets: readonly Ticket[]): string | null {
  let latest: string | null = null
  for (const ticket of tickets) {
    if (ticket.prices_as_of && (latest === null || ticket.prices_as_of > latest)) {
      latest = ticket.prices_as_of
    }
  }
  return latest
}

/** Distinct official price list URLs (`http(s)` only), in order of first appearance. */
export function priceListSources(tickets: readonly Ticket[]): string[] {
  const seen = new Set<string>()
  for (const ticket of tickets) {
    if (isHttpUrl(ticket.source_url)) seen.add(ticket.source_url)
  }
  return [...seen]
}

export function isHttpUrl(value: unknown): value is string {
  if (typeof value !== 'string') return false
  try {
    const url = new URL(value)
    return url.protocol === 'https:' || url.protocol === 'http:'
  } catch {
    return false
  }
}

/** Host name of a URL without a leading `www.` (link text next to the source link). */
export function urlHost(value: string): string {
  try {
    return new URL(value).hostname.replace(/^www\./, '')
  } catch {
    return value
  }
}

/** Whole days of a validity in minutes, or `null` when it is not a whole number of days. */
export function validityDays(minutes: number | null): number | null {
  if (minutes === null || !Number.isInteger(minutes) || minutes <= 0) return null
  return minutes % 1440 === 0 ? minutes / 1440 : null
}

/** A suggest response that carries a usable ticket (anything else shows no hint). */
export function hasSuggestedTicket(
  value: unknown,
): value is TicketSuggestResponse & { ticket: Ticket } {
  if (typeof value !== 'object' || value === null) return false
  const { ticket, reason } = value as { ticket?: unknown; reason?: unknown }
  if (typeof reason !== 'string' || typeof ticket !== 'object' || ticket === null) return false
  const t = ticket as Partial<Ticket>
  return (
    typeof t.id === 'string' &&
    typeof t.name === 'string' &&
    typeof t.price === 'string' &&
    typeof t.currency === 'string'
  )
}

/**
 * `duration_seconds` for the suggest request: whole seconds, at least 1. `null` (do not ask) when
 * the value is not a number or longer than the API maximum of 86400 s.
 */
export function suggestDuration(seconds: number): number | null {
  if (!Number.isFinite(seconds)) return null
  const rounded = Math.max(1, Math.round(seconds))
  return rounded > 86400 ? null : rounded
}

/** `transfers` for the suggest request: a whole number ≥ 0. */
export function suggestTransfers(transfers: number): number {
  return Number.isFinite(transfers) ? Math.max(0, Math.round(transfers)) : 0
}
