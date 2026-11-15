import { flushPromises } from '@vue/test-utils'
import { nextTick } from 'vue'

import JourneyForm from '@/components/journey/JourneyForm.vue'
import PlaceInput from '@/components/journey/PlaceInput.vue'
import { applyLocale } from '@/i18n'
import en from '@/locales/en.json'
import pl from '@/locales/pl.json'
import { useCityStore } from '@/stores/city'
import { useJourneyStore } from '@/stores/journey'
import type { PlaceValue } from '@/utils/journey'

import { cityDetail } from './citiesFixtures'
import { jsonResponse, mountApp, resetEnvironment } from './helpers'
import { journeyResponse, stopResult } from './journeyFixtures'

const fetchMock = vi.fn()

beforeEach(() => {
  resetEnvironment()
  fetchMock.mockReset()
  fetchMock.mockImplementation(async () => jsonResponse([]))
  vi.stubGlobal('fetch', fetchMock)
})
afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

const stopCalls = () =>
  fetchMock.mock.calls.filter(([url]) => String(url).includes('/stops/')) as [string, RequestInit][]

const northgate: PlaceValue = {
  source: 'stop',
  name: 'Northgate',
  lat: 50.06,
  lon: 19.93,
  stopId: 'feed_a:stop_1',
}

function mountInput(props: Record<string, unknown> = {}) {
  return mountApp(PlaceInput, {
    props: { id: 'p', label: 'From', modelValue: null, city: 'alpha', ...props },
  })
}

async function type(wrapper: Awaited<ReturnType<typeof mountInput>>['wrapper'], value: string) {
  const input = wrapper.find('input')
  await input.setValue(value)
}

