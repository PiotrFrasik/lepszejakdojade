import type { Ticket, TicketCatalogue, TicketSuggestResponse } from '@/types/api'

/** Fictional ticket data (no real-city names or prices). */

export function ticket(over: Partial<Ticket> = {}): Ticket {
  return {
    id: 'alpha-time-60-z1',
    name: 'Hourly ticket',
    description: 'Unlimited rides for an hour in Zone A.',
    kind: 'time',
    validity_minutes: 60,
    zones: ['1'],
    reduced: false,
    price: '6.00',
    currency: 'PLN',
    prices_as_of: '2026-11-01',
    source_url: 'https://tickets.example.org/prices',
    ...over,
  }
}

export function catalogue(over: Partial<TicketCatalogue> = {}): TicketCatalogue {
  return {
    zones: [
      { id: '1', name: 'Zone A' },
      { id: '2', name: 'Zone B' },
    ],
    tickets: [
      ticket({
        id: 'alpha-single-z1',
        name: 'Single ride',
        kind: 'single',
        validity_minutes: null,
        price: '4.20',
      }),
      ticket({
        id: 'alpha-single-z1-r',
        name: 'Single ride reduced',
        kind: 'single',
        validity_minutes: null,
        reduced: true,
        price: '2.10',
      }),
      ticket({ id: 'alpha-time-20-z1', name: 'Short ticket', validity_minutes: 20, price: '3.10' }),
      ticket({ id: 'alpha-time-60-z1', name: 'Hourly ticket', validity_minutes: 60, price: '6.00' }),
      ticket({
        id: 'alpha-time-60-z1-r',
        name: 'Hourly reduced',
        validity_minutes: 60,
        reduced: true,
        price: '3.00',
      }),
      ticket({
        id: 'alpha-daily-1',
        name: 'Day ticket',
        kind: 'daily',
        validity_minutes: 1440,
        zones: ['1', '2'],
        price: '17.50',
        prices_as_of: '2026-11-05',
      }),
      ticket({
        id: 'alpha-period-7',
        name: 'Week pass',
        kind: 'period',
        validity_minutes: 10080,
        price: '48.00',
        source_url: 'https://www.pass.example.net/list',
      }),
    ],
    ...over,
  }
}

export function suggestion(over: Partial<TicketSuggestResponse> = {}): TicketSuggestResponse {
  return {
    ticket: ticket(),
    reason: 'A 60-minute ticket covers this 17-minute journey in Zone A.',
    ...over,
  }
}
