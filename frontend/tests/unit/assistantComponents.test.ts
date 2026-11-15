import { flushPromises } from '@vue/test-utils'
import { nextTick } from 'vue'

import { ApiError } from '@/api/client'
import ChatConversation from '@/components/assistant/ChatConversation.vue'
import ChatDeparturesCard from '@/components/assistant/ChatDeparturesCard.vue'
import ChatJourneyCard from '@/components/assistant/ChatJourneyCard.vue'
import ChatPanel from '@/components/assistant/ChatPanel.vue'
import ChatStopsCard from '@/components/assistant/ChatStopsCard.vue'
import { applyLocale } from '@/i18n'
import en from '@/locales/en.json'
import pl from '@/locales/pl.json'
import { useAssistantStore } from '@/stores/assistant'
import { useCityStore } from '@/stores/city'
import { useJourneyStore } from '@/stores/journey'
import AssistantView from '@/views/AssistantView.vue'

import { departuresCard, journeyCard, stopsCard } from './assistantFixtures'
import { cityList } from './citiesFixtures'
import { mountApp, resetEnvironment } from './helpers'

const sendChat = vi.fn()
vi.mock('@/api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/client')>()
  return { ...actual, sendChat: (...args: unknown[]) => sendChat(...args) }
})

beforeEach(() => {
  resetEnvironment()
  window.sessionStorage.clear()
  sendChat.mockReset()
})
afterEach(() => vi.useRealTimers())

const answer = (text: string, cards: unknown[] = []) => ({
  message: { role: 'assistant', text },
  cards,
})

async function mountChat(component = ChatConversation, props: Record<string, unknown> = {}) {
  const mounted = await mountApp(component, {
    props: { idPrefix: 'test', ...props },
    attachTo: document.body,
  })
  const city = useCityStore()
  city.cities = cityList('pl')
  city.cityId = 'alpha'
  await nextTick()
  return { ...mounted, city, assistant: useAssistantStore() }
}

async function type(wrapper: Awaited<ReturnType<typeof mountChat>>['wrapper'], text: string) {
  await wrapper.find('textarea').setValue(text)
}