describe('PlaceInput', () => {
  it('debounces typing into a single stop search with the final text', async () => {
    vi.useFakeTimers()
    fetchMock.mockImplementation(async () => jsonResponse([stopResult()]))
    const { wrapper } = await mountInput()
    await type(wrapper, 'no')
    await type(wrapper, 'nor')
    await type(wrapper, 'north')
    await vi.advanceTimersByTimeAsync(100)
    expect(stopCalls()).toHaveLength(0)
    await vi.advanceTimersByTimeAsync(400)
    await flushPromises()
    expect(stopCalls()).toHaveLength(1)
    expect(stopCalls()[0]![0]).toBe('/api/v1/cities/alpha/stops/?q=north')
    expect(wrapper.findAll('[role="option"]')).toHaveLength(1)
    expect(wrapper.find('[role="option"]').text()).toContain('Northgate')
  })

  it('does not search for fewer than 2 characters', async () => {
    vi.useFakeTimers()
    const { wrapper } = await mountInput()
    await type(wrapper, ' n ')
    await vi.advanceTimersByTimeAsync(1000)
    expect(stopCalls()).toHaveLength(0)
  })

  it('selects a result with ArrowDown and Enter', async () => {
    vi.useFakeTimers()
    fetchMock.mockImplementation(async () =>
      jsonResponse([stopResult(), stopResult({ stop_id: 'feed_a:stop_5', name: 'Northfield' })]),
    )
    const { wrapper } = await mountInput()
    await type(wrapper, 'north')
    await vi.advanceTimersByTimeAsync(400)
    await flushPromises()
    const input = wrapper.find('input')
    await input.trigger('keydown', { key: 'ArrowDown' })
    await input.trigger('keydown', { key: 'ArrowDown' })
    expect(input.attributes('aria-activedescendant')).toBe('p-opt-1')
    await input.trigger('keydown', { key: 'Enter' })
    const emitted = wrapper.emitted('update:modelValue')!
    expect(emitted[emitted.length - 1]![0]).toMatchObject({
      source: 'stop',
      name: 'Northfield',
      stopId: 'feed_a:stop_5',
    })
  })

  it('selects the first result on Enter when none is highlighted', async () => {
    vi.useFakeTimers()
    fetchMock.mockImplementation(async () => jsonResponse([stopResult()]))
    const { wrapper } = await mountInput()
    await type(wrapper, 'north')
    await vi.advanceTimersByTimeAsync(400)
    await flushPromises()
    await wrapper.find('input').trigger('keydown', { key: 'Enter' })
    const emitted = wrapper.emitted('update:modelValue')!
    expect(emitted[emitted.length - 1]![0]).toMatchObject({ stopId: 'feed_a:stop_1' })
  })

  it('closes the list on Escape and wraps ArrowUp to the last option', async () => {
    vi.useFakeTimers()
    fetchMock.mockImplementation(async () =>
      jsonResponse([stopResult(), stopResult({ stop_id: 'feed_a:stop_5', name: 'Northfield' })]),
    )
    const { wrapper } = await mountInput()
    await type(wrapper, 'north')
    await vi.advanceTimersByTimeAsync(400)
    await flushPromises()
    const input = wrapper.find('input')
    await input.trigger('keydown', { key: 'ArrowUp' })
    expect(input.attributes('aria-activedescendant')).toBe('p-opt-1')
    await input.trigger('keydown', { key: 'Escape' })
    expect(input.attributes('aria-expanded')).toBe('false')
  })

  it('selects a result by mouse and shows the stop name', async () => {
    vi.useFakeTimers()
    fetchMock.mockImplementation(async () => jsonResponse([stopResult()]))
    const { wrapper } = await mountInput()
    await type(wrapper, 'north')
    await vi.advanceTimersByTimeAsync(400)
    await flushPromises()
    await wrapper.find('[role="option"]').trigger('mousedown')
    await wrapper.setProps({ modelValue: northgate })
    expect((wrapper.find('input').element as HTMLInputElement).value).toBe('Northgate')
  })

  it('shows a "no results" status for an empty list', async () => {
    vi.useFakeTimers()
    const { wrapper } = await mountInput()
    await type(wrapper, 'zzz')
    await vi.advanceTimersByTimeAsync(400)
    await flushPromises()
    expect(wrapper.find('[role="status"]').text()).toBe(
      pl.journey.autocomplete.noResults.replace('{query}', 'zzz'),
    )
    expect(wrapper.find('input').attributes('aria-expanded')).toBe('false')
  })

  it('shows an error status when the search fails', async () => {
    vi.useFakeTimers()
    fetchMock.mockRejectedValue(new TypeError('offline'))
    const { wrapper } = await mountInput()
    await type(wrapper, 'north')
    await vi.advanceTimersByTimeAsync(400)
    await flushPromises()
    expect(wrapper.find('[role="status"]').text()).toBe(pl.journey.autocomplete.error)
  })

  it('clears the chosen place when the user types again', async () => {
    const { wrapper } = await mountInput({ modelValue: northgate })
    expect((wrapper.find('input').element as HTMLInputElement).value).toBe('Northgate')
    await wrapper.find('input').setValue('Nor')
    const emitted = wrapper.emitted('update:modelValue')!
    expect(emitted[emitted.length - 1]![0]).toBeNull()
  })

  it('labels "my location" and map points through i18n', async () => {
    const { wrapper } = await mountInput({
      modelValue: { source: 'location', name: null, lat: 1, lon: 2 },
    })
    const input = wrapper.find('input').element as HTMLInputElement
    expect(input.value).toBe(pl.journey.place.myLocation)
    await wrapper.setProps({ modelValue: { source: 'map', name: null, lat: 1, lon: 2 } })
    expect(input.value).toBe(pl.journey.place.mapPoint)
    applyLocale('en')
    await nextTick()
    expect(input.value).toBe(en.journey.place.mapPoint)
  })

  it('shows the error text and links it to the field', async () => {
    const { wrapper } = await mountInput({ errorText: 'Denied!' })
    expect(wrapper.find('.place-input__error').text()).toBe('Denied!')
    expect(wrapper.find('input').attributes('aria-invalid')).toBe('true')
  })

  it('emits locate and pick from the icon buttons', async () => {
    const { wrapper } = await mountInput()
    const buttons = wrapper.findAll('button')
    await buttons[0]!.trigger('click')
    await buttons[1]!.trigger('click')
    expect(wrapper.emitted('locate')).toHaveLength(1)
    expect(wrapper.emitted('pick')).toHaveLength(1)
    expect(buttons[0]!.attributes('aria-label')).toBe(pl.journey.myLocation)
    expect(buttons[1]!.attributes('aria-label')).toBe(pl.journey.pickOnMap)
  })
})

