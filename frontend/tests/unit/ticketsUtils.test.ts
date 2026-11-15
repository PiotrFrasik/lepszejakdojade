import { applyLocale } from '@/i18n'
import { formatMoney } from '@/i18n/format'
import en from '@/locales/en.json'
import pl from '@/locales/pl.json'
import {
  groupTicketsByKind,
  hasSuggestedTicket,
  isHttpUrl,
  latestPricesAsOf,
  priceListSources,
  suggestDuration,
  suggestTransfers,
  urlHost,
  validityDays,
} from '@/utils/tickets'

import { resetEnvironment } from './helpers'
import { catalogue, suggestion, ticket } from './ticketsFixtures'

const norm = (s: string) => s.replace(/[  ]/g, ' ')

beforeEach(() => resetEnvironment())

describe('formatMoney', () => {
  it('formats a decimal string for Polish', () => {
    expect(norm(formatMoney('6.00', 'PLN'))).toBe('6,00 zł')
  })

  it('formats a decimal string for English', () => {
    applyLocale('en')
    expect(norm(formatMoney('6.00', 'PLN'))).toBe('PLN 6.00')
  })

  it('always shows two decimals', () => {
    expect(norm(formatMoney('12.5', 'PLN'))).toBe('12,50 zł')
    expect(norm(formatMoney('7', 'PLN'))).toBe('7,00 zł')
  })

  it('does not suffer from float rounding', () => {
    expect(norm(formatMoney('0.10', 'PLN'))).toBe('0,10 zł')
    expect(norm(formatMoney('9007199254740993.00', 'PLN')).replace(/ /g, '')).toContain(
      '9007199254740993',
    )
  })

  it('formats thousands and negative amounts', () => {
    expect(norm(formatMoney('1234.50', 'PLN'))).toContain('1234,50')
    expect(norm(formatMoney('-1.00', 'PLN'))).toContain('1,00')
  })

  it('returns an empty string for malformed amounts', () => {
    for (const bad of ['', 'abc', '1,00', '1.', '.5', 'NaN', '1e3', '--1']) {
      expect(formatMoney(bad, 'PLN'), bad).toBe('')
    }
    expect(formatMoney(undefined as unknown as string, 'PLN')).toBe('')
    expect(formatMoney(6 as unknown as string, 'PLN')).toBe('')
  })

  it('returns an empty string for an unknown currency code', () => {
    expect(formatMoney('6.00', 'not-a-code')).toBe('')
  })

  it('formats other currencies', () => {
    applyLocale('en')
    expect(norm(formatMoney('5.00', 'EUR'))).toBe('€5.00')
  })
})

describe('groupTicketsByKind', () => {
  it('groups in kind order regardless of input order', () => {
    const groups = groupTicketsByKind([
      ticket({ id: 'a', kind: 'period' }),
      ticket({ id: 'b', kind: 'single' }),
      ticket({ id: 'c', kind: 'daily' }),
      ticket({ id: 'd', kind: 'time' }),
    ])
    expect(groups.map((g) => g.kind)).toEqual(['single', 'time', 'daily', 'period'])
  })

  it('keeps ticket order inside a group and leaves out empty groups', () => {
    const groups = groupTicketsByKind([
      ticket({ id: 't2' }),
      ticket({ id: 't1' }),
      ticket({ id: 's', kind: 'single' }),
    ])
    expect(groups.map((g) => g.kind)).toEqual(['single', 'time'])
    expect(groups[1]!.tickets.map((t) => t.id)).toEqual(['t2', 't1'])
  })

  it('puts unknown kinds last in order of appearance', () => {
    const groups = groupTicketsByKind([
      ticket({ id: 'x', kind: 'weird' as never }),
      ticket({ id: 'y', kind: 'time' }),
      ticket({ id: 'z', kind: 'odd' as never }),
    ])
    expect(groups.map((g) => g.kind)).toEqual(['time', 'weird', 'odd'])
  })

  it('returns no groups for no tickets', () => {
    expect(groupTicketsByKind([])).toEqual([])
  })
})

