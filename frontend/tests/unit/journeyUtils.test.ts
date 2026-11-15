import {
  boundsOf,
  buildJourneyRequest,
  legsToGeoJson,
  placeToInput,
  samePlace,
  timeZoneOffsetMinutes,
  validateForm,
  zonedLocalNow,
  zonedLocalToIso,
  type JourneyFormValues,
  type PlaceValue,
} from '@/utils/journey'

import { journeyItinerary } from './journeyFixtures'

const WARSAW = 'Europe/Warsaw'

const stop = (over: Partial<PlaceValue> = {}): PlaceValue => ({
  source: 'stop',
  name: 'Northgate',
  lat: 50.06,
  lon: 19.93,
  stopId: 'feed_a:stop_1',
  ...over,
})
const point = (lat: number, lon: number): PlaceValue => ({
  source: 'map',
  name: null,
  lat,
  lon,
})

function form(over: Partial<JourneyFormValues> = {}): JourneyFormValues {
  return {
    from: stop(),
    to: point(50.02, 19.89),
    timeChoice: 'now',
    localTime: '',
    preferences: { fewer_transfers: false, less_walking: false, wheelchair: false },
    ...over,
  }
}

describe('zonedLocalToIso', () => {
  it('uses +01:00 in winter', () => {
    expect(zonedLocalToIso('2026-11-16T08:00', WARSAW)).toBe('2026-11-16T08:00:00+01:00')
  })

  it('uses +02:00 in summer', () => {
    expect(zonedLocalToIso('2026-07-15T08:00', WARSAW)).toBe('2026-07-15T08:00:00+02:00')
  })

  it('switches offset across the spring DST change (2026-03-29)', () => {
    expect(zonedLocalToIso('2026-03-29T01:30', WARSAW)).toBe('2026-03-29T01:30:00+01:00')
    expect(zonedLocalToIso('2026-03-29T03:30', WARSAW)).toBe('2026-03-29T03:30:00+02:00')
    expect(zonedLocalToIso('2026-03-30T00:30', WARSAW)).toBe('2026-03-30T00:30:00+02:00')
  })

  it('switches offset across the autumn DST change (2026-10-25)', () => {
    expect(zonedLocalToIso('2026-10-25T01:30', WARSAW)).toBe('2026-10-25T01:30:00+02:00')
    expect(zonedLocalToIso('2026-10-25T04:00', WARSAW)).toBe('2026-10-25T04:00:00+01:00')
  })

  it('produces an instant equal to the wall clock in the given zone', () => {
    const iso = zonedLocalToIso('2026-07-15T23:45', WARSAW)!
    expect(new Date(iso).toISOString()).toBe('2026-07-15T21:45:00.000Z')
  })

  it('handles zones with other offsets', () => {
    expect(zonedLocalToIso('2026-11-16T08:00', 'UTC')).toBe('2026-11-16T08:00:00+00:00')
    expect(zonedLocalToIso('2026-11-16T08:00', 'Asia/Kolkata')).toBe('2026-11-16T08:00:00+05:30')
    expect(zonedLocalToIso('2026-11-16T08:00', 'America/New_York')).toBe(
      '2026-11-16T08:00:00-05:00',
    )
  })

  it('returns null for malformed input or an unknown zone', () => {
    expect(zonedLocalToIso('', WARSAW)).toBeNull()
    expect(zonedLocalToIso('2026-11-16 08:00', WARSAW)).toBeNull()
    expect(zonedLocalToIso('2026-11-16T08:00:00', WARSAW)).toBeNull()
    expect(zonedLocalToIso('2026-11-16T08:00', 'Not/AZone')).toBeNull()
  })
})

describe('timeZoneOffsetMinutes and zonedLocalNow', () => {
  it('reports the zone offset in minutes', () => {
    expect(timeZoneOffsetMinutes(new Date('2026-01-10T12:00:00Z'), WARSAW)).toBe(60)
    expect(timeZoneOffsetMinutes(new Date('2026-07-10T12:00:00Z'), WARSAW)).toBe(120)
  })

  it('renders the current wall clock of the zone, not of the browser', () => {
    const now = new Date('2026-11-16T23:30:00Z')
    expect(zonedLocalNow(WARSAW, now)).toBe('2026-11-17T00:30')
    expect(zonedLocalNow('UTC', now)).toBe('2026-11-16T23:30')
  })
})

