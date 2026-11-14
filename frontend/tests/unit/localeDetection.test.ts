import { DEFAULT_LOCALE, detectLocale, getInitialLocale } from '@/i18n'
import { STORAGE_KEYS } from '@/utils/storage'

import { resetEnvironment } from './helpers'

function stubLanguages(languages: string[], language = languages[0] ?? '') {
  vi.spyOn(window.navigator, 'languages', 'get').mockReturnValue(languages)
  vi.spyOn(window.navigator, 'language', 'get').mockReturnValue(language)
}

beforeEach(() => resetEnvironment())
afterEach(() => vi.restoreAllMocks())

describe('detectLocale', () => {
  it('maps regional tags to the base language', () => {
    expect(detectLocale(['en-US'])).toBe('en')
    expect(detectLocale(['pl-PL'])).toBe('pl')
  })

  it('is case-insensitive and accepts underscores', () => {
    expect(detectLocale(['PL'])).toBe('pl')
    expect(detectLocale(['EN-gb'])).toBe('en')
    expect(detectLocale(['en_US'])).toBe('en')
  })

  it('picks the first supported language in preference order', () => {
    expect(detectLocale(['de-DE', 'en-US', 'pl'])).toBe('en')
    expect(detectLocale(['pl', 'en'])).toBe('pl')
  })

  it('returns null when nothing is supported or the list is empty', () => {
    expect(detectLocale(['de-DE', 'fr'])).toBeNull()
    expect(detectLocale([])).toBeNull()
    expect(detectLocale([''])).toBeNull()
  })

  it('does not match languages that merely start with a supported code', () => {
    expect(detectLocale(['pln'])).toBeNull()
    expect(detectLocale(['english'])).toBeNull()
  })

  it('reads navigator.languages by default', () => {
    stubLanguages(['de', 'pl-PL'])
    expect(detectLocale()).toBe('pl')
  })
})

describe('getInitialLocale', () => {
  it('prefers the stored choice over the browser language', () => {
    stubLanguages(['en-US'])
    window.localStorage.setItem(STORAGE_KEYS.locale, 'pl')
    expect(getInitialLocale()).toBe('pl')
  })

  it('uses the browser language when nothing is stored', () => {
    stubLanguages(['en-GB', 'pl'])
    expect(getInitialLocale()).toBe('en')
  })

  it('ignores an unsupported stored value and falls back to the browser', () => {
    stubLanguages(['en-US'])
    window.localStorage.setItem(STORAGE_KEYS.locale, 'de')
    expect(getInitialLocale()).toBe('en')
  })

  it('falls back to Polish when the browser language is unsupported', () => {
    stubLanguages(['de-DE', 'fr'])
    expect(getInitialLocale()).toBe(DEFAULT_LOCALE)
    expect(DEFAULT_LOCALE).toBe('pl')
  })

  it('falls back to Polish when no languages are available', () => {
    stubLanguages([], '')
    expect(getInitialLocale()).toBe('pl')
  })

  it('does not persist the detected language', () => {
    stubLanguages(['en-US'])
    expect(getInitialLocale()).toBe('en')
    expect(window.localStorage.getItem(STORAGE_KEYS.locale)).toBeNull()
  })
})

describe('startup', () => {
  afterEach(() => {
    vi.resetModules()
    document.documentElement.lang = ''
  })

  it('sets <html lang> from the detected browser language on module load', async () => {
    vi.resetModules()
    stubLanguages(['en-US'])
    document.documentElement.lang = ''
    const mod = await import('@/i18n')
    expect(mod.getCurrentLocale()).toBe('en')
    expect(document.documentElement.lang).toBe('en')
    expect(window.localStorage.getItem(STORAGE_KEYS.locale)).toBeNull()
  })

  it('sets <html lang> from the stored choice even if the browser differs', async () => {
    vi.resetModules()
    stubLanguages(['en-US'])
    window.localStorage.setItem(STORAGE_KEYS.locale, 'pl')
    document.documentElement.lang = ''
    await import('@/i18n')
    expect(document.documentElement.lang).toBe('pl')
  })

  it('defaults <html lang> to pl for an unsupported browser language', async () => {
    vi.resetModules()
    stubLanguages(['de'])
    document.documentElement.lang = ''
    await import('@/i18n')
    expect(document.documentElement.lang).toBe('pl')
  })
})
