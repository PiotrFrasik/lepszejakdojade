import { flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

import { ApiError, parseRetryAfter } from '@/api/client'
import { useAssistantStore } from '@/stores/assistant'
import { useCityStore } from '@/stores/city'
import { MAX_HISTORY, MAX_MESSAGE_LENGTH, buildHistory, knownCards } from '@/utils/assistant'
import { SESSION_KEYS } from '@/utils/storage'

import { departuresCard, journeyCard, stopsCard } from './assistantFixtures'
import { cityList } from './citiesFixtures'

const sendChat = vi.fn()
vi.mock('@/api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/client')>()
  return { ...actual, sendChat: (...args: unknown[]) => sendChat(...args) }
})

function setup(sessionValue?: string) {
  window.sessionStorage.clear()
  if (sessionValue !== undefined) {
    window.sessionStorage.setItem(SESSION_KEYS.assistantConversation, sessionValue)
  }
  const pinia = createPinia()
  setActivePinia(pinia)
  const city = useCityStore()
  city.cities = cityList('en')
  city.cityId = 'alpha'
  const store = useAssistantStore()
  return { city, store }
}

const answer = (text: string, cards: unknown[] = []) => ({
  message: { role: 'assistant', text },
  cards,
})

beforeEach(() => {
  window.localStorage.clear()
  sendChat.mockReset()
})

describe('assistant store: sending', () => {
  it('sends the city and the conversation and appends the answer', async () => {
    const { store } = setup()
    sendChat.mockResolvedValue(answer('Hello there'))
    await store.ask('  When is the next tram?  ')
    expect(sendChat).toHaveBeenCalledTimes(1)
    expect(sendChat.mock.calls[0]![0]).toEqual({
      city: 'alpha',
      messages: [{ role: 'user', text: 'When is the next tram?' }],
    })
    expect(store.entries.map((e) => [e.role, e.text])).toEqual([
      ['user', 'When is the next tram?'],
      ['assistant', 'Hello there'],
    ])
    expect(store.draft).toBe('')
    expect(store.sending).toBe(false)
  })

  it('uses the draft by default and ignores blank questions', async () => {
    const { store } = setup()
    sendChat.mockResolvedValue(answer('ok'))
    await store.ask('   ')
    expect(sendChat).not.toHaveBeenCalled()
    store.draft = 'from draft'
    await store.ask()
    expect(sendChat.mock.calls[0]![0].messages[0].text).toBe('from draft')
  })

  it('sends only the last 20 messages, ending with the new question', async () => {
    const { store } = setup()
    sendChat.mockResolvedValue(answer('a'))
    for (let i = 0; i < 12; i++) await store.ask(`question ${i}`)
    const messages = sendChat.mock.calls[11]![0].messages
    expect(messages).toHaveLength(MAX_HISTORY)
    expect(messages[messages.length - 1]).toEqual({ role: 'user', text: 'question 11' })
  })

  it('rejects a question over the limit without calling the API', async () => {
    const { store } = setup()
    await store.ask('x'.repeat(MAX_MESSAGE_LENGTH + 1))
    expect(sendChat).not.toHaveBeenCalled()
    expect(store.problem?.kind).toBe('too_long')
    expect(store.entries).toHaveLength(0)
  })

  it('does not send without a city', async () => {
    const { store, city } = setup()
    city.cityId = null
    await store.ask('hello')
    expect(sendChat).not.toHaveBeenCalled()
  })

  it('ignores a second question while one is pending', async () => {
    const { store } = setup()
    let resolve!: (v: unknown) => void
    sendChat.mockReturnValue(new Promise((r) => (resolve = r)))
    const first = store.ask('one')
    await store.ask('two')
    expect(sendChat).toHaveBeenCalledTimes(1)
    expect(store.sending).toBe(true)
    resolve(answer('done'))
    await first
    expect(store.sending).toBe(false)
  })

  it('keeps only known, well-formed cards from the response', async () => {
    const { store } = setup()
    sendChat.mockResolvedValue(
      answer('here', [
        journeyCard(),
        { type: 'hologram', x: 1 },
        { type: 'journey' },
        { type: 'departures', stop: {} },
        null,
        'text',
        stopsCard(),
        departuresCard(),
      ]),
    )
    await store.ask('q')
    expect(store.entries[1]!.cards.map((c) => c.type)).toEqual(['journey', 'stops', 'departures'])
  })

  it('tolerates a response without cards or text', async () => {
    const { store } = setup()
    sendChat.mockResolvedValue({})
    await store.ask('q')
    expect(store.entries[1]).toMatchObject({ role: 'assistant', text: '', cards: [] })
  })
})