describe('validateForm', () => {
  it('accepts a complete form', () => {
    expect(validateForm(form())).toBeNull()
  })

  it('reports missing places in order', () => {
    expect(validateForm(form({ from: null }))).toBe('missing_from')
    expect(validateForm(form({ to: null }))).toBe('missing_to')
    expect(validateForm(form({ from: null, to: null }))).toBe('missing_from')
  })

  it('rejects the same stop and (nearly) the same point', () => {
    expect(validateForm(form({ to: stop({ name: 'Other name' }) }))).toBe('same_place')
    expect(validateForm(form({ from: point(50.0, 19.9), to: point(50.000001, 19.9) }))).toBe(
      'same_place',
    )
  })

  it('tells two stops apart by id', () => {
    expect(samePlace(stop(), stop({ stopId: 'feed_a:stop_2' }))).toBe(false)
  })

  it('requires a valid local time unless leaving now', () => {
    expect(validateForm(form({ timeChoice: 'depart', localTime: '' }))).toBe('invalid_time')
    expect(validateForm(form({ timeChoice: 'arrive', localTime: 'tomorrow' }))).toBe('invalid_time')
    expect(validateForm(form({ timeChoice: 'now', localTime: '' }))).toBeNull()
    expect(validateForm(form({ timeChoice: 'depart', localTime: '2026-11-16T08:00' }))).toBeNull()
  })
})

describe('placeToInput', () => {
  it('sends the stop id with its name for stops', () => {
    expect(placeToInput(stop())).toEqual({ stop_id: 'feed_a:stop_1', name: 'Northgate' })
    expect(placeToInput(stop({ name: null }))).toEqual({ stop_id: 'feed_a:stop_1' })
  })

  it('sends only coordinates for map points and the device location', () => {
    expect(placeToInput(point(50.02, 19.89))).toEqual({ lat: 50.02, lon: 19.89 })
    expect(placeToInput({ source: 'location', name: null, lat: 1, lon: 2 })).toEqual({
      lat: 1,
      lon: 2,
    })
  })

  it('never sends both a stop id and coordinates', () => {
    expect('lat' in placeToInput(stop())).toBe(false)
  })
})

describe('buildJourneyRequest', () => {
  it('omits time for "now" and defaults to depart', () => {
    const request = buildJourneyRequest(form(), WARSAW)!
    expect(request).toEqual({
      from: { stop_id: 'feed_a:stop_1', name: 'Northgate' },
      to: { lat: 50.02, lon: 19.89 },
      time_mode: 'depart',
      preferences: { fewer_transfers: false, less_walking: false, wheelchair: false },
    })
    expect('time' in request).toBe(false)
  })

  it('sends an ISO time with the city offset for depart-at', () => {
    const request = buildJourneyRequest(
      form({ timeChoice: 'depart', localTime: '2026-07-15T08:00' }),
      WARSAW,
    )!
    expect(request.time).toBe('2026-07-15T08:00:00+02:00')
    expect(request.time_mode).toBe('depart')
  })

  it('uses time_mode arrive for arrive-by', () => {
    const request = buildJourneyRequest(
      form({ timeChoice: 'arrive', localTime: '2026-11-16T18:15' }),
      WARSAW,
    )!
    expect(request.time).toBe('2026-11-16T18:15:00+01:00')
    expect(request.time_mode).toBe('arrive')
  })

  it('passes preferences through as a copy', () => {
    const values = form({
      preferences: { fewer_transfers: true, less_walking: false, wheelchair: true },
    })
    const request = buildJourneyRequest(values, WARSAW)!
    expect(request.preferences).toEqual({
      fewer_transfers: true,
      less_walking: false,
      wheelchair: true,
    })
    expect(request.preferences).not.toBe(values.preferences)
  })

  it('returns null for an invalid form or an unconvertible time', () => {
    expect(buildJourneyRequest(form({ from: null }), WARSAW)).toBeNull()
    expect(
      buildJourneyRequest(
        form({ timeChoice: 'depart', localTime: '2026-11-16T08:00' }),
        'Not/AZone',
      ),
    ).toBeNull()
  })
})

describe('map helpers', () => {
  it('converts legs to GeoJSON lines, falling back to the end points', () => {
    const itinerary = journeyItinerary()
    const walk = itinerary.legs[0]!
    walk.geometry = { type: 'LineString', coordinates: [] }
    const collection = legsToGeoJson(itinerary)
    expect(collection.features).toHaveLength(2)
    expect(collection.features[0]!.geometry.coordinates).toEqual([
      [walk.from.lon, walk.from.lat],
      [walk.to.lon, walk.to.lat],
    ])
    expect(collection.features[1]!.properties).toMatchObject({ mode: 'tram', colour: '#1f6feb' })
  })

  it('returns an empty collection for no itinerary', () => {
    expect(legsToGeoJson(null).features).toEqual([])
  })

  it('computes bounds of points', () => {
    expect(boundsOf([])).toBeNull()
    expect(
      boundsOf([
        [19, 50],
        [20, 49],
        [19.5, 51],
      ]),
    ).toEqual([
      [19, 49],
      [20, 51],
    ])
  })
})
