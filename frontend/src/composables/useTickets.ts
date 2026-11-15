import { getTickets, suggestTicket } from '@/api/client'
import type {
  CityId,
  TicketCatalogue,
  TicketSuggestRequest,
  TicketSuggestResponse,
} from '@/types/api'

/**
 * Dev-only switch to the fictional ticket data in `src/api/ticketsMock.ts`
 * (`VITE_TICKETS_MOCK=true|empty|fail|offline`). Statically false in production builds, so the
 * mock module is never bundled there.
 */
const useMock =
  import.meta.env.DEV &&
  ['true', 'empty', 'fail', 'offline'].includes(String(import.meta.env.VITE_TICKETS_MOCK))

/** `GET /cities/{city}/tickets/` (or the dev mock). */
export async function fetchTicketCatalogue(
  city: CityId,
  params: { reduced?: boolean },
  signal: AbortSignal,
): Promise<TicketCatalogue> {
  if (useMock) {
    const { mockGetTickets } = await import('@/api/ticketsMock')
    return mockGetTickets(city, params, signal)
  }
  return getTickets(city, params, signal)
}

/** `POST /cities/{city}/tickets/suggest/` (or the dev mock). */
export async function fetchTicketSuggestion(
  city: CityId,
  request: TicketSuggestRequest,
  signal: AbortSignal,
): Promise<TicketSuggestResponse> {
  if (useMock) {
    const { mockSuggestTicket } = await import('@/api/ticketsMock')
    return mockSuggestTicket(city, request, signal)
  }
  return suggestTicket(city, request, signal)
}