async function mountForm() {
  const mounted = await mountApp(JourneyForm)
  const city = useCityStore()
  city.cityId = 'alpha'
  const journey = useJourneyStore()
  return { ...mounted, city, journey }
}

describe('JourneyForm', () => {
  it('swaps start and destination', async () => {
    const { wrapper, journey } = await mountForm()
    journey.setPlace('from', northgate)
    journey.setPlace('to', { source: 'map', name: null, lat: 50.02, lon: 19.89 })
    await nextTick()
    await wrapper.find('.journey-form__swap').trigger('click')
    expect(journey.from).toMatchObject({ source: 'map' })
    expect(journey.to).toMatchObject({ source: 'stop', name: 'Northgate' })
    const inputs = wrapper.findAll('input[role="combobox"]')
    expect((inputs[0]!.element as HTMLInputElement).value).toBe(pl.journey.place.mapPoint)
    expect((inputs[1]!.element as HTMLInputElement).value).toBe('Northgate')
  })

  it('shows the map-pick label for a point chosen on the map', async () => {
    const { wrapper, journey } = await mountForm()
    journey.startPicking('to')
    journey.pickPoint(50.02, 19.89)
    await nextTick()
    const inputs = wrapper.findAll('input[role="combobox"]')
    expect((inputs[1]!.element as HTMLInputElement).value).toBe(pl.journey.place.mapPoint)
    expect(journey.picking).toBeNull()
  })

  it('toggles picking from the map button and marks it pressed', async () => {
    const { wrapper, journey } = await mountForm()
    const pickButtons = wrapper.findAll('button[aria-pressed]')
    await pickButtons[0]!.trigger('click')
    expect(journey.picking).toBe('from')
    expect(wrapper.findAll('button[aria-pressed]')[0]!.attributes('aria-pressed')).toBe('true')
    await wrapper.findAll('button[aria-pressed]')[0]!.trigger('click')
    expect(journey.picking).toBeNull()
  })

  it('shows a validation message instead of sending an incomplete form', async () => {
    const { wrapper } = await mountForm()
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(wrapper.find('[role="alert"]').text()).toBe(pl.journey.problems.missing_from)
    expect(fetchMock.mock.calls.filter(([u]) => String(u).includes('journeys'))).toHaveLength(0)
  })

  it('reports the same place for identical start and destination', async () => {
    const { wrapper, journey } = await mountForm()
    journey.setPlace('from', northgate)
    journey.setPlace('to', northgate)
    await wrapper.find('form').trigger('submit')
    expect(wrapper.find('[role="alert"]').text()).toBe(pl.journey.problems.same_place)
  })

  it('submits a search request with stop id, coordinates and preferences', async () => {
    fetchMock.mockImplementation(async (url: string) =>
      String(url).includes('journeys') ? jsonResponse(journeyResponse()) : jsonResponse([]),
    )
    const { wrapper, journey } = await mountForm()
    journey.setPlace('from', northgate)
    journey.setPlace('to', { source: 'map', name: null, lat: 50.02, lon: 19.89 })
    await nextTick()
    await wrapper.find('input[type="checkbox"]').setValue(true)
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    const call = fetchMock.mock.calls.find(([u]) => String(u).includes('journeys'))!
    expect(call[0]).toBe('/api/v1/cities/alpha/journeys/search/')
    const body = JSON.parse((call[1] as RequestInit).body as string)
    expect(body.from).toEqual({ stop_id: 'feed_a:stop_1', name: 'Northgate' })
    expect(body.to).toEqual({ lat: 50.02, lon: 19.89 })
    expect(body.preferences.fewer_transfers).toBe(true)
    expect(body.time).toBeUndefined()
    expect(journey.status).toBe('ready')
  })

  it('disables the submit button while searching', async () => {
    let resolve!: (r: Response) => void
    fetchMock.mockImplementation(() => new Promise<Response>((r) => (resolve = r)))
    const { wrapper, journey } = await mountForm()
    journey.setPlace('from', northgate)
    journey.setPlace('to', { source: 'map', name: null, lat: 50.02, lon: 19.89 })
    await wrapper.find('form').trigger('submit')
    await nextTick()
    expect(wrapper.find('button[type="submit"]').attributes('disabled')).toBeDefined()
    resolve(jsonResponse(journeyResponse()))
    await flushPromises()
    expect(wrapper.find('button[type="submit"]').attributes('disabled')).toBeUndefined()
  })

  it('shows the date-time input only for depart-at and arrive-by, in the city time zone', async () => {
    const { wrapper, journey, city } = await mountForm()
    city.cityId = 'alpha'
    expect(wrapper.find('input[type="datetime-local"]').exists()).toBe(false)
    await wrapper.find('#journey-time-choice').setValue('arrive')
    expect(journey.timeChoice).toBe('arrive')
    const input = wrapper.find('input[type="datetime-local"]')
    expect(input.exists()).toBe(true)
    expect((input.element as HTMLInputElement).value).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/)
    expect(cityDetail('alpha').timezone).toBe('Europe/Warsaw')
  })

  it('translates labels when the language changes', async () => {
    const { wrapper } = await mountForm()
    expect(wrapper.text()).toContain(pl.journey.search)
    applyLocale('en')
    await nextTick()
    expect(wrapper.text()).toContain(en.journey.search)
    expect(wrapper.text()).not.toContain(pl.journey.search)
    expect(wrapper.find('.journey-form__swap').attributes('aria-label')).toBe(en.journey.swap)
  })
})

