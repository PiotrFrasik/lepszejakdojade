import type { Itinerary, JourneyLeg, JourneySearchResponse, StopSearchResult } from '@/types/api'

/** Fictional journey data (no real-city names). */

export function stopResult(over: Partial<StopSearchResult> = {}): StopSearchResult {
  return {
    stop_id: 'feed_a:stop_1',
    name: 'Northgate',
    lat: 50.06,
    lon: 19.93,
    vehicle_types: ['tram', 'bus'],
    stop_ids: ['feed_a:stop_1', 'feed_b:stop_2'],
    ...over,
  }
}

export function journeyItinerary(over: Partial<Itinerary> = {}): Itinerary {
  const walk: JourneyLeg = {
    mode: 'walk',
    start: '2026-11-16T08:03:00+01:00',
    end: '2026-11-16T08:07:00+01:00',
    duration: 240,
    distance: 300,
    from: { name: 'Northgate', stop_id: null, lat: 50.0606, lon: 19.933 },
    to: { name: 'Northgate Square', stop_id: 'feed_a:stop_1', lat: 50.061, lon: 19.9325 },
    line: null,
    headsign: null,
    trip_id: null,
    intermediate_stops: [],
    geometry: {
      type: 'LineString',
      coordinates: [
        [19.933, 50.0606],
        [19.9325, 50.061],
      ],
    },
  }
  const tram: JourneyLeg = {
    mode: 'tram',
    start: '2026-11-16T08:07:00+01:00',
    end: '2026-11-16T08:20:00+01:00',
    duration: 780,
    distance: 4100,
    from: { name: 'Northgate Square', stop_id: 'feed_a:stop_1', lat: 50.061, lon: 19.9325 },
    to: { name: 'Southfield', stop_id: 'feed_a:stop_9', lat: 50.017, lon: 19.889 },
    line: {
      id: 'feed_a:52',
      short_name: '52',
      vehicle_type: 'tram',
      group: 'day',
      colour: '#1f6feb',
      text_colour: '#ffffff',
    },
    headsign: 'Southfield',
    trip_id: 'feed_a:trip_3',
    intermediate_stops: [{ name: 'Midtown', stop_id: 'feed_a:stop_2' }],
    geometry: {
      type: 'LineString',
      coordinates: [
        [19.9325, 50.061],
        [19.889, 50.017],
      ],
    },
  }
  return {
    id: 'i1',
    start: '2026-11-16T08:03:00+01:00',
    end: '2026-11-16T08:20:00+01:00',
    duration: 1020,
    transfers: 0,
    walk_distance: 300,
    walk_duration: 240,
    legs: [walk, tram],
    ...over,
  }
}

export function journeyResponse(over: Partial<JourneySearchResponse> = {}): JourneySearchResponse {
  return {
    from: { name: 'Northgate', lat: 50.0606, lon: 19.933 },
    to: { name: null, lat: 50.0215, lon: 19.89 },
    itineraries: [journeyItinerary(), journeyItinerary({ id: 'i2', transfers: 2 })],
    comparison: {
      walk: { duration: 3900, distance: 5200 },
      bike: { duration: 1260, distance: 5600 },
    },
    ...over,
  }
}