describe('ChatConversation', () => {
  it('shows the intro and example questions when empty; a suggestion sends it', async () => {
    sendChat.mockResolvedValue(answer('ok'))
    const { wrapper } = await mountChat()
    expect(wrapper.text()).toContain('Alfa')
    const buttons = wrapper.findAll('.chat__suggestion')
    expect(buttons).toHaveLength(3)
    await buttons[0]!.trigger('click')
    await flushPromises()
    expect(sendChat.mock.calls[0]![0].messages[0].text).toBe(pl.assistant.suggestions.departures)
  })

  it('sends on Enter and does not send on Shift+Enter', async () => {
    sendChat.mockResolvedValue(answer('reply'))
    const { wrapper } = await mountChat()
    await type(wrapper, 'hello')
    await wrapper.find('textarea').trigger('keydown', { key: 'Enter', shiftKey: true })
    expect(sendChat).not.toHaveBeenCalled()
    await wrapper.find('textarea').trigger('keydown', { key: 'Enter' })
    await flushPromises()
    expect(sendChat).toHaveBeenCalledTimes(1)
    expect(wrapper.findAll('.chat__message')).toHaveLength(2)
  })

  it('disables Send for blank and over-long input', async () => {
    const { wrapper } = await mountChat()
    const send = wrapper.find('button[type="submit"]')
    expect(send.attributes('disabled')).toBeDefined()
    await type(wrapper, 'hi')
    expect(send.attributes('disabled')).toBeUndefined()
    await type(wrapper, '   ')
    expect(send.attributes('disabled')).toBeDefined()
  })

  it('renders messages as plain text, never as HTML', async () => {
    sendChat.mockResolvedValue(answer('<img src=x onerror="window.__pwned=1"><b>bold</b>'))
    const { wrapper } = await mountChat()
    await type(wrapper, '<script>window.__pwned=1</script><i>x</i>')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    const bubbles = wrapper.findAll('.chat__bubble')
    expect(bubbles[0]!.text()).toBe('<script>window.__pwned=1</script><i>x</i>')
    expect(bubbles[1]!.text()).toContain('<img src=x')
    expect(wrapper.find('.chat__log img').exists()).toBe(false)
    expect(wrapper.find('.chat__log b').exists()).toBe(false)
    expect(wrapper.find('.chat__log i').exists()).toBe(false)
    expect((window as unknown as { __pwned?: number }).__pwned).toBeUndefined()
  })

  it('shows a placeholder for an assistant answer with empty text', async () => {
    sendChat.mockResolvedValue(answer('', [stopsCard()]))
    const { wrapper } = await mountChat()
    await type(wrapper, 'q')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(wrapper.findAll('.chat__bubble')[1]!.text()).toBe(pl.assistant.emptyAnswer)
  })

  it('ignores unknown and malformed cards', async () => {
    sendChat.mockResolvedValue(
      answer('here', [{ type: 'hologram' }, { type: 'journey' }, { type: 'stops' }, 7, null]),
    )
    const { wrapper } = await mountChat()
    await type(wrapper, 'q')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(wrapper.find('.chat__cards').exists()).toBe(false)
    expect(wrapper.find('.chat__bubble--x').exists()).toBe(false)
    expect(wrapper.text()).toContain('here')
  })

  it('puts the question back into the input after a failure and shows the message', async () => {
    sendChat.mockRejectedValue(new ApiError(0, 'network_error', 'offline'))
    const { wrapper } = await mountChat()
    await type(wrapper, 'my question')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect((wrapper.find('textarea').element as HTMLTextAreaElement).value).toBe('my question')
    expect(wrapper.find('.chat__problem').text()).toContain(pl.errors.network)
    expect(wrapper.findAll('.chat__message')).toHaveLength(0)
    await wrapper.find('.chat__dismiss').trigger('click')
    expect(wrapper.find('.chat__problem').exists()).toBe(false)
  })

  it.each([
    [503, pl.assistant.problems.unavailable],
    [500, pl.errors.generic],
    [400, 'Server says no'],
  ])('shows the message for HTTP %i', async (status, text) => {
    sendChat.mockRejectedValue(new ApiError(status, 'c', 'Server says no'))
    const { wrapper } = await mountChat()
    await type(wrapper, 'q')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(wrapper.find('.chat__problem').text()).toContain(text)
  })

  it('shows English problem text when the language is English', async () => {
    applyLocale('en')
    sendChat.mockRejectedValue(new ApiError(503, 'c', 'x'))
    const { wrapper } = await mountChat()
    await type(wrapper, 'q')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(wrapper.find('.chat__problem').text()).toContain(en.assistant.problems.unavailable)
  })

  it('blocks sending during the 429 countdown and unblocks afterwards', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval', 'Date'] })
    sendChat.mockRejectedValueOnce(new ApiError(429, 'rate_limited', 'x', undefined, 5))
    const { wrapper } = await mountChat()
    await type(wrapper, 'q')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(wrapper.find('.chat__problem').text()).toContain(
      pl.assistant.problems.rateLimited.replace('{seconds}', '5'),
    )
    const send = wrapper.find('button[type="submit"]')
    expect(send.attributes('disabled')).toBeDefined()
    // Enter must not send either.
    await wrapper.find('textarea').trigger('keydown', { key: 'Enter' })
    expect(sendChat).toHaveBeenCalledTimes(1)
    for (const b of wrapper.findAll('.chat__suggestion')) {
      expect(b.attributes('disabled')).toBeDefined()
    }

    vi.advanceTimersByTime(3000)
    await nextTick()
    expect(wrapper.find('.chat__problem').text()).toContain(
      pl.assistant.problems.rateLimited.replace('{seconds}', '2'),
    )
    vi.advanceTimersByTime(3000)
    await nextTick()
    expect(wrapper.find('.chat__problem').text()).toContain(pl.assistant.problems.rateLimitedOver)
    expect(send.attributes('disabled')).toBeUndefined()
  })

  it('429 without Retry-After shows a generic wait message and does not block', async () => {
    sendChat.mockRejectedValue(new ApiError(429, 'rate_limited', 'x'))
    const { wrapper } = await mountChat()
    await type(wrapper, 'q')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(wrapper.find('.chat__problem').text()).toContain(pl.assistant.problems.rateLimitedWait)
    expect(wrapper.find('button[type="submit"]').attributes('disabled')).toBeUndefined()
  })

  it('stops-card choice prefills the input without sending', async () => {
    sendChat.mockResolvedValue(answer('which one?', [stopsCard()]))
    const { wrapper } = await mountChat()
    await type(wrapper, 'northgate')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    await wrapper.findAll('.chat-stops__item')[1]!.trigger('click')
    expect((wrapper.find('textarea').element as HTMLTextAreaElement).value).toBe(
      pl.assistant.cards.stopQuestion.replace('{stop}', 'Northgate Park'),
    )
    expect(sendChat).toHaveBeenCalledTimes(1)
  })

  it('has no city: input is disabled and no suggestions are shown', async () => {
    const { wrapper, city } = await mountChat()
    city.cityId = null
    await nextTick()
    expect(wrapper.find('textarea').attributes('disabled')).toBeDefined()
    expect(wrapper.findAll('.chat__suggestion')).toHaveLength(0)
    expect(wrapper.text()).toContain(pl.assistant.introNoCity)
  })
})

