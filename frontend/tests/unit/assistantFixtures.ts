import type {
  ChatDeparture,
  DeparturesChatCard,
  JourneyChatCard,
  StopsChatCard,
} from '@/types/api'

import { journeyItinerary, stopResult } from './journeyFixtures'
import { summary } from './timetableFixtures'

/** Fictional chat card fixtures (no real-city names). */

export function journeyCard(over: Partial<JourneyChatCard> = {}): JourneyChatCard {
  return {
    type: 'journey',
    from: { name: 'Northgate', lat: 50.0606, lon: 19.933 },
    to: { name: 'Southfield', lat: 50.0215, lon: 19.89 },
    itinerary: journeyItinerary(),
    comparison: {
      walk: { duration: 3900, distance: 5200 },
      bike: { duration: 1260, distance: 5600 },
    },
    ...over,
  }
}

export function chatDeparture(over: Partial<ChatDeparture> = {}): ChatDeparture {
  return {
    line: summary({ id: 'feed_a:7', short_name: '7' }),
    direction: 0,
    headsign: 'Southfield',
    time: '08:15',
    next_day: false,
    date: '2099-01-02',
    trip_id: 'feed_a:trip_1',
    // Platform the departure leaves from (contract: each departure has its own stop_id).
    stop_id: 'feed_a:platform_9',
    ...over,
  } as ChatDeparture
}

export function departuresCard(over: Partial<DeparturesChatCard> = {}): DeparturesChatCard {
  return {
    type: 'departures',
    stop: { stop_id: 'feed_a:stop_1', name: 'Northgate Square', lat: 50.06, lon: 19.93 },
    departures: [
      chatDeparture(),
      chatDeparture({
        direction: 1,
        headsign: 'Eastend',
        time: '00:10',
        next_day: true,
        trip_id: 'feed_a:trip_2',
      }),
    ],
    ...over,
  } as DeparturesChatCard
}

export function stopsCard(): StopsChatCard {
  return {
    type: 'stops',
    stops: [
      stopResult({ stop_id: 'feed_a:stop_1', name: 'Northgate' }),
      stopResult({ stop_id: 'feed_b:stop_5', name: 'Northgate Park', vehicle_types: ['bus'] }),
    ],
  }
}