describe('assistant store: failures', () => {
  it('removes the question from the conversation and puts it back into the input', async () => {
    const { store } = setup()
    sendChat.mockRejectedValue(new ApiError(0, 'network_error', 'offline'))
    await store.ask('where is my bus')
    expect(store.entries).toHaveLength(0)
    expect(store.draft).toBe('where is my bus')
    expect(store.problem).toEqual({ kind: 'network' })
    expect(store.sending).toBe(false)
  })

  it('does not overwrite text the user typed meanwhile', async () => {
    const { store } = setup()
    sendChat.mockImplementation(async () => {
      store.draft = 'newer text'
      throw new ApiError(503, 'assistant_unavailable', 'x')
    })
    await store.ask('old')
    expect(store.draft).toBe('newer text')
  })

  it.each([
    [400, 'validation'],
    [503, 'unavailable'],
    [500, 'generic'],
  ])('maps HTTP %i to %s', async (status, kind) => {
    const { store } = setup()
    sendChat.mockRejectedValue(new ApiError(status, 'code', 'Translated server message'))
    await store.ask('q')
    expect(store.problem?.kind).toBe(kind)
    if (status === 400) expect(store.problem?.message).toBe('Translated server message')
  })

  it('maps a non-API error to generic', async () => {
    const { store } = setup()
    sendChat.mockRejectedValue(new Error('boom'))
    await store.ask('q')
    expect(store.problem?.kind).toBe('generic')
  })

  it('computes retryAt from Retry-After on 429', async () => {
    const { store } = setup()
    const before = Date.now()
    sendChat.mockRejectedValue(new ApiError(429, 'rate_limited', 'x', undefined, 30))
    await store.ask('q')
    expect(store.problem?.kind).toBe('rate_limited')
    expect(store.problem!.retryAt!).toBeGreaterThanOrEqual(before + 30_000)
    expect(store.problem!.retryAt!).toBeLessThanOrEqual(Date.now() + 30_000)
  })

  it('handles 429 without Retry-After', async () => {
    const { store } = setup()
    sendChat.mockRejectedValue(new ApiError(429, 'rate_limited', 'x'))
    await store.ask('q')
    expect(store.problem).toEqual({ kind: 'rate_limited' })
  })

  it('a pending request aborted by clear() does not add an answer or a problem', async () => {
    const { store } = setup()
    sendChat.mockImplementation(
      (_r: unknown, signal: AbortSignal) =>
        new Promise((_res, rej) =>
          signal.addEventListener('abort', () => rej(new DOMException('x', 'AbortError'))),
        ),
    )
    const pending = store.ask('q')
    store.clear()
    await pending
    expect(store.entries).toHaveLength(0)
    expect(store.problem).toBeNull()
    expect(store.sending).toBe(false)
  })
})