describe('price list helpers', () => {
  it('finds the latest prices_as_of', () => {
    expect(latestPricesAsOf(catalogue().tickets)).toBe('2026-11-05')
    expect(latestPricesAsOf([])).toBeNull()
  })

  it('lists distinct http(s) sources only', () => {
    const sources = priceListSources([
      ticket({ source_url: 'https://a.example.org/x' }),
      ticket({ source_url: 'https://a.example.org/x' }),
      ticket({ source_url: 'javascript:alert(1)' }),
      ticket({ source_url: '' }),
      ticket({ source_url: 'http://b.example.org' }),
    ])
    expect(sources).toEqual(['https://a.example.org/x', 'http://b.example.org'])
  })

  it('validates URLs', () => {
    expect(isHttpUrl('https://x.example.org')).toBe(true)
    expect(isHttpUrl('ftp://x.example.org')).toBe(false)
    expect(isHttpUrl('data:text/html,hi')).toBe(false)
    expect(isHttpUrl(null)).toBe(false)
    expect(isHttpUrl('not a url')).toBe(false)
  })

  it('extracts the host without www', () => {
    expect(urlHost('https://www.pass.example.net/list')).toBe('pass.example.net')
    expect(urlHost('nonsense')).toBe('nonsense')
  })
})

describe('validityDays', () => {
  it('converts whole days', () => {
    expect(validityDays(1440)).toBe(1)
    expect(validityDays(10080)).toBe(7)
  })

  it('returns null otherwise', () => {
    expect(validityDays(60)).toBeNull()
    expect(validityDays(1500)).toBeNull()
    expect(validityDays(null)).toBeNull()
    expect(validityDays(0)).toBeNull()
    expect(validityDays(-1440)).toBeNull()
    expect(validityDays(1440.5)).toBeNull()
  })
})

describe('suggest request helpers', () => {
  it('rounds the duration and clamps it to at least 1', () => {
    expect(suggestDuration(1020)).toBe(1020)
    expect(suggestDuration(1020.6)).toBe(1021)
    expect(suggestDuration(0)).toBe(1)
    expect(suggestDuration(0.2)).toBe(1)
    expect(suggestDuration(-5)).toBe(1)
  })

  it('does not ask for durations above 86400 or non-numbers', () => {
    expect(suggestDuration(86400)).toBe(86400)
    expect(suggestDuration(86401)).toBeNull()
    expect(suggestDuration(Number.NaN)).toBeNull()
    expect(suggestDuration(Number.POSITIVE_INFINITY)).toBeNull()
  })

  it('normalises transfers to a whole number >= 0', () => {
    expect(suggestTransfers(2)).toBe(2)
    expect(suggestTransfers(-1)).toBe(0)
    expect(suggestTransfers(1.4)).toBe(1)
    expect(suggestTransfers(Number.NaN)).toBe(0)
  })
})

describe('hasSuggestedTicket', () => {
  it('accepts a response with a ticket and a reason', () => {
    expect(hasSuggestedTicket(suggestion())).toBe(true)
  })

  it('rejects null ticket, missing parts and non-objects', () => {
    expect(hasSuggestedTicket(suggestion({ ticket: null }))).toBe(false)
    expect(hasSuggestedTicket({ ticket: ticket() })).toBe(false)
    expect(hasSuggestedTicket({ reason: 'x', ticket: { id: 'a' } })).toBe(false)
    expect(hasSuggestedTicket({ reason: 'x', ticket: { ...ticket(), price: 6 } })).toBe(false)
    expect(hasSuggestedTicket(null)).toBe(false)
    expect(hasSuggestedTicket('x')).toBe(false)
    expect(hasSuggestedTicket([])).toBe(false)
  })
})

describe('ticket locale keys', () => {
  it('have the same key sets in pl and en', () => {
    const keys = (value: unknown, prefix = ''): string[] =>
      Object.entries(value as Record<string, unknown>).flatMap(([k, v]) =>
        typeof v === 'object' && v !== null ? keys(v, `${prefix}${k}.`) : [`${prefix}${k}`],
      )
    expect(keys(en.tickets).sort()).toEqual(keys(pl.tickets).sort())
    expect(keys(en.journey.ticket).sort()).toEqual(keys(pl.journey.ticket).sort())
  })
})