describe('my location', () => {
  function stubGeolocation(error: { code: number } | null) {
    const getCurrentPosition = vi.fn(
      (ok: (p: unknown) => void, fail: (e: { code: number }) => void) => {
        if (error) fail(error)
        else ok({ coords: { latitude: 50.03, longitude: 19.91 } })
      },
    )
    vi.stubGlobal('navigator', { ...navigator, geolocation: { getCurrentPosition } })
    return getCurrentPosition
  }

  it('shows the denied message under the field that asked', async () => {
    stubGeolocation({ code: 1 })
    const { wrapper } = await mountForm()
    await wrapper.findAll('.place-input__icon-button')[0]!.trigger('click')
    await flushPromises()
    const errors = wrapper.findAll('.place-input__error')
    expect(errors).toHaveLength(1)
    expect(errors[0]!.text()).toBe(pl.journey.locationErrors.denied)
  })

  it('shows the unsupported message when geolocation is missing', async () => {
    vi.stubGlobal('navigator', { ...navigator, geolocation: undefined })
    const { wrapper } = await mountForm()
    await wrapper.findAll('.place-input__icon-button')[0]!.trigger('click')
    await flushPromises()
    expect(wrapper.find('.place-input__error').text()).toBe(pl.journey.locationErrors.unsupported)
  })

  it('maps timeout and other errors to their own messages', async () => {
    stubGeolocation({ code: 3 })
    const { wrapper, journey } = await mountForm()
    await journey.useMyLocation('from')
    await nextTick()
    expect(wrapper.find('.place-input__error').text()).toBe(pl.journey.locationErrors.timeout)
    stubGeolocation({ code: 2 })
    await journey.useMyLocation('from')
    await nextTick()
    expect(wrapper.find('.place-input__error').text()).toBe(pl.journey.locationErrors.unavailable)
  })

  it('fills the field with the device position and clears the message on success', async () => {
    stubGeolocation(null)
    const { wrapper, journey } = await mountForm()
    await wrapper.findAll('.place-input__icon-button')[0]!.trigger('click')
    await flushPromises()
    expect(journey.from).toMatchObject({ source: 'location', lat: 50.03, lon: 19.91 })
    expect(wrapper.find('.place-input__error').exists()).toBe(false)
    expect((wrapper.find('input').element as HTMLInputElement).value).toBe(
      pl.journey.place.myLocation,
    )
  })

  it('translates the denied message to English', async () => {
    stubGeolocation({ code: 1 })
    const { wrapper } = await mountForm()
    applyLocale('en')
    await wrapper.findAll('.place-input__icon-button')[0]!.trigger('click')
    await flushPromises()
    expect(wrapper.find('.place-input__error').text()).toBe(en.journey.locationErrors.denied)
  })
})
