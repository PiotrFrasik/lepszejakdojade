/**
 * Development-only stand-ins for `GET /api/v1/cities/{city}/tickets/` and
 * `POST /api/v1/cities/{city}/tickets/suggest/`, used only in the Vite dev server
 * (`import.meta.env.DEV`) started with `VITE_TICKETS_MOCK` set (before the backend endpoints
 * exist). Production builds never use or bundle them, whatever the variable says. They follow the
 * contract shapes with fictional tickets and prices. Texts are English mock data, not UI text;
 * a `[pl]` / `[en]` prefix with the request language shows that a language switch re-fetched.
 *
 * Values of `VITE_TICKETS_MOCK`:
 * - `true`: a catalogue for every city; suggest follows the contract selection rules.
 * - `empty`: zones but no tickets; suggest always returns `ticket: null`.
 * - `fail`: both endpoints answer `500`.
 * - `offline`: both endpoints fail with a network error.
 * The switch itself lives in `src/composables/useTickets.ts`.
 */
import { ApiError } from '@/api/client'
import { getCurrentLocale } from '@/i18n'
import type {
  Ticket,
  TicketCatalogue,
  TicketKind,
  TicketSuggestRequest,
  TicketSuggestResponse,
  TicketZone,
} from '@/types/api'

const ticketsMockMode: string = import.meta.env.VITE_TICKETS_MOCK ?? ''

const ZONES: TicketZone[] = [
  { id: '1', name: 'Zone A (mock)' },
  { id: '2', name: 'Zone B (mock)' },
]

interface MockTicket {
  slug: string
  kind: TicketKind
  minutes: number | null
  zones: string[]
  /** Standard price in minor currency units; the reduced variant costs half. */
  cents: number
  name: string
  description: string
}

const BASE: MockTicket[] = [
  {
    slug: 'single-z1',
    kind: 'single',
    minutes: null,
    zones: ['1'],
    cents: 400,
    name: 'Single-ride ticket (mock)',
    description: 'One ride without transfers.',
  },
  {
    slug: 'time-20-z1',
    kind: 'time',
    minutes: 20,
    zones: ['1'],
    cents: 350,
    name: '20-minute ticket (mock)',
    description: 'Unlimited rides for 20 minutes in Zone A.',
  },
  {
    slug: 'time-60-z1',
    kind: 'time',
    minutes: 60,
    zones: ['1'],
    cents: 500,
    name: '60-minute ticket (mock)',
    description: 'Unlimited rides for 60 minutes in Zone A.',
  },
  {
    slug: 'time-90-z12',
    kind: 'time',
    minutes: 90,
    zones: ['1', '2'],
    cents: 750,
    name: '90-minute ticket (mock)',
    description: 'Unlimited rides for 90 minutes in Zones A and B.',
  },
  {
    slug: 'daily-24h-z1',
    kind: 'daily',
    minutes: 1440,
    zones: ['1'],
    cents: 1500,
    name: '24-hour ticket (mock)',
    description: 'Unlimited rides for one day.',
  },
  {
    slug: 'daily-72h-z12',
    kind: 'daily',
    minutes: 4320,
    zones: ['1', '2'],
    cents: 3600,
    name: '72-hour ticket (mock)',
    description: 'Unlimited rides for three days.',
  },
  {
    slug: 'period-7d-z1',
    kind: 'period',
    minutes: 10080,
    zones: ['1'],
    cents: 5200,
    name: '7-day pass (mock)',
    description: 'Weekly pass.',
  },
]

function wait(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(resolve, ms)
    signal?.addEventListener('abort', () => {
      clearTimeout(timer)
      reject(new DOMException('Aborted', 'AbortError'))
    })
  })
}

function failIfAsked(): void {
  if (ticketsMockMode === 'fail') throw new ApiError(500, 'server_error', 'Server error.')
  if (ticketsMockMode === 'offline') throw new ApiError(0, 'network_error', 'Failed to fetch')
}

/** `[pl] ` / `[en] ` marker of the request language (the mock has no real translations). */
function marker(): string {
  return `[${getCurrentLocale()}] `
}

/** Integer minor currency units → decimal string with two places (no float arithmetic). */
function centsToDecimal(cents: number): string {
  return `${Math.floor(cents / 100)}.${String(cents % 100).padStart(2, '0')}`
}

function buildTickets(city: string): Ticket[] {
  const prefix = marker()
  const all: Ticket[] = []
  for (const base of BASE) {
    for (const reduced of [false, true]) {
      const cents = reduced ? Math.round(base.cents / 2) : base.cents
      all.push({
        id: `${city}-mock-${base.slug}${reduced ? '-reduced' : ''}`,
        name: prefix + base.name,
        description: base.description,
        kind: base.kind,
        validity_minutes: base.minutes,
        zones: [...base.zones],
        reduced,
        price: centsToDecimal(cents),
        currency: 'PLN',
        prices_as_of: '2026-11-01',
        source_url: 'https://example.com/mock-price-list',
      })
    }
  }
  return all
}

function zones(): TicketZone[] {
  const prefix = marker()
  return ZONES.map((zone) => ({ id: zone.id, name: prefix + zone.name }))
}

function priceCents(price: string): number {
  const [whole = '0', fraction = '00'] = price.split('.')
  return Number(whole) * 100 + Number(fraction.padEnd(2, '0').slice(0, 2))
}

export async function mockGetTickets(
  city: string,
  params: { reduced?: boolean } = {},
  signal?: AbortSignal,
): Promise<TicketCatalogue> {
  await wait(600, signal)
  failIfAsked()
  const tickets =
    ticketsMockMode === 'empty'
      ? []
      : buildTickets(city).filter(
          (ticket) => params.reduced === undefined || ticket.reduced === params.reduced,
        )
  return { zones: zones(), tickets }
}

export async function mockSuggestTicket(
  city: string,
  request: TicketSuggestRequest,
  signal?: AbortSignal,
): Promise<TicketSuggestResponse> {
  await wait(400, signal)
  failIfAsked()
  const wanted = request.zones ?? [ZONES[0]!.id]
  const transfers = request.transfers ?? 0
  const reduced = request.reduced ?? false
  const minutes = Math.ceil(request.duration_seconds / 60)

  const candidates =
    ticketsMockMode === 'empty'
      ? []
      : buildTickets(city).filter(
          (ticket) =>
            ticket.reduced === reduced &&
            wanted.every((zone) => ticket.zones.includes(zone)) &&
            ((ticket.kind === 'single' && transfers === 0) ||
              (ticket.kind === 'time' &&
                (ticket.validity_minutes ?? 0) * 60 >= request.duration_seconds)),
        )
  candidates.sort(
    (a, b) =>
      priceCents(a.price) - priceCents(b.price) ||
      (a.validity_minutes ?? 0) - (b.validity_minutes ?? 0) ||
      a.zones.length - b.zones.length ||
      a.id.localeCompare(b.id),
  )
  const ticket = candidates[0] ?? null
  if (!ticket) {
    return {
      ticket: null,
      reason: `${marker()}No single or time ticket covers this ${minutes}-minute journey (mock).`,
    }
  }
  return {
    ticket,
    reason: `${marker()}A ${minutes}-minute journey is covered by this ticket (mock).`,
  }
}