describe('assistant store: conversation lifetime', () => {
  it('clears the conversation when the city changes', async () => {
    const { store, city } = setup()
    sendChat.mockResolvedValue(answer('a'))
    await store.ask('q')
    store.draft = 'typed'
    city.cityId = 'beta'
    await flushPromises()
    expect(store.entries).toHaveLength(0)
    expect(store.draft).toBe('')
    expect(window.sessionStorage.getItem(SESSION_KEYS.assistantConversation)).toBeNull()
  })

  it('clear() starts a new conversation and removes the stored one', async () => {
    const { store } = setup()
    sendChat.mockResolvedValue(answer('a'))
    await store.ask('q')
    expect(window.sessionStorage.getItem(SESSION_KEYS.assistantConversation)).not.toBeNull()
    store.clear()
    expect(store.entries).toHaveLength(0)
    expect(store.isEmpty).toBe(true)
    expect(window.sessionStorage.getItem(SESSION_KEYS.assistantConversation)).toBeNull()
    sendChat.mockResolvedValue(answer('b'))
    await store.ask('again')
    expect(sendChat.mock.calls[1]![0].messages).toEqual([{ role: 'user', text: 'again' }])
  })

  it('persists the conversation and restores it for the same city', async () => {
    const first = setup()
    sendChat.mockResolvedValue(answer('stored answer', [stopsCard()]))
    await first.store.ask('stored question')
    const raw = window.sessionStorage.getItem(SESSION_KEYS.assistantConversation)!
    expect(JSON.parse(raw).city).toBe('alpha')

    const second = setup(raw)
    expect(second.store.entries.map((e) => e.text)).toEqual(['stored question', 'stored answer'])
    expect(second.store.entries[1]!.cards.map((c) => c.type)).toEqual(['stops'])
    sendChat.mockResolvedValue(answer('next'))
    await second.store.ask('follow up')
    expect(sendChat.mock.lastCall![0].messages).toHaveLength(3)
  })

  it('does not restore a conversation of another city', () => {
    const raw = JSON.stringify({
      city: 'beta',
      entries: [{ id: 1, role: 'user', text: 'q', cards: [] }],
    })
    expect(setup(raw).store.entries).toHaveLength(0)
  })

  it.each(['not json', '{"city":"alpha","entries":"x"}', 'null', '[]'])(
    'ignores corrupt stored data %s',
    (raw) => {
      expect(setup(raw).store.entries).toHaveLength(0)
    },
  )

  it('drops malformed stored entries and unknown cards', () => {
    const raw = JSON.stringify({
      city: 'alpha',
      entries: [
        { id: 1, role: 'user', text: 'ok', cards: [] },
        { id: 2, role: 'system', text: 'bad role' },
        { id: 3, role: 'assistant', text: 5 },
        { id: 4, role: 'assistant', text: 'fine', cards: [{ type: 'zzz' }, stopsCard()] },
      ],
    })
    const { store } = setup(raw)
    expect(store.entries.map((e) => e.text)).toEqual(['ok', 'fine'])
    expect(store.entries[1]!.cards).toHaveLength(1)
  })

  it('opens and closes the panel', () => {
    const { store } = setup()
    expect(store.panelOpen).toBe(false)
    store.openPanel()
    expect(store.panelOpen).toBe(true)
    store.closePanel()
    expect(store.panelOpen).toBe(false)
  })
})

describe('assistant utils', () => {
  it('buildHistory trims, truncates, drops empty and keeps the last 20', () => {
    const many = Array.from({ length: 30 }, (_, i) => ({ role: 'user' as const, text: `m${i}` }))
    expect(buildHistory(many)).toHaveLength(20)
    expect(buildHistory(many)[0]!.text).toBe('m10')
    const out = buildHistory([
      { role: 'assistant', text: '   ' },
      { role: 'assistant', text: ' ' + 'y'.repeat(MAX_MESSAGE_LENGTH + 50) },
    ])
    expect(out).toHaveLength(1)
    expect(out[0]!.text.length).toBeLessThanOrEqual(MAX_MESSAGE_LENGTH)
  })

  it('knownCards returns [] for non-arrays', () => {
    expect(knownCards(undefined)).toEqual([])
    expect(knownCards({})).toEqual([])
  })
})

describe('Retry-After parsing', () => {
  it('parses seconds, dates and garbage', () => {
    expect(parseRetryAfter('42')).toBe(42)
    expect(parseRetryAfter(null)).toBeNull()
    expect(parseRetryAfter('soon')).toBeNull()
    const parsed = parseRetryAfter(new Date(Date.now() + 10_000).toUTCString())!
    expect(parsed).toBeGreaterThanOrEqual(8)
    expect(parsed).toBeLessThanOrEqual(11)
    expect(parseRetryAfter(new Date(Date.now() - 60_000).toUTCString())).toBe(0)
  })
})