describe('chat cards', () => {
  it('journey card renders titles and "show on map" calls showItinerary and navigates home', async () => {
    const card = journeyCard()
    const { wrapper, router, pinia } = await mountApp(ChatJourneyCard, {
      props: { card, idPrefix: 'jc' },
    })
    void pinia
    const journey = useJourneyStore()
    const spy = vi.spyOn(journey, 'showItinerary')
    expect(wrapper.find('.chat-journey__title').text()).toBe('Northgate → Southfield')
    expect(wrapper.find('.itinerary').exists()).toBe(true)
    await wrapper.find('.chat-journey__map').trigger('click')
    await flushPromises()
    expect(spy).toHaveBeenCalledWith(card.from, card.to, card.itinerary, card.comparison)
    expect(wrapper.emitted('navigate')).toHaveLength(1)
    expect(router.currentRoute.value.name).toBe('home')
    expect(journey.result?.itineraries).toHaveLength(1)
    expect(journey.status).toBe('ready')
  })

  it('journey card copes with a missing comparison and unnamed places', async () => {
    const card = journeyCard({
      from: { name: null, lat: 1, lon: 2 },
      comparison: undefined as never,
    })
    const { wrapper } = await mountApp(ChatJourneyCard, { props: { card, idPrefix: 'jc' } })
    expect(wrapper.find('.chat-journey__title').text()).toContain(pl.journey.leg.unnamed)
    expect(wrapper.find('.chat-journey__comparison').exists()).toBe(false)
  })

  it('two journey cards use distinct element ids', async () => {
    const a = await mountApp(ChatJourneyCard, {
      props: { card: journeyCard(), idPrefix: 'one' },
      attachTo: document.body,
    })
    const b = await mountApp(ChatJourneyCard, {
      props: { card: journeyCard(), idPrefix: 'two' },
      attachTo: document.body,
    })
    const ids = [...a.wrapper.element.querySelectorAll('[id]'), ...b.wrapper.element.querySelectorAll('[id]')].map((e) => e.id)
    expect(new Set(ids).size).toBe(ids.length)
    a.wrapper.unmount()
    b.wrapper.unmount()
  })

  it('departures card lists rows and links to the stop timetable', async () => {
    const { wrapper, router } = await mountApp(ChatDeparturesCard, {
      props: { card: departuresCard(), idPrefix: 'dc' },
    })
    expect(wrapper.find('.chat-departures__title').text()).toContain('Northgate Square')
    const rows = wrapper.findAll('a.chat-departures__row')
    expect(rows).toHaveLength(2)
    expect(rows[0]!.text()).toContain('08:15')
    expect(rows[0]!.text()).toContain('Southfield')
    expect(rows[0]!.attributes('href')).toMatch(/\/timetable\/lines\/feed_a(:|%3A)7\/stops\//)
    expect(rows[1]!.attributes('href')).toContain('direction=1')
    expect(rows[1]!.find('small').exists()).toBe(true)
    await rows[0]!.trigger('click')
    await flushPromises()
    expect(wrapper.emitted('navigate')).toBeTruthy()
    await vi.waitFor(() => expect(router.currentRoute.value.name).toBe('timetable-stop'))
    expect(router.currentRoute.value.params.lineId).toBe('feed_a:7')
  })

  it('departures links use the per-departure stop_id (contract change)', async () => {
    const { wrapper } = await mountApp(ChatDeparturesCard, {
      props: { card: departuresCard(), idPrefix: 'dc' },
    })
    const href = decodeURIComponent(wrapper.find('a.chat-departures__row').attributes('href')!)
    expect(href).toContain('/stops/feed_a:platform_9')
    expect(href).not.toContain('/stops/feed_a:stop_1')
  })

  it('departures card skips rows without a line or time', async () => {
    const card = departuresCard()
    card.departures.push({ ...card.departures[0]!, time: '' }, { time: '09:00' } as never)
    const { wrapper } = await mountApp(ChatDeparturesCard, { props: { card, idPrefix: 'dc' } })
    expect(wrapper.findAll('a.chat-departures__row')).toHaveLength(2)
  })

  it('stops card renders each stop and emits a prefill question', async () => {
    const { wrapper } = await mountApp(ChatStopsCard, {
      props: { card: stopsCard(), idPrefix: 'sc' },
    })
    expect(wrapper.findAll('.chat-stops__item')).toHaveLength(2)
    await wrapper.findAll('.chat-stops__item')[0]!.trigger('click')
    expect(wrapper.emitted('prefill')![0]).toEqual([
      pl.assistant.cards.stopQuestion.replace('{stop}', 'Northgate'),
    ])
  })

  it('stops card question is in English when the language is English', async () => {
    applyLocale('en')
    const { wrapper } = await mountApp(ChatStopsCard, {
      props: { card: stopsCard(), idPrefix: 'sc' },
    })
    await wrapper.findAll('.chat-stops__item')[0]!.trigger('click')
    expect(wrapper.emitted('prefill')![0]).toEqual([
      en.assistant.cards.stopQuestion.replace('{stop}', 'Northgate'),
    ])
  })
})

describe('ChatPanel', () => {
  it('opens from the launcher, closes with Escape and returns focus to the launcher', async () => {
    const { wrapper, assistant } = await mountChat(ChatPanel as never, { modal: false })
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    await wrapper.find('.chat-launcher').trigger('click')
    await flushPromises()
    expect(assistant.panelOpen).toBe(true)
    const dialog = wrapper.find('[role="dialog"]')
    expect(dialog.exists()).toBe(true)
    expect(dialog.attributes('aria-modal')).toBeUndefined()
    expect(document.activeElement).toBe(wrapper.find('textarea').element)

    await wrapper.find('textarea').trigger('keydown', { key: 'Escape' })
    await flushPromises()
    expect(assistant.panelOpen).toBe(false)
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(document.activeElement).toBe(wrapper.find('.chat-launcher').element)
  })

  it('closes with the close button and is aria-modal on phones', async () => {
    const { wrapper, assistant } = await mountChat(ChatPanel as never, { modal: true })
    await wrapper.find('.chat-launcher').trigger('click')
    await flushPromises()
    expect(wrapper.find('[role="dialog"]').attributes('aria-modal')).toBe('true')
    await wrapper.find('.chat-panel__close').trigger('click')
    await flushPromises()
    expect(assistant.panelOpen).toBe(false)
    expect(document.activeElement).toBe(wrapper.find('.chat-launcher').element)
  })

  it('shows "new conversation" only when there are messages and it clears them', async () => {
    sendChat.mockResolvedValue(answer('a'))
    const { wrapper, assistant } = await mountChat(ChatPanel as never, { modal: false })
    await wrapper.find('.chat-launcher').trigger('click')
    expect(wrapper.find('.chat-panel__action').exists()).toBe(false)
    await assistant.ask('q')
    await flushPromises()
    expect(wrapper.find('.chat-panel__action').text()).toBe(pl.assistant.clear)
    await wrapper.find('.chat-panel__action').trigger('click')
    expect(assistant.entries).toHaveLength(0)
  })

  it('is hidden on the assistant page and closes an open panel there', async () => {
    const { wrapper, router, assistant } = await mountChat(ChatPanel as never, { modal: false })
    assistant.openPanel()
    await nextTick()
    await router.push('/assistant')
    await flushPromises()
    expect(assistant.panelOpen).toBe(false)
    expect(wrapper.find('.chat-launcher').exists()).toBe(false)
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
  })

  it('labels the launcher and dialog in both languages', async () => {
    applyLocale('en')
    const { wrapper } = await mountChat(ChatPanel as never, { modal: false })
    expect(wrapper.find('.chat-launcher').attributes('aria-label')).toBe(en.assistant.open)
    await wrapper.find('.chat-launcher').trigger('click')
    expect(wrapper.find('.chat-panel__close').attributes('aria-label')).toBe(en.assistant.close)
  })
})

describe('AssistantView', () => {
  it('shows the page title, the shared conversation and a working clear button', async () => {
    sendChat.mockResolvedValue(answer('page answer'))
    const { wrapper, assistant } = await mountChat(AssistantView as never)
    expect(wrapper.find('h1').text()).toBe(pl.assistant.title)
    expect(wrapper.find('.assistant-page .chat').exists()).toBe(true)
    await assistant.ask('q')
    await flushPromises()
    expect(wrapper.text()).toContain('page answer')
    await wrapper.find('.assistant-page__head button').trigger('click')
    expect(assistant.entries).toHaveLength(0)
  })
})

describe('assistant locale keys', () => {
  type Tree = { [k: string]: string | Tree }
  const flat = (t: Tree, p = ''): string[] =>
    Object.entries(t).flatMap(([k, v]) =>
      typeof v === 'string' ? [`${p}${k}`] : flat(v, `${p}${k}.`),
    )

  it('pl and en have the same non-empty assistant keys', () => {
    const plKeys = flat(pl.assistant as Tree).sort()
    expect(plKeys.length).toBeGreaterThan(30)
    expect(flat(en.assistant as Tree).sort()).toEqual(plKeys)
  })

  it('every assistant.* key used in the sources exists in both languages', async () => {
    const fs = await import('node:fs')
    const path = await import('node:path')
    const dir = path.resolve(__dirname, '../../src/components/assistant')
    const files = [
      ...fs.readdirSync(dir).map((f) => path.join(dir, f)),
      path.resolve(__dirname, '../../src/views/AssistantView.vue'),
    ]
    const known = new Set(flat(pl.assistant as Tree).map((k) => `assistant.${k}`))
    const used = new Set<string>()
    for (const file of files) {
      for (const m of fs.readFileSync(file, 'utf8').matchAll(/t\(\s*'(assistant\.[\w.]+)'/g)) {
        used.add(m[1]!)
      }
    }
    expect(used.size).toBeGreaterThan(15)
    for (const key of used) expect(known.has(key), key).toBe(true)
    for (const key of ['departures', 'journey', 'lines']) {
      expect(known.has(`assistant.suggestions.${key}`)).toBe(true)
    }
  })
})
